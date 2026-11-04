"""Wire direction convention: which end of a conductor is "from".

Default convention (configurable under `direction:` in schemagen.yml):
- supply: source -> load (power_out -> power_in; breaker LOAD -> ..., ... -> breaker LINE);
- return / ground: device -> where it returns (ground bus, else the ground pin of the supplying unit, else a splice);
- one-way signals: sender -> receiver (signal_out -> signal_in; a switch -> the input it drives);
- no defined direction: CAN in bus order from one terminator end (the end that agrees with most conductors, or
  `direction.can_start`); bidirectional data from the controlling unit (part `controller: true`) outward.

A conductor is flagged only when the net gives both of its ends a distance from the reference; everything else
(no pin data, loops) stays unflagged.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from .context import Ctx
from .model import Terminal
from .net import NodeKey


@dataclass
class Flip:
    index: int
    id: str
    label: str
    reason: str


def _bfs(starts: list[NodeKey], adj: dict[NodeKey, list[NodeKey]]) -> dict[NodeKey, int]:
    d: dict[NodeKey, int] = {}
    q: deque[NodeKey] = deque()
    for s in starts:
        if s not in d: d[s] = 0; q.append(s)
    while q:
        n = q.popleft()
        for x in adj.get(n, []):
            if x not in d: d[x] = d[n] + 1; q.append(x)
    return d


def analyse(ctx: Ctx) -> list[Flip]:
    """Conductors whose from/to order breaks the convention."""
    opts: dict[str, Any] = (getattr(ctx.cfg, "direction", None) or {})
    if opts.get("enabled", True) is False: return []
    net, conds = ctx.net, ctx.m.conductors
    controllers = set(opts.get("controllers", []))
    can_start = opts.get("can_start", {}) or {}
    out: list[Flip] = []
    term_nodes = {b.net_id: b.terminators for b in ctx.can_buses}
    for n in net.nets():
        kind = ctx.net_kind(n.conductors)
        adj: dict[NodeKey, list[NodeKey]] = {}
        for i in n.conductors:
            a, b = net.node(i, 1), net.node(i, 2)
            adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
        typed: dict[NodeKey, str] = {}
        owner: dict[NodeKey, str] = {}
        for node in n.nodes:
            if len(node) == 3 and node[0] in ctx.comp and ctx.comp[node[0]].kind != "harness":
                t = Terminal(device=node[0], connector=node[1], pin=node[2])
                ty = ctx.pin_type(t)
                if ty: typed[node] = ty
                owner[node] = ctx.comp[node[0]].id
        role: dict[NodeKey, str] = {node: net.role(node[0]) for node in n.nodes if len(node) == 1}
        away, why = True, ""
        starts: list[NodeKey] = []
        if kind == "GND":
            buses: list[NodeKey] = [x for x, r in role.items() if r == "bus"]
            sup = [x for x, ty in typed.items() if ty == "ground" and _supplies(ctx, x[0])]
            spl: list[NodeKey] = [x for x, r in role.items() if r == "splice"]
            if buses: starts, why = buses, "returns go device → ground bus"
            elif sup: starts, why = sup, "returns go device → the supplying unit's ground pin"
            else: starts, why = spl, "returns go device → splice"
            away = False
        elif kind == "CAN":
            ts = [x for x in term_nodes.get(n.id, []) if x in adj]
            if len(ts) >= 2:
                cands = sorted(ts, key=lambda x: owner.get(x, ""))
                start = next((x for x in cands if owner.get(x) == can_start.get(n.id) or owner.get(x) in can_start.values()), None)
                if start is None:  # the terminator end most conductors already agree with
                    def score(s: NodeKey) -> int:
                        d = _bfs([s], adj)
                        return sum(1 for i in n.conductors if d.get(net.node(i, 1), -1) < d.get(net.node(i, 2), -1))
                    start = max(cands, key=score)
                starts, why = [start], f"CAN in bus order from terminator {owner.get(start, start[0])}"
            else:
                starts = [x for x in typed if _controller(ctx, x[0], controllers)]
                why = "bidirectional bus from the controlling unit outward"
        elif kind == "signal":
            send = [x for x, ty in typed.items() if ty == "signal_out"]
            recv = [x for x, ty in typed.items() if ty == "signal_in"]
            if send: starts, why = send, "signals go sender → receiver"
            elif recv: starts, why, away = recv, "signals go sender → receiver", False
            else: starts, why = [x for x in typed if _controller(ctx, x[0], controllers)], "from the controlling unit outward"
        else:
            src = [x for x, ty in typed.items() if ty == "power_out"]
            snk = [x for x, ty in typed.items() if ty == "power_in"]
            if src: starts, why = src, "supply goes source → load"
            else: starts, why, away = snk, "supply goes source → load", False
        if not starts: continue
        dist = _bfs(starts, adj)
        for i in n.conductors:
            da, db = dist.get(net.node(i, 1)), dist.get(net.node(i, 2))
            if da is None or db is None or da == db: continue
            if (da > db) if away else (da < db):
                out.append(Flip(i, conds[i].id, conds[i].label, why))
    return sorted(out, key=lambda f: f.index)


def _supplies(ctx: Ctx, raw: str) -> bool:
    p = ctx.part_of(raw)
    return bool(p and any(pin.type == "power_out" for c in p.connectors for pin in c.pins))


def _controller(ctx: Ctx, raw: str, names: set[str]) -> bool:
    c, p = ctx.comp.get(raw), ctx.part_of(raw)
    return bool((c and c.id in names) or (p and p.controller))
