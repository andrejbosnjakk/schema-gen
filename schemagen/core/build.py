"""Build the typed Model from importer records: resolve labels, names, function classes, colours and connector sides,
and derive components, connectors, splices, buses, protective devices, switches, relays, harnesses and zones."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ..importers.records import Problem, Record, clean_extra, listof, number, sources, text
from .classes import classify, connector_size
from .config import Config
from .model import (Bus, Component, Conductor, Connector, ConnectorHalf, Decision, Harness, LabelEntry, LabelLedger, Model,
                    OpenItem, Part, ProtectiveDevice, Relay, Splice, Switch, Terminal, Zone)

CONDUCTOR_KEYS = {"id", "label", "name", "p1", "p1c", "p1p", "p1side", "p2", "p2c", "p2p", "p2side", "func", "bus", "cls", "awg",
                  "colour", "amps", "length", "st", "subsystem", "notes", "zone", "harn", "prot", "src"}
CODE = re.compile(r"[A-Z0-9][A-Za-z0-9_.-]*")


def code(raw: str) -> str | None:
    """Device code: the first token when it looks like one (upper case, digits, - _ .)."""
    tok = raw.split()[0] if raw.split() else raw
    return tok if CODE.fullmatch(tok) and any(c.isupper() for c in tok) else None


@dataclass
class Inputs:
    rows: list[Record]
    protection: list[Record] = field(default_factory=list)
    decisions: list[Record] = field(default_factory=list)
    open_items: list[Record] = field(default_factory=list)
    components: list[Record] = field(default_factory=list)
    connectors: list[Record] = field(default_factory=list)
    labels_sheet: list[Record] = field(default_factory=list)
    parts: list[Part] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)   # labels.json: id -> printed label
    names: dict[str, str] = field(default_factory=dict)    # names.py NAMES: id -> wire name
    display: dict[str, str] = field(default_factory=dict)  # DISPLAY: device string -> readable name
    ledger: list[dict[str, Any]] = field(default_factory=list)


class Builder:
    def __init__(self, cfg: Config, naming: Any, inp: Inputs):
        self.cfg, self.naming, self.inp = cfg, naming, inp
        self.problems: list[Problem] = []
        self.warnings: list[str] = []
        self.parts = inp.parts
        self._part_of: dict[str, Part | None] = {}
        self._h: dict[str, Any] = {}

    def harness(self, raw: str) -> Any:
        """The display module's harness(raw), cached: (name, code, far side) or None."""
        if raw not in self._h: self._h[raw] = self.naming.harness(raw)
        return self._h[raw]

    # ---------------------------------------------------------------- roles
    def part_for(self, raw: str) -> Part | None:
        if raw not in self._part_of:
            c = code(raw) or ""
            self._part_of[raw] = next((p for p in self.parts if p.device and re.search(p.device, c)), None)
        return self._part_of[raw]

    def kind(self, raw: str) -> str:
        c, cfg = code(raw) or "", self.cfg
        p = self.part_for(raw)
        if c.startswith(cfg.splice_prefix): return "splice"
        if self.harness(raw): return "harness"
        if c in cfg.buses or c.startswith(tuple(cfg.bus_prefixes)): return "bus"
        if c.startswith(tuple(cfg.breaker_prefixes)): return "fuse" if (p and p.kind == "fuse") or c.startswith("FU") else "breaker"
        if p and p.kind not in ("device", "splice", "bus", "harness", "breaker", "fuse"): return p.kind
        if c.startswith(tuple(cfg.relay_prefixes)): return "relay"
        if c.startswith(tuple(cfg.switch_prefixes)): return "switch"
        return "device"

    # ---------------------------------------------------------------- conductors
    def conductor(self, r: Record, kinds: dict[str, str]) -> Conductor | None:
        d = r.data
        bad = False
        for k in ("id", "p1", "p2"):
            if text(d.get(k)) == "":
                self.problems.append(Problem(r.file, r.row, r.col(k), f"'{r.col(k)}' is empty")); bad = True
        if bad: return None
        cid = text(d["id"])
        ends = []
        for e in (1, 2):
            dev = text(d[f"p{e}"])
            side = text(d.get(f"p{e}side")).lower()
            if side not in ("", "near", "far"):
                self.problems.append(Problem(r.file, r.row, r.col(f"p{e}side"), f"side must be near or far, not '{side}'")); side = ""
            ends.append(Terminal(device=dev, connector=text(d.get(f"p{e}c")), pin=text(d.get(f"p{e}p")), side=side))  # type: ignore[arg-type]
        extra = clean_extra({k: v for k, v in d.items() if k not in CONDUCTOR_KEYS})
        nums: dict[str, float | None] = {}
        for f, key in (("amps", "current_a"), ("length", "length_m")):
            v = number(d.get(f))
            if isinstance(v, str):
                self.warnings.append(f"{r.file}, row {r.row}, column '{r.col(f)}': '{v}' is not a number (kept as text in extra)")
                extra[f] = v; v = None
            nums[key] = v
        label = text(d.get("label")) or self.inp.labels.get(cid, cid)
        func = text(d.get("func"))
        bus = text(d.get("bus"))
        cls = text(d.get("cls"))
        kind, can, col = classify(cid, bus, func, label, self.cfg, cls)
        c: Conductor = Conductor.model_validate(dict(
            id=cid, label=label, name=text(d.get("name")) or self.inp.names.get(cid) or self.naming.strip(func),
            **{"from": ends[0]}, to=ends[1], func=func, bus=bus, cls=cls, gauge=text(d.get("awg")), colour=text(d.get("colour")),
            status=text(d.get("st")), subsystem=text(d.get("subsystem")), notes=text(d.get("notes")), zone=text(d.get("zone")),
            harness=text(d.get("harn")), protection=text(d.get("prot")), sources=sources(d.get("src")), extra=extra,
            kind=kind, can=can, colour_code=text(d.get("colour")) or col, **nums))
        for e in (1, 2):
            kinds.setdefault(c.end(e).device, "")
        return c

    # ---------------------------------------------------------------- connector sides
    def sides(self, conductors: list[Conductor], kinds: dict[str, str]) -> dict[str, Connector]:
        out: dict[str, Connector] = {}
        given: dict[tuple[str, str], str] = {}
        for r in self.inp.connectors:  # Connectors sheet: connector, half, side
            hc, hname, sd = text(r.data.get("connector")), text(r.data.get("half")), text(r.data.get("side")).lower()
            if hc and hname and sd in ("near", "far"): given.setdefault((hc, hname), sd)
        for hc, sm in self.cfg.sides.items():
            for hname, sd in sm.items(): given.setdefault((hc, hname), sd)
        halves: dict[str, dict[str, ConnectorHalf]] = defaultdict(dict)
        for c in conductors:  # row-level sides first
            for e in (1, 2):
                t = c.end(e)
                if kinds[t.device] != "harness" or not t.side: continue
                h = self.harness(t.device)[1]
                prev = halves[h].get(t.connector)
                if prev and prev.side != t.side:
                    self.warnings.append(f"{h}: half '{t.connector}' is given as both near and far; '{prev.side}' kept")
                elif not prev: halves[h][t.connector] = ConnectorHalf(name=t.connector, side=t.side)
        for c in conductors:
            for e in (1, 2):
                t = c.end(e)
                if kinds[t.device] != "harness": continue
                hn = self.harness(t.device)
                h = hn[1]
                if h not in out:
                    out[h] = Connector(id=h, raw=t.device, name=str(hn[0]), far_side=str(hn[2]) if len(hn) > 2 else "",
                                       pin_count=connector_size(t.device))
                half = halves[h].get(t.connector)
                if half is None:
                    gs = given.get((h, t.connector))
                    if gs: half = ConnectorHalf(name=t.connector, side=gs)  # type: ignore[arg-type]
                    else:
                        near = any(w in t.connector.lower() for w in self.cfg.near_words)
                        half = ConnectorHalf(name=t.connector, side="near" if near else "far", guessed=True)
                        self.warnings.append(f"{h}: side of half '{t.connector}' guessed as {half.side} from near_words; "
                                             f"set it in schemagen.yml (sides: {{{h}: {{'{t.connector}': near|far}}}})")
                    halves[h][t.connector] = half
                t.side = half.side
        top: dict[str, int] = {}
        for c in conductors:
            for t in (c.from_, c.to):
                if kinds[t.device] == "harness" and t.pin.isdigit():
                    h = self.harness(t.device)[1]; top[h] = max(top.get(h, 0), int(t.pin))
        for h, con in out.items():
            con.halves = sorted(halves[h].values(), key=lambda x: (x.side != "near", x.name))
            if con.pin_count is None: con.pin_count = connector_size(*(x.name for x in con.halves)) or top.get(h)
        return out

    # ---------------------------------------------------------------- everything else
    def build(self) -> Model:
        kinds: dict[str, str] = {}
        conductors = [c for c in (self.conductor(r, kinds) for r in self.inp.rows) if c]
        for raw in kinds: kinds[raw] = self.kind(raw)
        connectors = self.sides(conductors, kinds)
        # components
        zones_of: dict[str, Counter[str]] = defaultdict(Counter)
        for c in conductors:
            for e in (1, 2):
                if c.zone: zones_of[c.end(e).device][c.zone] += 1
        over = {text(r.data.get("device")): r for r in self.inp.components if text(r.data.get("device"))}
        comps: dict[str, Component] = {}
        for raw in kinds:
            cid = code(raw) or raw
            if kinds[raw] == "harness": cid = self.harness(raw)[1]
            k = 2
            base = cid
            while cid in comps: cid = f"{base}~{k}"; k += 1
            p = self.part_for(raw)
            zc = sorted(zones_of[raw].items(), key=lambda kv: (-kv[1], kv[0]))
            comp = Component(id=cid, raw=raw, name=str(self.naming.device(raw, self.inp.display)), kind=kinds[raw],  # type: ignore[arg-type]
                             part=p.id if p else "", zone=zc[0][0] if zc else "")
            if raw in over:
                od = over[raw].data
                for f in ("name", "part", "zone"):
                    if od.get(f) not in (None, ""): setattr(comp, f, text(od[f]))
                comp.extra = clean_extra({k: v for k, v in od.items() if k not in ("id", "device", "name", "kind", "part", "zone")})
            comps[cid] = comp
        cl = sorted(comps.values(), key=lambda x: x.id)
        m = Model(conductors=conductors, components=cl, connectors=sorted(connectors.values(), key=lambda x: x.id))
        bus_kind: dict[str, Counter[str]] = defaultdict(Counter)
        for c in conductors:
            for e in (1, 2): bus_kind[c.end(e).device][c.kind] += 1
        for x in cl:
            if x.kind == "splice": m.splices.append(Splice(id=x.id, raw=x.raw, zone=x.zone))
            elif x.kind == "bus":
                m.buses.append(Bus(id=x.id, raw=x.raw, function_class=bus_kind[x.raw].most_common(1)[0][0] if bus_kind[x.raw] else ""))
            elif x.kind in ("switch", "relay"):
                p = self.part_for(x.raw)
                if x.kind == "switch": m.switches.append(Switch(id=x.id, part=x.part, contacts=p.contacts if p else []))
                else: m.relays.append(Relay(id=x.id, part=x.part, coil=p.coil if p else None, contacts=p.contacts if p else []))
        m.protective_devices = self.protection(cl)
        m.parts = sorted(self.parts, key=lambda p: p.id)
        hs: dict[str, list[str]] = defaultdict(list)
        for c in conductors:
            if c.harness: hs[c.harness].append(c.id)
        m.harnesses = [Harness(id=h, name=h, conductors=ids) for h, ids in sorted(hs.items())]
        zs: dict[str, Zone] = {}
        for zk, v in self.cfg.zones.items():
            v = v or {}
            zs[str(zk)] = Zone(id=str(zk), name=str(v.get("name", zk)), xy=(float(v["xy"][0]), float(v["xy"][1])) if v.get("xy") else None)
        for zn in sorted({c.zone for c in conductors if c.zone} | {x.zone for x in cl if x.zone}):
            zs.setdefault(zn, Zone(id=zn, name=zn))
        m.zones = sorted(zs.values(), key=lambda z: z.id)
        m.decisions = [self._obj(Decision, r, {"id": ("id",), "date": ("date",), "text": ("text", "decision"), "by": ("by", "owner")})
                       for r in self.inp.decisions]
        m.open_items = [self._obj(OpenItem, r, {"id": ("id",), "text": ("text", "item"), "status": ("status",), "owner": ("owner",),
                                                "objects": ("objects", "object")}) for r in self.inp.open_items]
        m.decisions = [x for x in m.decisions if x]
        m.open_items = [x for x in m.open_items if x]
        led = [dict(r.data) for r in self.inp.labels_sheet] or self.inp.ledger
        try:
            m.ledger = LabelLedger(entries=[LabelEntry.model_validate({k: text(v) for k, v in e.items() if v not in (None, "")}) for e in led])
        except ValidationError as e:
            self.problems.append(Problem("label ledger", None, "", str(e)))
        return m

    def _obj(self, cls: Any, r: Record, keys: dict[str, tuple[str, ...]]) -> Any:
        d = {str(k).strip().lower(): v for k, v in r.data.items()}
        used: set[str] = set()
        out: dict[str, Any] = {}
        for f, names in keys.items():
            for n in names:
                if n in d and d[n] not in (None, ""):
                    out[f] = listof(d[n]) if f == "objects" else text(d[n]); used.add(n); break
        if not out.get("id"):
            self.problems.append(Problem(r.file, r.row, "id", "id is empty")); return None
        out["extra"] = clean_extra({k: v for k, v in r.data.items() if str(k).strip().lower() not in used})
        return cls.model_validate(out)

    def protection(self, comps: list[Component]) -> list[ProtectiveDevice]:
        keys = {"id": ("id", "code", "cb", "device"), "rating": ("rating", "rating_a", "amps", "a"), "panel": ("panel", "panel_label", "label"),
                "loads": ("loads", "load"), "kind": ("kind", "type"), "i_interrupt": ("i_interrupt", "i_interrupt_a", "interrupt"),
                "curve": ("trip_curve", "curve"), "src": ("sources", "src")}
        out: dict[str, ProtectiveDevice] = {}
        explicit_kind: set[str] = set()
        for r in self.inp.protection:
            d = {str(k).strip().lower(): v for k, v in r.data.items()}
            got: dict[str, Any] = {}
            used: set[str] = set()
            for f, names in keys.items():
                for n in names:
                    if n in d and d[n] not in (None, ""): got[f] = d[n]; used.add(n); break
            pid = text(got.get("id"))
            if not pid: self.problems.append(Problem(r.file, r.row, "id", "protective device without id")); continue
            extra = clean_extra({k: v for k, v in r.data.items() if str(k).strip().lower() not in used})
            rating = number(got.get("rating"))
            if isinstance(rating, str):
                self.warnings.append(f"{r.file}, row {r.row}: rating '{rating}' of {pid} is not a number (kept in extra)")
                extra["rating"] = rating; rating = None
            ii = number(got.get("i_interrupt"))
            if isinstance(ii, str): extra["i_interrupt"] = ii; ii = None
            kind = text(got.get("kind")).lower()
            if kind: explicit_kind.add(pid)
            out[pid] = ProtectiveDevice(id=pid, kind="fuse" if kind == "fuse" else "breaker", rating_a=rating, panel=text(got.get("panel")),
                                        loads=listof(got.get("loads")), trip_curve=text(got.get("curve")), i_interrupt=ii,
                                        sources=sources(got.get("src")), extra=extra)  # type: ignore[arg-type]
        for c in comps:
            if c.kind not in ("breaker", "fuse"): continue
            p = self.part_for(c.raw)
            pd = out.get(c.id)
            if pd is None:
                m = re.search(r"(\d+(?:[.,]\d+)?)\s*A\b", c.raw)
                pd = out[c.id] = ProtectiveDevice(id=c.id, kind=c.kind, rating_a=float(m.group(1).replace(",", ".")) if m else None)
            if pd.id not in explicit_kind: pd.kind = c.kind
            if not pd.trip_curve and p and p.trip_curve: pd.trip_curve = p.id
        return sorted(out.values(), key=lambda x: x.id)


def build(cfg: Config, naming: Any, inp: Inputs) -> tuple[Model, list[str], list[Problem]]:
    b = Builder(cfg, naming, inp)
    m = b.build()
    return m, b.warnings, b.problems
