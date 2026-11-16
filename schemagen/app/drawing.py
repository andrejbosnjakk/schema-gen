"""The wiring drawing of a part of the project (docs/api.md, Drawing): for every pin in scope, the wires that leave it
and everything they pass through (harness connector pins, splices) down to where they land. Scope today: one component,
or the connection between two components; a harness or a subsystem is the same walk over more components.
A harness connector is drawn pin by pin with both of its halves: what arrives on one side, what leaves on the other.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import zip_longest
from typing import Any

from ..exporters.palette import HEX
from ..exporters.pinout import where
from .workspace import _natural, kind_of, severities

MAX_ROWS = 600  # a drawing is cut here (and says so); the checklist export has no limit


def _seg(st: Any, i: int, e: int, wsev: dict[str, str]) -> dict[str, Any]:
    """Conductor i walked away from its end e: the wire and where it lands."""
    ctx, c = st.ctx, st.m.conductors[i]
    o = c.end(3 - e)
    oc = ctx.comp.get(o.device)
    sim = (st.overlay or {}).get("items", {}).get(f"conductor:{c.id}")
    return dict(wire=c.id, label=c.label, name=c.name, gauge=c.gauge, colour=c.colour_code or c.colour, hex=HEX.get((c.colour_code or "")[:2], "#888"),
                sev=wsev.get(c.id, ""), reason=sim["reason"] if sim and sim["status"] != "ok" else "",
                at=where(ctx, o), comp=oc.id if oc else "", role=ctx.net.role(o.device))


def _paths(st: Any, i: int, e: int, wsev: dict[str, str], seen: frozenset[int] = frozenset()) -> list[list[dict[str, Any]]]:
    """Every run from end e of conductor i to a terminal that is not a splice or a harness pin (one list of segments each)."""
    net = st.ctx.net
    seg = _seg(st, i, e, wsev)
    if seg["role"] not in ("splice", "harness"): return [[seg]]
    nxt = [(j, k) for j, k in net.at[net.node(i, 3 - e)] if j != i and j not in seen]
    return [[seg] + p for j, k in nxt for p in _paths(st, j, k, wsev, seen | {i})] or [[seg]]


def drawing(st: Any, cid: str, to: str = "") -> dict[str, Any] | None:
    """The drawing of component `cid`; with `to`, only the runs that reach that component."""
    ctx, conds = st.ctx, st.m.conductors
    c, other = ctx.comp_by_id.get(cid), ctx.comp_by_id.get(to) if to else None
    if c is None or (to and other is None): return None
    wsev = severities(st)[1]
    keep = lambda ps: [p for p in ps if not to or any(s["comp"] == to for s in p)]  # noqa: E731  (a run through a connector goes on behind it)
    by: dict[str, dict[str, list[list[dict[str, Any]]]]] = defaultdict(lambda: defaultdict(list))  # group -> pin -> runs
    names: dict[tuple[str, str], str] = {}
    for i, e in ctx.net.by_dev[c.raw]:
        t = conds[i].end(e)
        d = ctx.pin(t)
        names[(t.connector, t.pin)] = d.name if d and d.name else ""
        by[t.connector][t.pin or t.connector] += keep(_paths(st, i, e, wsev))
    groups: list[dict[str, Any]] = []
    sides: list[str] = []
    if c.kind == "harness":  # pin by pin, one half to the left and the other to the right
        sides = sorted(by, key=_natural)[:2]
        rows = []
        for pin in sorted({p for s in sides for p in by[s]}, key=_natural):
            left, right = by[sides[0]].get(pin, []), by[sides[1]].get(pin, []) if len(sides) > 1 else []
            rows += [dict(pin=pin, pin_name="", left=a or [], right=b or []) for a, b in zip_longest(left, right)]
        groups = [dict(name="", rows=rows)]
    else:
        for con in sorted(by, key=_natural):
            rows = [dict(pin=pin, pin_name=names.get((con, pin), ""), left=[], right=p) for pin in sorted(by[con], key=_natural) for p in by[con][pin]]
            if rows: groups.append(dict(name=con, rows=rows))
    total = sum(len(g["rows"]) for g in groups)
    cut = max(0, total - MAX_ROWS)
    if cut:
        room = MAX_ROWS
        for g in groups: g["rows"], room = g["rows"][:room], max(0, room - len(g["rows"]))
        groups = [g for g in groups if g["rows"]]
    wires = {s["wire"] for g in groups for r in g["rows"] for s in r["left"] + r["right"]}
    return dict(id=c.id, name=c.name or c.id, kind=kind_of(st, c), to=dict(id=other.id, name=other.name or other.id) if other else None,
                project=st.cfg.root.name, sides=sides, groups=groups, wires=len(wires), cut=cut)
