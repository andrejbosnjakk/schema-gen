"""Analysis context shared by the rules, the direction convention, the pinout and the simulation: pin data per
terminal, protection regions, CAN buses."""
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from .model import Component, Model, Part, PinDef, Terminal
from .net import Net, NodeKey

# terminal names that say which way power flows when the part library has no pin type
SOURCE_NAMES = {"load", "out", "no", "nc", "+", "output"}
SINK_NAMES = {"line", "in", "com", "input", "bat", "supply"}
POWER_CLASSES_EXCLUDED = {"GND", "signal", "CAN"}


@dataclass
class CanBus:
    net_id: str
    polarity: str                   # H or L
    conductors: list[int] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)          # component ids with CAN pins (terminators excluded)
    terminators: list[NodeKey] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)        # components on the bus without CAN pin data (nodes inferred from their stubs)
    inferred_terms: list[str] = field(default_factory=list) # terminations inferred from the device name (no pin data)


class Ctx:
    def __init__(self, model: Model, cfg: Any = None):
        self.m, self.cfg = model, cfg
        self.net = Net(model)
        self.parts: dict[str, Part] = {p.id: p for p in model.parts}
        self.comp: dict[str, Component] = {c.raw: c for c in model.components}
        self.comp_by_id: dict[str, Component] = {c.id: c for c in model.components}

    # ---------------------------------------------------------------- pins
    def part_of(self, raw: str) -> Part | None:
        c = self.comp.get(raw)
        return self.parts.get(c.part) if c and c.part else None

    def pin(self, t: Terminal) -> PinDef | None:
        p = self.part_of(t.device)
        return p.pin(t.connector, t.pin) if p else None

    def pin_type(self, t: Terminal) -> str | None:
        """Pin type from the part library, else from the terminal name on breakers, switches, relays and batteries."""
        d = self.pin(t)
        if d and d.type: return d.type
        c = self.comp.get(t.device)
        if c and c.kind in ("breaker", "fuse", "switch", "relay", "battery", "dcdc"):
            if t.connector.strip().lower() == "coil": return "ground" if t.pin.strip() in ("-", "−", "A2") else "power_in"  # coil +/A1 is a load
            n = (t.pin or t.connector).strip().lower()
            words = set(n.split())  # named terminals: "load stud", "fuse output", "LV1 output"
            if n in SOURCE_NAMES or words & SOURCE_NAMES - {"+"}: return "power_out"
            if n in SINK_NAMES or words & SINK_NAMES: return "power_in"
            if n in ("-", "−", "gnd"): return "ground"
        return None

    def ref(self, t: Terminal) -> str:
        """Object reference of a terminal: pin:<component id>/<connector>/<pin>."""
        c = self.comp.get(t.device)
        return f"pin:{c.id if c else t.device}/{t.connector}/{t.pin}"

    @cached_property
    def by_terminal(self) -> dict[tuple[str, str, str], list[tuple[int, int]]]:
        out: dict[tuple[str, str, str], list[tuple[int, int]]] = defaultdict(list)
        for i, c in enumerate(self.m.conductors):
            out[c.from_.key()].append((i, 1)); out[c.to.key()].append((i, 2))
        return out

    def net_kind(self, idx: list[int]) -> str:
        k: dict[str, int] = defaultdict(int)
        for i in idx: k[self.m.conductors[i].kind] += 1
        return max(sorted(k), key=lambda x: k[x]) if k else ""

    # ---------------------------------------------------------------- protection regions
    def contact_peers(self, t: Terminal) -> list[Terminal]:
        """Terminals joined to t through a switch or relay contact (any state), from the part's contacts."""
        p = self.part_of(t.device)
        if not p or p.kind not in ("switch", "relay"): return []
        me = f"{t.connector}.{t.pin}" if t.pin else t.connector
        out = []
        for c in p.contacts:
            group = [x for x in (c.a, c.b, c.com, c.no, c.nc) if x]
            if me in group:
                for g in group:
                    if g != me:
                        con, _, pin = g.partition(".")
                        out.append(Terminal(device=t.device, connector=con, pin=pin))
        return out

    @cached_property
    def protected_by(self) -> dict[str, list[int]]:
        """Protective device id -> conductors downstream of its load side, through splices, harness pins and switch or
        relay contacts; the region ends at devices, buses and other protective devices."""
        out: dict[str, list[int]] = {}
        net, conds = self.net, self.m.conductors
        for comp in self.m.components:
            if comp.kind not in ("breaker", "fuse"): continue
            starts = [(i, e) for i, e in net.by_dev[comp.raw] if self.pin_type(conds[i].end(e)) == "power_out"]
            seen_c: set[int] = set()
            seen_n: set[NodeKey] = set()
            todo: deque[NodeKey] = deque(net.node(i, e) for i, e in starts)
            while todo:
                n = todo.popleft()
                if n in seen_n: continue
                seen_n.add(n)
                for i, e in net.at[n]:
                    if i in seen_c: continue
                    seen_c.add(i)
                    far = conds[i].end(3 - e)
                    if net.role(far.device) == "bus": continue  # a bus ends the region
                    todo.append(net.node(i, 3 - e))  # same node: splice, harness pin, or a device pin shared by several conductors
                    for peer in self.contact_peers(far): todo.append(net.node_of(peer))  # through switch / relay contacts
            out[comp.id] = sorted(seen_c)
        return out

    # ---------------------------------------------------------------- CAN
    @cached_property
    def can_buses(self) -> list[CanBus]:
        """CAN nets with their nodes and terminations; without pin data a device matching tables.can.terminator_pattern
        is a termination and any other device on the net a node (from its stub conductor)."""
        from . import tables
        tpat = re.compile(str(tables.table("can", self.cfg)["terminator_pattern"]), re.I)
        out = []
        for n in self.net.nets():
            if self.net_kind(n.conductors) != "CAN": continue
            pol = "L" if sum(self.m.conductors[i].can == "CAN_L" for i in n.conductors) * 2 > len(n.conductors) else "H"
            b = CanBus(net_id=n.id, polarity=pol, conductors=n.conductors)
            seen: set[str] = set()
            for node in n.nodes:
                if len(node) != 3: continue
                t = Terminal(device=node[0], connector=node[1], pin=node[2])
                comp = self.comp.get(t.device)
                if comp is None or comp.kind == "harness": continue
                d, p = self.pin(t), self.part_of(t.device)
                if d and (d.term or (p and p.term and d.type in ("can_h", "can_l"))): b.terminators.append(node)
                elif not (d and d.type in ("can_h", "can_l")) and not (p and p.kind == "terminator") and (tpat.search(comp.raw) or tpat.search(comp.id)):
                    b.terminators.append(node); b.inferred_terms.append(comp.id); continue
                if p and p.kind == "terminator": continue
                if comp.id in seen: continue
                seen.add(comp.id)
                if d and d.type in ("can_h", "can_l"): b.nodes.append(comp.id)
                else: b.unknown.append(comp.id)
            for i in n.conductors:  # a termination jumper between two pins of one device ("CAN termination: jumper pin 28 to pin 45")
                c = self.m.conductors[i]
                if c.from_.device == c.to.device and re.search(r"terminat", f"{c.name} {c.func}", re.I):
                    node = self.net.node(i, 1)
                    comp = self.comp.get(c.from_.device)
                    if comp and not any(t[0] == node[0] for t in b.terminators):
                        b.terminators.append(node); b.inferred_terms.append(comp.id)
            out.append(b)
        return out

    def length(self, i: int, measured: dict[str, float] | None = None) -> float | None:
        c = self.m.conductors[i]
        if measured and c.label in measured: return measured[c.label]
        return c.length_m


def harness_pins(m: Model, ctx: Ctx) -> dict[str, dict[str, dict[str, list[int]]]]:
    """Harness connector id -> pin -> side -> conductor indices."""
    out: dict[str, dict[str, dict[str, list[int]]]] = defaultdict(lambda: defaultdict(lambda: {"near": [], "far": []}))
    for i, c in enumerate(m.conductors):
        for t in (c.from_, c.to):
            comp = ctx.comp.get(t.device)
            if comp and comp.kind == "harness": out[comp.id][t.pin][t.side or "far"].append(i)
    return out


def dsub_size(raw: str) -> int | None:
    m = re.search(r"D-SUB (\d+)", raw)
    return int(m.group(1)) if m else None
