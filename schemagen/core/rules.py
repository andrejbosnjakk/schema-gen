"""Rules engine. Every rule has an id, a default severity, a message per finding, the objects it concerns and a fix
hint. Switch rules off or change their severity in schemagen.yml:

    rules:
      duplicate-ends: off
      contact-current: warning

`schemagen check <project> --format text|json|sarif` runs them and exits non-zero when there is an error.
Object references: conductor:<id>, component:<id>, connector:<id>, pin:<component>/<connector>/<pin>, net:<id>,
protective:<id>, open_item:<id>, label:<label>.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from . import direction, tables
from .context import Ctx, dsub_size, harness_pins
from .model import Issue, Model, Severity


@dataclass
class Rule:
    id: str
    severity: Severity
    title: str
    fn: Callable[[Ctx], Iterator[tuple[str, list[str], str]]]  # yields (message, objects, fix)


RULES: dict[str, Rule] = {}


def rule(rid: str, severity: Severity, title: str) -> Callable[[Callable[[Ctx], Iterator[tuple[str, list[str], str]]]], Any]:
    def deco(fn: Callable[[Ctx], Iterator[tuple[str, list[str], str]]]) -> Any:
        RULES[rid] = Rule(rid, severity, title, fn)
        return fn
    return deco


def cref(ctx: Ctx, i: int) -> str:
    return f"conductor:{ctx.m.conductors[i].id}"


# ---------------------------------------------------------------- identity
@rule("duplicate-id", "error", "Two conductors share an id")
def r_dup_id(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    seen: dict[str, list[str]] = defaultdict(list)
    for c in ctx.m.conductors: seen[c.id].append(c.label)
    for k, labs in seen.items():
        if len(labs) > 1: yield f"conductor id {k} is used {len(labs)} times (labels {', '.join(labs)})", [f"conductor:{k}"], "give each conductor its own id"


@rule("duplicate-ends", "warning", "Two conductors join the same two terminals")
def r_dup_ends(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    seen: dict[frozenset[tuple[str, str, str]], list[int]] = defaultdict(list)
    for i, c in enumerate(ctx.m.conductors):
        if c.extra.get("parallel"): continue
        seen[frozenset((c.from_.key(), c.to.key()))].append(i)
    for idx in seen.values():
        if len(idx) > 1:
            labs = [ctx.m.conductors[i].label for i in idx]
            yield f"{' and '.join(labs)} join the same two terminals", [cref(ctx, i) for i in idx], \
                "remove the duplicate, or mark intended parallel conductors with parallel: true"


@rule("label-duplicate", "error", "Two conductors share a printed label")
def r_dup_label(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    seen: dict[str, list[str]] = defaultdict(list)
    for c in ctx.m.conductors: seen[c.label].append(c.id)
    for lab, ids in seen.items():
        if len(ids) > 1: yield f"label {lab} is printed on {', '.join(ids)}", [f"conductor:{i}" for i in ids], "give each conductor its own label"


@rule("label-reused", "error", "A retired label is printed again")
def r_label_reused(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    retired = {e.label: e for e in ctx.m.ledger.entries if e.status == "retired"}
    for c in ctx.m.conductors:
        e = retired.get(c.label)
        if e: yield f"{c.id} uses label {c.label}, retired ({e.reason or 'no reason given'})", [f"conductor:{c.id}", f"label:{c.label}"], \
            "printed labels are never reused: assign a new label"


# ---------------------------------------------------------------- direction
@rule("direction", "warning", "Conductor runs against the direction convention")
def r_direction(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for f in direction.analyse(ctx):
        yield f"{f.label} ({f.id}) runs against the convention: {f.reason}", [f"conductor:{f.id}"], \
            "run `schemagen fix direction` to swap its ends (the label stays)"


@rule("direction-unknown", "info", "Signal wires whose direction cannot be told")
def r_direction_unknown(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    idx = direction.unknown(ctx)
    if idx: yield f"{len(idx)} signal wire(s) have no known direction", [cref(ctx, i) for i in idx], \
        "add pin types (signal_in / signal_out) to the part data, or direction.senders / receivers patterns"


# ---------------------------------------------------------------- protection and contacts
@rule("gauge-protection", "error", "Wire gauge too light for its protective device")
def r_gauge_prot(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    pds = {p.id: p for p in ctx.m.protective_devices}
    src = tables.table("protection", ctx.cfg)["source"]
    for pid, idx in ctx.protected_by.items():
        pd = pds.get(pid)
        if not pd or pd.rating_a is None: continue
        for i in idx:
            c = ctx.m.conductors[i]
            if c.awg is None: continue
            mx = tables.max_rating(c.awg, pd.kind, ctx.cfg)
            note = ""
            if mx is None:  # lighter than every gauge in the table: hold it to the lightest one
                light = tables.lightest(pd.kind, ctx.cfg)
                if light is None or c.awg <= light[0]: continue
                mx, note = light[1], f" (lighter than the lightest tabled gauge, {light[0]} AWG)"
            if pd.rating_a > mx:
                yield (f"{c.label}: {c.awg} AWG is protected by {pid} {pd.rating_a:g} A; at most {mx:g} A per {src}{note}",
                       [cref(ctx, i), f"protective:{pid}"], f"use a {pd.kind} of {mx:g} A or less, or a heavier gauge")


def _ends(ctx: Ctx) -> Iterator[tuple[int, int]]:
    for i, c in enumerate(ctx.m.conductors):
        yield i, 1
        yield i, 2


@rule("contact-gauge", "error", "Wire gauge outside the contact's AWG range")
def r_contact_awg(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for i, e in _ends(ctx):
        c = ctx.m.conductors[i]; t = c.end(e)
        d = ctx.pin(t)
        if not d or c.awg is None or (d.awg_min is None and d.awg_max is None): continue
        lo, hi = d.awg_min if d.awg_min is not None else 0, d.awg_max if d.awg_max is not None else 99
        if not lo <= c.awg <= hi:
            yield (f"{c.label}: {c.awg} AWG at {ctx.ref(t)[4:]}, the contact takes {lo}-{hi} AWG", [cref(ctx, i), ctx.ref(t)],
                   "change the gauge or the contact")


@rule("contact-current", "error", "Current above the contact rating")
def r_contact_i(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for i, e in _ends(ctx):
        c = ctx.m.conductors[i]; t = c.end(e)
        d = ctx.pin(t)
        if d and d.i_max is not None and c.current_a is not None and c.current_a > d.i_max:
            yield (f"{c.label}: {c.current_a:g} A through {ctx.ref(t)[4:]}, rated {d.i_max:g} A", [cref(ctx, i), ctx.ref(t)],
                   "spread the current over more contacts or use a larger contact")


@rule("dsub-gauge", "error", "Wire heavier than a D-sub crimp contact")
def r_dsub(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for i, e in _ends(ctx):
        c = ctx.m.conductors[i]; t = c.end(e)
        comp = ctx.comp.get(t.device)
        if comp and comp.kind == "harness" and dsub_size(t.device) and c.awg is not None and c.awg < 20:
            yield (f"{c.label}: {c.awg} AWG on {comp.id} pin {t.pin} is heavier than a standard D-sub crimp contact (20-24 AWG)",
                   [cref(ctx, i), f"pin:{comp.id}//{t.pin}"], "use 20 AWG or lighter, split over two contacts, or a power contact")


# ---------------------------------------------------------------- pin types on a net
def _net_pins(ctx: Ctx) -> Iterator[tuple[str, list[tuple[str, str]], bool]]:
    """(net id, [(pin type, pin ref)], has a GND bus) per net."""
    for n in ctx.net.nets():
        pins: list[tuple[str, str]] = []
        gnd_bus = False
        for node in n.nodes:
            if len(node) == 1:
                b = next((x for x in ctx.m.buses if x.raw == node[0]), None)
                gnd_bus = gnd_bus or bool(b and b.function_class == "GND")
            elif node[0] in ctx.comp and ctx.comp[node[0]].kind != "harness":
                from .model import Terminal
                t = Terminal(device=node[0], connector=node[1], pin=node[2])
                ty = ctx.pin_type(t) if ctx.pin(t) else None
                if ty: pins.append((ty, ctx.ref(t)))
        yield n.id, pins, gnd_bus


@rule("output-conflict", "error", "Two outputs drive one net")
def r_out_out(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for nid, pins, _ in _net_pins(ctx):
        for ty in ("signal_out", "power_out"):
            outs = [r for t, r in pins if t == ty]
            if len(outs) > 1:
                yield f"{len(outs)} {ty} pins on one net: {', '.join(o[4:] for o in outs)}", [nid] + outs, "one output per net; check the pin assignment"


@rule("power-ground", "error", "Power pin and ground on one net (short)")
def r_pwr_gnd(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for nid, pins, gnd_bus in _net_pins(ctx):
        pw = [r for t, r in pins if t in ("power_in", "power_out")]
        gd = [r for t, r in pins if t == "ground"]
        if pw and (gd or gnd_bus):
            yield (f"power pins {', '.join(p[4:] for p in pw)} share a net with ground ({', '.join(g[4:] for g in gd) or 'ground bus'})",
                   [nid] + pw + gd, "a power pin must not be wired to ground: check both ends")


@rule("required-pin", "warning", "Required pin not connected")
def r_required(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    used: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for k in ctx.by_terminal: used[k[0]].add((k[1], k[2]))
    for comp in ctx.m.components:
        p = ctx.parts.get(comp.part) if comp.part else None
        if not p or comp.raw not in used: continue
        for con in p.connectors:
            conns = {c for c, _ in used[comp.raw] if c == con.id or (con.match and re.search(con.match, c))}
            for pin in con.pins:
                if pin.required and not any((c, pin.n) in used[comp.raw] for c in conns):
                    yield (f"{comp.id} {con.id} pin {pin.n} ({pin.name or pin.type}) is required but not connected",
                           [f"component:{comp.id}", f"pin:{comp.id}/{con.id}/{pin.n}"], "wire the pin or mark it not required in the part data")


# ---------------------------------------------------------------- CAN
@rule("can-terminators", "error", "A CAN bus needs exactly two terminations")
def r_can_term(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    need = int(tables.table("can", ctx.cfg)["terminators"])
    for b in ctx.can_buses:
        if b.unknown and len(b.terminators) < need: continue  # reported by can-part-data
        if len(b.terminators) != need:
            yield (f"CAN_{b.polarity} bus {b.net_id[4:]} has {len(b.terminators)} termination(s), expected {need}",
                   [b.net_id] + [f"component:{ctx.comp[t[0]].id}" for t in b.terminators], "terminate the two ends of the bus, nothing in between")


@rule("can-part-data", "info", "CAN node without part data")
def r_can_unknown(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for b in ctx.can_buses:
        if b.unknown:
            yield (f"CAN_{b.polarity} bus {b.net_id[4:]}: no CAN pin data for {', '.join(b.unknown)}, so its terminations cannot be checked",
                   [b.net_id] + [f"component:{u}" for u in b.unknown], "add a card with can_h/can_l pins (and term: true where terminated)")


@rule("can-nodes", "warning", "CAN node count out of range")
def r_can_nodes(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    t = tables.table("can", ctx.cfg)
    for b in ctx.can_buses:
        n = len(b.nodes) + len(b.unknown)
        if not int(t["min_nodes"]) <= n <= int(t["max_nodes"]):
            yield f"CAN_{b.polarity} bus {b.net_id[4:]} has {n} nodes, allowed {t['min_nodes']}-{t['max_nodes']} ({t['source']})", [b.net_id], \
                "split the bus or add the missing nodes"


@rule("can-stub", "warning", "CAN stub too long")
def r_can_stub(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    from collections import deque
    t = tables.table("can", ctx.cfg)
    lim = float(t["max_stub_m"])
    measured = getattr(ctx, "measured", None) or {}
    net = ctx.net
    for b in ctx.can_buses:
        if len(b.terminators) != 2: continue
        adj: dict[Any, list[tuple[Any, int]]] = defaultdict(list)
        for i in b.conductors:
            a, c = net.node(i, 1), net.node(i, 2)
            adj[a].append((c, i)); adj[c].append((a, i))
        s, goal = b.terminators
        prev: dict[Any, tuple[Any, int] | None] = {s: None}
        q = deque([s])
        while q:
            x = q.popleft()
            for y, i in adj[x]:
                if y not in prev: prev[y] = (x, i); q.append(y)
        if goal not in prev: continue
        main, x = {goal}, goal
        while prev[x] is not None: x = prev[x][0]; main.add(x)  # type: ignore[index]
        for node in adj:  # stub length: from each device pin off the main path back to the path
            if node in main or len(node) != 3 or node[0] not in ctx.comp or ctx.comp[node[0]].kind == "harness": continue
            seen, q2, tot = {node: 0.0}, deque([node]), None
            while q2 and tot is None:
                x = q2.popleft()
                for y, i in adj[x]:
                    if y in seen: continue
                    ln = ctx.length(i, measured)
                    if ln is None: tot = -1.0; break
                    seen[y] = seen[x] + ln
                    if y in main: tot = seen[y]; break
                    q2.append(y)
            if tot is not None and tot > lim:
                comp = ctx.comp[node[0]].id
                yield f"CAN_{b.polarity} stub to {comp} is {tot:.2f} m, at most {lim:g} m ({t['source']})", [b.net_id, f"component:{comp}"], \
                    "move the splice closer to the node or run the bus through the node"


# ---------------------------------------------------------------- harness connectors (ported from 0.2)
@rule("open-end", "error", "Harness pin wired on one side only")
def r_open_end(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for h, pins in harness_pins(ctx.m, ctx).items():
        for p, sd in pins.items():
            ws = sd["near"] + sd["far"]
            if ws and (not sd["near"] or not sd["far"]):
                side = "near" if sd["near"] else "far"
                yield f"{h} pin {p}: only the {side} side is wired ({ctx.m.conductors[ws[0]].label})", [f"pin:{h}//{p}"] + [cref(ctx, i) for i in ws], \
                    "wire the mating half, or move the conductor to a pin that is wired through"


@rule("pin-clash", "error", "Two conductors on one harness pin and side")
def r_pin_clash(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for h, pins in harness_pins(ctx.m, ctx).items():
        for p, sd in pins.items():
            for s in ("near", "far"):
                if len(sd[s]) > 1:
                    yield f"{h} pin {p} {s} side: {', '.join(ctx.m.conductors[i].label for i in sd[s])}", [f"pin:{h}//{p}"] + [cref(ctx, i) for i in sd[s]], \
                        "one conductor per contact: move one to a spare pin, or splice before the connector"


@rule("half-naming", "warning", "One side of a harness connector has several half names")
def r_half_naming(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for con in ctx.m.connectors:
        for s in ("near", "far"):
            names = sorted(h.name for h in con.halves if h.side == s)
            if len(names) > 1:
                yield f"{con.id} {s} side uses several names: {' / '.join(names)}", [f"connector:{con.id}"], \
                    "use one name per half (or fix the sides in schemagen.yml)"


@rule("side-guessed", "warning", "Connector-half side guessed")
def r_side_guessed(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for con in ctx.m.connectors:
        for h in con.halves:
            if h.guessed:
                yield f"{con.id}: side of '{h.name}' guessed as {h.side}", [f"connector:{con.id}"], \
                    f"add sides: {{{con.id}: {{'{h.name}': near|far}}}} to schemagen.yml"


@rule("gauge-change", "warning", "Gauge changes across a harness pin")
def r_gauge_change(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for h, pins in harness_pins(ctx.m, ctx).items():
        for p, sd in pins.items():
            if sd["near"] and sd["far"]:
                ws = sd["near"] + sd["far"]
                if len({ctx.m.conductors[i].gauge for i in ws}) > 1:
                    yield f"{h} pin {p}: " + ", ".join(f"{ctx.m.conductors[i].label} {ctx.m.conductors[i].gauge}" for i in ws), \
                        [f"pin:{h}//{p}"] + [cref(ctx, i) for i in ws], "use one gauge through the contact"


@rule("class-change", "warning", "Function class changes across a harness pin")
def r_class_change(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for h, pins in harness_pins(ctx.m, ctx).items():
        for p, sd in pins.items():
            if sd["near"] and sd["far"]:
                ws = sd["near"] + sd["far"]
                if len({ctx.m.conductors[i].kind for i in ws}) > 1:
                    yield f"{h} pin {p}: " + ", ".join(f"{ctx.m.conductors[i].label} {ctx.m.conductors[i].kind}" for i in ws), \
                        [f"pin:{h}//{p}"] + [cref(ctx, i) for i in ws], "both halves must carry the same function"


# ---------------------------------------------------------------- open items and TBD
@rule("open-status", "info", "Conductor status is open")
def r_open_status(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for c in ctx.m.conductors:
        if c.status.lower().startswith("open"): yield f"{c.label} ({c.id}) status: {c.status}", [f"conductor:{c.id}"], "close the item and set the status"


@rule("open-item", "info", "Open item")
def r_open_item(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for o in ctx.m.open_items:
        if o.status.lower() not in ("closed", "done", "resolved"):
            yield f"{o.id}: {o.text}" + (f" ({', '.join(o.objects)})" if o.objects else ""), [f"open_item:{o.id}"] + [f"component:{x}" for x in o.objects], \
                f"owner {o.owner}" if o.owner else "assign an owner"


@rule("pin-tbd", "warning", "Connector or pin to be decided")
def r_pin_tbd(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for i, e in _ends(ctx):
        t = ctx.m.conductors[i].end(e)
        if "TBD" in f"{t.connector} {t.pin}":
            comp = ctx.comp.get(t.device)
            yield f"{ctx.m.conductors[i].label} at {comp.id if comp else t.device}: {t.connector} {t.pin}".strip(), [cref(ctx, i)], "decide the pin"


@rule("gauge-tbd", "warning", "Gauge to be decided")
def r_gauge_tbd(ctx: Ctx) -> Iterator[tuple[str, list[str], str]]:
    for i, c in enumerate(ctx.m.conductors):
        if c.awg is None: yield f"{c.label}: gauge '{c.gauge or 'empty'}'", [cref(ctx, i)], "set the gauge (AWG)"


# ---------------------------------------------------------------- engine
def run_rules(model: Model, cfg: Any = None, only: list[str] | None = None, measured: dict[str, float] | None = None,
              ctx: Ctx | None = None) -> list[Issue]:
    """All enabled rules; severity overrides and `off` come from schemagen.yml `rules:`."""
    ctx = ctx or Ctx(model, cfg)
    ctx.measured = measured or {}  # type: ignore[attr-defined]
    conf: dict[str, Any] = (getattr(cfg, "rules", None) or {}) if cfg else {}
    out: list[Issue] = []
    for rid, r in RULES.items():
        if only and rid not in only: continue
        sev = conf.get(rid, r.severity)
        if sev in ("off", False): continue
        for msg, objs, fix in r.fn(ctx):
            out.append(Issue(rule=rid, severity=sev, message=msg, objects=objs, fix=fix))
    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda x: (order[x.severity], x.rule, x.message))
