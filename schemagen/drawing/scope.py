"""Scope -> scene (docs/drawing-model.md, Scene): which items, pins, wires and off-sheet flags a drawing of part of the
project contains. Every run is walked from the pins of the scope's components through splices and harness connector
pins to where it lands (`walk`, also behind the app's first drawing); conductors that leave a drawn node away from the
scope become off-sheet flags, so every conductor on a drawn node is a wire or a flag, never cut silently (D108)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from ..app.workspace import _natural, kind_of, severities
from ..core.model import Component, Contact, Terminal
from ..core.net import Net, NodeKey
from ..exporters.palette import HEX
from ..exporters.pinout import where
from .geometry import VERSION, Block, Cover, Fault, Item, Pin, Scene, SceneFlag, SceneWire, Scope

SCOPES = ("component", "connection", "harness", "selection", "subsystem", "system")
SYMBOLS = {"device": "block", "load": "block", "sensor": "block", "controller": "block", "harness": "harness", "splice": "splice",
           "bus": "bus", "breaker": "breaker", "fuse": "fuse", "switch": "switch", "relay": "relay", "terminator": "terminator",
           "battery": "battery", "dcdc": "dcdc"}  # and "ground": a bus whose function class is GND
COLUMNS = {"battery": 0, "dcdc": 0, "breaker": 1, "fuse": 1, "switch": 1, "relay": 1, "bus": 2, "block": 3, "harness": 4, "splice": 4,
           "terminator": 5, "ground": 6}
FAR_COLUMN = 5
Run = list[tuple[int, int]]  # (conductor index, the end it is walked away from)


# ---------------------------------------------------------------- runs (one implementation, also behind app/drawing.py)
def walk(net: Net, i: int, e: int, seen: frozenset[int] = frozenset()) -> list[Run]:
    """Every run from end e of conductor i to a terminal that is not a splice or a harness pin."""
    if net.role(net.c[i].end(3 - e).device) not in ("splice", "harness"): return [[(i, e)]]
    nxt = [(j, k) for j, k in net.at[net.node(i, 3 - e)] if j != i and j not in seen]
    return [[(i, e)] + r for j, k in nxt for r in walk(net, j, k, seen | {i})] or [[(i, e)]]


def _seg(st: Any, i: int, e: int, wsev: dict[str, str]) -> dict[str, Any]:
    """Conductor i walked away from its end e: the wire and where it lands."""
    ctx, c = st.ctx, st.m.conductors[i]
    o = c.end(3 - e)
    oc = ctx.comp.get(o.device)
    sim = (st.overlay or {}).get("items", {}).get(f"conductor:{c.id}")
    return dict(wire=c.id, label=c.label, name=c.name, gauge=gauge(c.gauge), colour=c.colour_code or c.colour, hex=ink(c),
                sev=wsev.get(c.id, ""), reason=sim["reason"] if sim and sim["status"] != "ok" else "",
                at=where(ctx, o), comp=oc.id if oc else "", role=ctx.net.role(o.device))


def _paths(st: Any, i: int, e: int, wsev: dict[str, str]) -> list[list[dict[str, Any]]]:
    """Every run from end e of conductor i, one list of segments each (the app's drawing)."""
    return [[_seg(st, j, k, wsev) for j, k in r] for r in walk(st.ctx.net, i, e)]


# ---------------------------------------------------------------- scope
def parse(text: str) -> Scope:
    """`component:VCU`, `connection:A~B`, `harness:X-FW`, `selection:A,B,C`, `subsystem:<name>` or `system`."""
    kind, _, rest = text.strip().partition(":")
    rest = rest.strip()
    if kind not in SCOPES: raise ValueError(f"unknown scope {text!r}: use component:, connection:, harness:, selection:, subsystem: or system")
    sep = {"connection": "~", "selection": ","}.get(kind)
    ids = [] if kind == "system" else list(dict.fromkeys(x.strip() for x in rest.split(sep) if x.strip())) if sep else [rest] if rest else []
    if (kind == "connection" and len(ids) != 2) or (kind != "system" and not ids):
        raise ValueError(f"scope {text!r}: " + ("connection:A~B names two components" if kind == "connection" else f"{kind}: needs an id"))
    return Scope(kind=kind, ids=ids, text=kind if kind == "system" else f"{kind}:{(sep or '').join(ids)}")  # type: ignore[typeddict-item]


def members(st: Any, sc: Scope) -> tuple[list[Component], list[Component]]:
    """The scope's components (drawn in full) and the components its runs must reach: for a connection the other end, for a selection of
    several components the ones after the first (the drawing is the first one's wiring to them, D117); else none."""
    ctx, k, ids = st.ctx, sc["kind"], sc["ids"]

    def comp(i: str) -> Component:
        c = ctx.comp_by_id.get(i)
        if c is None: raise ValueError(f"unknown component {i!r}")
        return c
    if k == "system": return list(st.m.components), []
    if k in ("connection", "selection") and len(ids) > 1: return [comp(ids[0])], [comp(i) for i in ids[1:]]
    if k == "subsystem":  # a component belongs to the subsystem most of its conductors belong to (ties: the first name)
        subs: dict[str, Counter[str]] = defaultdict(Counter)
        for cd in st.m.conductors:
            if cd.subsystem:
                for e in (1, 2): subs[cd.end(e).device][cd.subsystem] += 1
        out = [c for c in st.m.components if c.kind not in ("splice", "harness") and c.raw in subs
               and max(sorted(subs[c.raw]), key=lambda s: subs[c.raw][s]) == ids[0]]
        if not out: raise ValueError(f"no component in subsystem {ids[0]!r}")
        return out, []
    out = [comp(i) for i in ids]
    if k == "harness" and out[0].kind != "harness": raise ValueError(f"{ids[0]} is not a harness connector")
    return out, []


def symbol(st: Any, c: Component) -> str:
    k = kind_of(st, c)
    if k == "bus" and any(b.raw == c.raw and b.function_class == "GND" for b in st.m.buses): return "ground"
    return SYMBOLS.get(k, "block")


def model_id(c: Component) -> str:
    return f"connector:{c.id}" if c.kind == "harness" else f"component:{c.id}"


def gauge(g: str) -> str:
    """A gauge as the drawings print it: the number, without a unit (a sheet may say `22 AWG`; the drawings add the unit once)."""
    return re.sub(r"\s*awg\s*", "", str(g or ""), flags=re.I).strip()


def ink(c: Any) -> str:
    """The colour a conductor is drawn in: its colour code's, black for a bus-strip link (a solid bar, no wire colour), grey when unknown."""
    return "#000000" if c.link and not c.colour_code else HEX.get((c.colour_code or "")[:2], "#888")


def weight(awg: int | None) -> str:
    """Line weight class from the gauge: heavy <= 10 AWG, medium 12-16, light 18-22 (and unknown), fine >= 24."""
    if awg is None: return "light"
    return "heavy" if awg <= 10 else "medium" if awg <= 16 else "light" if awg <= 22 else "fine"


# ---------------------------------------------------------------- scene
def scene(st: Any, scope: str | Scope) -> Scene:
    """What a drawing of `scope` contains. `st` needs m, ctx and cfg; issues and overlay are used when present."""
    sc = parse(scope) if isinstance(scope, str) else scope
    S, to = members(st, sc)
    ctx, net, conds = st.ctx, st.ctx.net, st.m.conductors
    full = set() if to else {c.raw for c in S}
    tos = {c.raw for c in to}
    drawn: set[int] = set()
    nodes: set[NodeKey] = set()
    for c in S:
        for i, e in net.by_dev[c.raw]:
            for r in walk(net, i, e):
                if to and not any(conds[j].end(3 - k).device in tos for j, k in r): continue  # a connection or selection: runs that reach `to`
                nodes.add(net.node(i, e)); drawn.update(j for j, _ in r); nodes.update(net.node(j, 3 - k) for j, k in r)
    flags: dict[int, int] = {}  # conductor -> its end on a drawn node
    for j in range(len(conds)):
        if j in drawn: continue
        a, b = net.node(j, 1) in nodes, net.node(j, 2) in nodes
        if a and b: drawn.add(j)  # both ends on the sheet: drawn, not flagged
        elif a or b: flags[j] = 1 if a else 2
    touched: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for j in drawn:
        for e in (1, 2): t = conds[j].end(e); touched[t.device].add((t.connector, t.pin))
    for j, e in flags.items(): t = conds[j].end(e); touched[t.device].add((t.connector, t.pin))
    in_scope = {c.raw for c in S}
    items = [_item(st, ctx.comp[raw], raw in in_scope, raw in full, touched[raw]) for raw in set(touched) | in_scope]
    wsev = severities(st)[1] if hasattr(st, "issues") else {}
    overlay = (getattr(st, "overlay", None) or {}).get("items", {})
    wires = [_wire(st, conds[j], wsev, overlay) for j in drawn]
    fl = _collapse(st, flags, [_flag(st, j, e) for j, e in flags.items()], {j: net.node(j, e) for j, e in flags.items()}, in_scope)
    return Scene(version=VERSION, scope=sc, title=_title(st, sc, S, to), project=st.cfg.root.name,
                 items=sorted(items, key=lambda x: (x["column"], _natural(x["code"]))),
                 wires=sorted(wires, key=lambda w: _natural(w["id"])), flags=sorted(fl, key=lambda f: _natural(f["id"])))


COLLAPSE = 4  # flags on one bus or ground node from here on become one summary flag (D111)


def _collapse(st: Any, ends: dict[int, int], fl: list[SceneFlag], node: dict[int, NodeKey], in_scope: set[str]) -> list[SceneFlag]:
    """One summary flag per bus or ground node that carries COLLAPSE or more off-sheet flags; it lists the conductors it stands for.
    A bus or ground that is itself in scope keeps every flag: all its wires are drawn."""
    ctx, conds = st.ctx, st.m.conductors
    by: dict[NodeKey, list[int]] = defaultdict(list)
    for j, e in ends.items():
        c = ctx.comp.get(conds[j].end(e).device)
        if c and c.raw not in in_scope and symbol(st, c) in ("bus", "ground"): by[node[j]].append(j)
    drop: set[str] = set()
    out: list[SceneFlag] = []
    for js in by.values():
        if len(js) < COLLAPSE: continue
        js.sort(key=lambda j: _natural(conds[j].id))
        f0 = next(f for f in fl if f["model"] == f"conductor:{conds[js[0]].id}")
        words = {f["model"]: f["text"].removeprefix("→ ") for f in fl}
        drawings = {f["model"]: f.get("drawing", "") for f in fl}
        cov = [Cover(id=conds[j].id, at=ctx.ref(conds[j].end(ends[j])), target=ctx.ref(conds[j].end(3 - ends[j])), label=conds[j].label, gauge=gauge(conds[j].gauge),
                     colour=conds[j].colour_code or conds[j].colour, text=words.get(f"conductor:{conds[j].id}", ""),
                     drawing=drawings.get(f"conductor:{conds[j].id}", "")) for j in js]
        name = ctx.comp[conds[js[0]].end(ends[js[0]]).device]
        out.append(dict(f0, id=f"flag:+{conds[js[0]].id}", target_item="", text=f"+ {len(js)} more wires on {name.id}", drawing=name.id, covers=cov))  # type: ignore[arg-type]
        drop |= {f"conductor:{conds[j].id}" for j in js}
    return [f for f in fl if f["model"] not in drop] + out


def _title(st: Any, sc: Scope, S: list[Component], to: list[Component]) -> str:
    nm = lambda c: c.name or c.id  # noqa: E731
    if sc["kind"] == "system": return str(st.cfg.root.name)
    if sc["kind"] == "subsystem": return f"Subsystem {sc['ids'][0]}"
    if to: return f"{nm(S[0])} to {', '.join(nm(c) for c in to)}"
    return ", ".join(nm(c) for c in S)


def _item(st: Any, c: Component, scoped: bool, full: bool, terms: set[tuple[str, str]]) -> Item:
    ctx = st.ctx
    sym = symbol(st, c)
    wired = {(t.connector, t.pin) for t in (st.m.conductors[i].end(e) for i, e in ctx.net.by_dev[c.raw])}
    part = ctx.part_of(c.raw)
    terms = set(terms) | (wired if full else set())
    side: dict[str, str] = {}
    if c.kind == "harness":  # matched pins side by side: every half lists the same pin numbers
        con = next((x for x in st.m.connectors if x.id == c.id), None)
        halves = [h for h in (con.halves if con else []) if h.side == "near"] + [h for h in (con.halves if con else []) if h.side != "near"]
        side = {h.name: h.side for h in halves}
        nums = {p for _, p in terms} | ({str(k) for k in range(1, con.pin_count + 1)} if full and con and con.pin_count else set())
        names = [h.name for h in halves] + sorted({n for n, _ in terms} - set(side), key=_natural)
        terms = {(n, p) for n in names for p in nums}
    elif part and full:
        for cd in part.connectors:
            used = sorted({n for n, _ in wired if n == cd.id or (cd.match and re.search(cd.match, n))}, key=_natural)
            terms |= {(used[0] if used else cd.id, p.n) for p in cd.pins}
    cdef = lambda n: next((cd for cd in (part.connectors if part else []) if cd.id == n or (cd.match and re.search(cd.match, n))), None)  # noqa: E731
    blocks: list[Block] = []
    order = list(side) + sorted({n for n, _ in terms} - set(side), key=_natural)
    for n in order:
        pins: list[Pin] = []
        for p in sorted({p for m, p in terms if m == n}, key=_natural):
            t = Terminal(device=c.raw, connector=n, pin=p)
            d = ctx.pin(t)
            pins.append(Pin(n=p, name=d.name if d else "", type=(d.type if d and d.type else ctx.pin_type(t) or ""), anchor=ctx.ref(t), spare=(n, p) not in wired))
        cd = cdef(n)
        blocks.append(Block(id=n, part=cd.part if cd else "", mate=str(cd.extra.get("mate", "")) if cd else "", side=side.get(n, ""), pins=pins))
    if sym in ("breaker", "fuse", "terminator", "battery") and sum(len(b["pins"]) for b in blocks) > 2: sym = "block"     # these symbols draw two terminals
    role = "harness" if c.kind == "harness" else "in_scope" if scoped else "far_end" if sym == "block" else "part"
    column = 3 if scoped and sym == "block" else FAR_COLUMN if sym == "block" else COLUMNS[sym]
    return Item(id=model_id(c), model=model_id(c), role=role, symbol=sym, kind=c.kind, code=c.id, name=c.name or c.id, part=c.part,  # type: ignore[typeddict-item]
                location=c.zone, partial=not full, column=column, blocks=blocks, attrs=_attrs(st, c, sym))


def _attrs(st: Any, c: Component, sym: str) -> dict[str, Any]:
    """Symbol data: rating and panel label, contacts and coil, a terminator's value, a source's voltage, a bus's class."""
    ctx, part = st.ctx, st.ctx.part_of(c.raw)
    ref = lambda s: ctx.ref(Terminal(device=c.raw, connector=s.partition(".")[0], pin=s.partition(".")[2]))  # noqa: E731  ("CONNECTOR.PIN")
    if sym in ("breaker", "fuse"):
        pd = next((p for p in st.m.protective_devices if p.id == c.id), None)
        pins = {(t.connector, t.pin): ctx.pin_type(t) or "" for t in (st.m.conductors[i].end(e) for i, e in ctx.net.by_dev[c.raw])}
        gap = "LINE" if "power_out" in pins.values() else "LOAD" if "power_in" in pins.values() else "other side"
        return dict(rating_a=pd.rating_a if pd else None, panel=pd.panel if pd else "", open=[f"{gap}: not in wire list"] if len(pins) == 1 else [])
    if sym in ("switch", "relay"):
        rec = next((x for x in [*st.m.switches, *st.m.relays] if x.id == c.id), None)
        contacts: list[Contact] = (rec.contacts if rec else []) or (part.contacts if part else [])
        coil = getattr(rec, "coil", None) or (part.coil if part else None)
        return dict(state="normal", contacts=[{k: ref(v) for k, v in x.model_dump().items() if v} for x in contacts],
                    coil=dict(a1=ref(coil.a1), a2=ref(coil.a2)) if coil else None)
    if sym == "terminator":
        m = re.search(r"(\d+(?:\.\d+)?)\s*(k?)\s*(?:ohm|Ω)", f"{c.part} {c.name}", re.I)
        return dict(value=f"{m.group(1)} {m.group(2)}Ω" if m else "")
    if sym in ("battery", "dcdc"):
        src = part.source or part.supply_out if part else None
        return dict(voltage=(src.v_oc or src.v_out) if src else None)
    if sym in ("bus", "ground"):
        return dict(function_class=next((b.function_class for b in st.m.buses if b.raw == c.raw), ""))
    return {}


def _wire(st: Any, c: Any, wsev: dict[str, str], overlay: dict[str, Any]) -> SceneWire:
    ctx = st.ctx
    sim = overlay.get(f"conductor:{c.id}")
    return SceneWire(id=c.id, model=f"conductor:{c.id}", label=c.label, name=c.name, gauge=gauge(c.gauge), colour=c.colour_code or c.colour,
                     hex=ink(c), cls=c.can or c.kind, weight=weight(c.awg), a=ctx.ref(c.from_), b=ctx.ref(c.to),
                     pair=str(c.extra.get("pair", "")), shield=str(c.extra.get("shield", "")), harness=c.harness, sev=wsev.get(c.id, ""),
                     fault=Fault(status=sim["status"], reason=sim.get("reason", "")) if sim and sim.get("status") != "ok" else None)


def short(words: str, limit: int = 50) -> str:
    """The `via` part of a far end's words goes when they are long."""
    return re.sub(r"\s+via .*$", "", words) if len(words) > limit else words


def short_name(name: str, limit: int = 1000) -> str:
    """A component name without the bracket after it (what the part is) when longer than `limit`; off by default: two parts can differ only in the bracket."""
    return re.sub(r"\s*\([^)]*\)", "", name) if len(name) > limit else name


def terminal_words(ctx: Any, t: Terminal) -> str:
    """A terminal by display name: `Battery 14 V, + terminal`, `EFIS, J1, pin 2`; a splice or bus by its name."""
    c = ctx.comp.get(t.device)
    nm = short_name((c.name or c.id) if c else t.device)
    if c and c.kind in ("splice", "bus"): return nm
    return ", ".join(x for x in (nm, t.connector, f"pin {t.pin}" if t.pin else "terminal" if t.connector else "") if x)


def far_end(st: Any, j: int, e: int) -> tuple[str, str]:
    """Where the other end of conductor j (away from its end e) is, in words, and the id of the component whose drawing shows it: the terminal itself,
    or past a splice the first terminal the run lands on (`+2 more`: it lands on others too; `via`: the splice)."""
    ctx, net, conds = st.ctx, st.ctx.net, st.m.conductors
    t = conds[j].end(3 - e)
    if net.role(t.device) != "splice": return short(terminal_words(ctx, t)), ctx.comp[t.device].id if t.device in ctx.comp else t.device
    seen, todo, lands = {j}, [net.node(j, 3 - e)], []
    while todo:
        for i, k in net.at[todo.pop()]:
            if i in seen: continue
            seen.add(i)
            o = conds[i].end(3 - k)
            if net.role(o.device) == "splice": todo.append(net.node(i, 3 - k))
            else: lands.append((terminal_words(ctx, o), o.device))
    lands.sort()
    via = terminal_words(ctx, t)
    if not lands: return short(via), ctx.comp[t.device].id
    first, dev = lands[0]
    return short(first + (f" +{len(lands) - 1} more" if len(lands) > 1 else "") + f" via {via}"), ctx.comp[dev].id if dev in ctx.comp else dev


def _flag(st: Any, j: int, e: int) -> SceneFlag:
    ctx, c = st.ctx, st.m.conductors[j]
    o = ctx.comp.get(c.end(3 - e).device)
    words, dwg = far_end(st, j, e)
    return SceneFlag(id=f"flag:{c.id}", model=f"conductor:{c.id}", kind="off_sheet", at=ctx.ref(c.end(e)), target=ctx.ref(c.end(3 - e)),
                     target_item=model_id(o) if o else "", text="→ " + words, drawing=dwg, label=c.label, gauge=gauge(c.gauge),
                     colour=c.colour_code or c.colour, hex=ink(c), cls=c.can or c.kind, weight=weight(c.awg))
