"""Wire direction convention: which end of a conductor is "from".

Default convention (configurable under `direction:` in schemagen.yml):
- supply: source -> load (power_out -> power_in; breaker LOAD -> ..., ... -> breaker LINE);
- return / ground: device -> where it returns (ground bus, else the ground pin of the supplying unit, else a splice);
- one-way signals: sender -> receiver (signal_out -> signal_in; a switch -> the input it drives);
- no defined direction: CAN in bus order from one terminator end (the end that agrees with most conductors, or
  `direction.can_start`); bidirectional data from the controlling unit (part `controller: true`) outward.

Without pin types (no part data) the fallbacks come from `direction:` patterns (regex on the device code or name):
- `bond`: bonds to structure have no direction (also conductors of class `bond`);
- `ground_points`: where a return ends when its net has no ground bus (a stud, a ground terminal);
- `senders` / `receivers`: one-way signal ends; an entry is a device regex or {device, function} to also require a
  conductor at that end whose function text matches (a low-side lamp driver receives, a high-side one does not).
Returns are judged by where the chain ends, never by the next hop (a splice).

A conductor is flagged only when the net gives both of its ends a distance from the reference; everything else
(no pin data, loops) stays unflagged, and `unknown()` lists the signal wires left without a direction.
"""
from __future__ import annotations

import re
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


DEFAULTS: dict[str, Any] = {"bond": [r"\bbond", "structure", "airframe"], "ground_points": [r"^GND", r"\bground\b", "earth"],
                            "senders": [r"^SW-", "switch", "sensor", r"\bmic"], "receivers": [{"device": "driver", "function": r"low.?side"}]}


def _pats(opts: dict[str, Any], key: str) -> list[tuple[re.Pattern[str], re.Pattern[str] | None]]:
    out = []
    for x in opts.get(key, DEFAULTS[key]) or []:
        dev, fn = (x.get("device", "."), x.get("function")) if isinstance(x, dict) else (x, None)
        out.append((re.compile(str(dev), re.I), re.compile(str(fn), re.I) if fn else None))
    return out


def analyse(ctx: Ctx) -> list[Flip]:
    """Conductors whose from/to order breaks the convention."""
    return _judge(ctx)[0]


def unknown(ctx: Ctx) -> list[int]:
    """Signal conductors whose direction the convention cannot tell (no pin types, no sender/receiver pattern)."""
    return _judge(ctx)[1]


def _judge(ctx: Ctx) -> tuple[list[Flip], list[int]]:
    opts: dict[str, Any] = (getattr(ctx.cfg, "direction", None) or {})
    if opts.get("enabled", True) is False: return [], []
    net, conds = ctx.net, ctx.m.conductors
    bond, gpts = [p for p, _ in _pats(opts, "bond")], [p for p, _ in _pats(opts, "ground_points")]
    senders, receivers = _pats(opts, "senders"), _pats(opts, "receivers")

    def match(raw: str, pats: list[re.Pattern[str]]) -> bool:
        c = ctx.comp.get(raw)
        return any(p.search(raw) or (c is not None and p.search(c.id)) for p in pats)

    def is_bond(i: int) -> bool:
        c = conds[i]
        return "bond" in (c.cls, c.kind) or any(match(t.device, bond) for t in (c.from_, c.to))
    unk: list[int] = []
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
                if not ty and kind == "signal":  # fallback: sender / receiver patterns
                    fns = [conds[i].func for i, _ in net.at[node]]
                    for pats, name in ((senders, "signal_out"), (receivers, "signal_in")):
                        if any((dp.search(node[0]) or dp.search(ctx.comp[node[0]].id)) and (fp is None or any(fp.search(f) for f in fns))
                               for dp, fp in pats): ty = name; break
                if ty: typed[node] = ty
                owner[node] = ctx.comp[node[0]].id
        role: dict[NodeKey, str] = {node: net.role(node[0]) for node in n.nodes if len(node) == 1}
        away, why = True, ""
        starts: list[NodeKey] = []
        if kind == "GND":
            buses: list[NodeKey] = [x for x, r in role.items() if r == "bus"]
            gp = [x for x in n.nodes if len(x) == 3 and x[0] in ctx.comp and ctx.comp[x[0]].kind != "harness" and match(x[0], gpts)
                  and not any(is_bond(i) for i, _ in net.at[x])]
            sup = [x for x, ty in typed.items() if ty == "ground" and _supplies(ctx, x[0])]
            spl: list[NodeKey] = [x for x, r in role.items() if r == "splice"]
            if buses: starts, why = buses, "returns go device → ground bus"
            elif gp: starts, why = gp, "returns go device → where the chain ends (ground point)"
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
        dist = _bfs(starts, adj) if starts else {}
        for i in n.conductors:
            if is_bond(i): continue
            da, db = dist.get(net.node(i, 1)), dist.get(net.node(i, 2))
            if da is None or db is None or da == db:
                if conds[i].kind == "signal": unk.append(i)
                continue
            if (da > db) if away else (da < db):
                out.append(Flip(i, conds[i].id, conds[i].label, why))
    return sorted(out, key=lambda f: f.index), sorted(unk)


def _supplies(ctx: Ctx, raw: str) -> bool:
    p = ctx.part_of(raw)
    return bool(p and any(pin.type == "power_out" for c in p.connectors for pin in c.pins))


def _controller(ctx: Ctx, raw: str, names: set[str]) -> bool:
    c, p = ctx.comp.get(raw), ctx.part_of(raw)
    return bool((c and c.id in names) or (p and p.controller))
