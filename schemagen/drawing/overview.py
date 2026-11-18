"""The overview: ONE sheet with the whole LV system, every conductor drawn exactly once (the "P&ID" view; contract in docs/drawing-model.md).

blocks    the power side (sources, breakers, fuses, switches, relays' contacts, buses) is one block, the ladder: it is the first column, at the top. Every
          controller (a device with CONTROLLER or more wires) is a block with its peripherals (the devices it shares most wires with, through splices
          and harness connectors) and the splices between them. Devices that belong to no controller, and harness connectors, are single nodes.
inside    a block is laid out on its own (columns by distance from its entry, rows by barycentre sweeps, tracks in the channels); a wire that leaves
          the block ends in a port on its frame.
outside   blocks, harness connectors and loose devices are laid out the same way as nodes with the ports as anchors, power flowing left to right;
          a wire that passes columns rides a lane (a dummy node) through each. The sheet is as big as the content needs (it may exceed A0).
symbols   devices: the used pins; splices: junction dots (bars with a dot per wire); buses: rails; in-line parts and harness connectors: the existing
          symbols; a relay's coil is its own symbol; ground: a mark per wire right of its pin (no routed ground bus); CAN wires are dashed.
Deterministic: stable sorts, no randomness."""
from __future__ import annotations

import heapq
from bisect import bisect_left
from collections import Counter, defaultdict, deque
from typing import Any

from ..app.workspace import _natural
from . import route as R
from . import symbols as S
from .geometry import Anchor, Geometry
from .scope import scene
from .style import GRID, MARGIN, PAD, SIZE, STRIP_H, ceil_to, text_w

BARS = ("splice", "bus")
ROWWISE = ("block", "harness", "dcdc")
LADDER = ("battery", "dcdc", "bus")
INLINE = ("breaker", "fuse", "switch", "relay")
RANK = {"battery": 0, "dcdc": 1, "breaker": 1, "fuse": 1, "switch": 1, "relay": 1, "bus": 2, "splice": 3, "harness": 3, "coil": 4, "terminator": 4, "block": 5}
CONTROLLER = 10            # a device with this many wires or more is a controller: a block of its own
TOP = 10.0                 # room for a block's caption above its frame content
Elem = dict[str, Any]
Edge = tuple[Elem, str, str, str, str, str, str]    # (wire piece, node u, key at u, pin ref at u, node v, key at v, pin ref at v)


class Node:
    """A symbol, a ground mark, a port, a block or a lane (dummy) in a column; `off` maps an end key to its anchor's offset from the top left."""

    def __init__(s, id: str, kind: str, item: Elem | None = None, w: float = 0.0, h: float = 0.0) -> None:
        s.id, s.kind, s.item, s.w, s.h = id, kind, item, w, h
        s.col, s.x, s.y = 0, 0.0, 0.0
        s.off: dict[str, tuple[float, float]] = {}
        s.act: dict[str, str] = {}                     # the side each anchor really has in the symbol
        s.ends: list[tuple[str, str, str, str]] = []   # (end key, side wanted, wire id, pin ref)
        s.req: dict[str, str] = {}
        s.item2: Elem | None = None
        s.fan: dict[str, list[str]] = {}
        s.taps: list[Elem] | None = None

    def at(s, key: str) -> float:
        return s.y + s.off[key][1]

    @property
    def sym(s) -> str:
        return s.item["symbol"] if s.item else ""


def _trim(it: Elem) -> Elem:
    """The item with the used pins only and no part numbers; a harness connector keeps both halves' rows for every pin number in use."""
    if it["symbol"] == "harness":
        used = {p["n"] for b in it["blocks"] for p in b["pins"] if not p["spare"]}
        bl = [dict(b, part="", mate="", pins=[p for p in b["pins"] if p["n"] in used]) for b in it["blocks"]]
    else: bl = [b for b in (dict(b, part="", mate="", pins=[p for p in b["pins"] if not p["spare"]]) for b in it["blocks"]) if b["pins"]]
    return dict(it, part="", location="", blocks=bl, **({"code": ""} if it["symbol"] == "splice" else {}))   # a splice is a bare junction dot: no label


def _split_relay(it: Elem) -> list[Elem]:
    """A relay as its contacts (the relay symbol without a coil) and its coil, its own item `<id>:coil` with the coil's terminals; a part with no
    contacts wired is its coil alone."""
    coil = it["attrs"].get("coil")
    if not coil: return [it]
    refs = {coil["a1"], coil["a2"]}
    pick = lambda keep: [b for b in (dict(b, pins=[p for p in b["pins"] if (p["anchor"] in refs) == keep]) for b in it["blocks"]) if b["pins"]]  # noqa: E731
    out = []
    if pick(False): out.append(dict(it, blocks=pick(False), attrs=dict(it["attrs"], coil=None)))
    if pick(True): out.append(dict(it, id=it["id"] + ":coil", symbol="coil", blocks=pick(True), attrs={}))
    return out


def _coil(it: Elem, x: float, y: float, sides: dict[str, str]) -> tuple[Elem, list[Any]]:
    """A relay's coil: a small box between its two terminals (first L, other R unless `sides` says otherwise) with the relay's name under it."""
    ps = [p for b in it["blocks"] for p in b["pins"]][:2]
    title, _ = S._head(it)
    B = S._B(it, x, y)
    W = ceil_to(max(20.0, S._tw(title + " coil", "name") + 2))
    s = [sides.get(p["anchor"], "L" if i == 0 else "R") for i, p in enumerate(ps)]
    if len(s) == 2 and s[0] == s[1]: s[1] = "R" if s[0] == "L" else "L"
    B.rect(5, 2.5, W - 10, 5, S.N, "white")
    B.line(0, 5, 5, 5); B.line(W - 5, 5, W, 5)
    for p, sd in zip(ps, s): B.anchor(p["anchor"], 0 if sd == "L" else W, 5, sd)
    B.text(title + " coil", W / 2, 11, "centre", "name")
    return dict(id=it["id"], kind="coil", model=it["model"], x=x, y=y, w=W, h=15.0, anchors=B.anchors, prims=B.prims), B.texts


def _ground_mark(x: float, y: float, wid: str, ref: str, side: str = "L") -> Elem:
    """A ground mark lying on its side at (x, y): lead, then three bars (10 x 10 mm); its anchor takes the wire from `side` (L: the mark is right of the pin)."""
    m = (lambda d: d) if side == "L" else (lambda d: 10 - d)
    ln = lambda x1, y1, x2, y2: dict(kind="line", stroke="normal", x1=x + m(x1), y1=y + y1, x2=x + m(x2), y2=y + y2)  # noqa: E731
    pr = [ln(0, 5, 3, 5)] + [ln(dx, 5 - h, dx, 5 + h) for dx, h in ((3, 2.5), (5, 1.5), (7, 0.5))]
    return dict(id=f"ground:{wid}", kind="ground", model=ref, x=x, y=y, w=10.0, h=10.0, anchors=[dict(id=f"{ref}#{wid}", model=ref, x=x + m(0), y=y + 5, side=side)], prims=pr)  # noqa: E501


def _cross(hs: list[tuple[float, float]]) -> int:
    """Crossings among the hops (y left, y right) of one channel: pairs whose order at the left differs from the order at the right."""
    hs = sorted(hs)
    ys = sorted({b for _, b in hs})
    tree = [0] * (len(ys) + 1)
    n = 0
    for k, (_, b) in enumerate(hs):
        i = bisect_left(ys, b) + 1
        j, below = i, 0
        while j: below += tree[j]; j -= j & -j
        n += k - below                                   # earlier hops that end lower (a larger y) than this one
        while i <= len(ys): tree[i] += 1; i += i & -i
    return n


class Env:
    """What building symbols needs: how many wire ends each pin has and which in-line parts are mirrored."""

    def __init__(s, cnt: dict[str, int]) -> None:
        s.cnt = cnt
        s.flip: dict[str, bool] = {}

    def key_at(s, n: Node, ref: str, wid: str) -> str:
        """The key of a wire's end: the pin ref, or ref#id where the symbol has an anchor per wire (bars, ground marks, shared pins)."""
        return f"{ref}#{wid}" if n.kind == "gnd" or n.sym in BARS or s.cnt[ref] > 1 else ref

    def defaults(s, it: Elem) -> dict[str, str]:
        sy = _coil(it, 0, 0, {})[0] if it["symbol"] == "coil" else S.build(it, 0, 0)[0]
        return {a["id"]: a["side"] for a in sy["anchors"]}

    def build(s, n: Node, pos: dict[str, float]) -> None:
        """Sizes the item's symbol from the sides its ends want: rows or anchors per wire where several wires share a pin, taps on bars."""
        it = n.item
        assert it is not None
        sd: dict[str, str] = {}
        rowwise = it["symbol"] in ROWWISE
        for k, s_, _, ref in n.ends: sd.setdefault(k if rowwise or it["symbol"] in BARS else ref, s_)
        multi: dict[str, list[str]] = defaultdict(list)
        for k, _, wid, ref in sorted(n.ends, key=lambda e: _natural(e[2])):
            if k != ref and it["symbol"] not in BARS: multi[ref].append(k)
        n.item2, n.fan = None, {}
        if multi and rowwise:   # one row per wire at a shared pin
            n.item2 = dict(it, blocks=[dict(b, pins=[q for p in b["pins"] for q in ([dict(p, anchor=k) for k in multi[p["anchor"]]] if p["anchor"] in multi else [p])]) for b in it["blocks"]])  # noqa: E501
        elif multi: n.fan = multi
        if it["symbol"] == "harness" and len(it["blocks"]) == 2:
            for i, b in enumerate(it["blocks"]):
                for p in b["pins"]:
                    for k in multi.get(p["anchor"], [p["anchor"]]): sd[k] = "L" if (i == 0) != s.flip.get(n.id, False) else "R"
        n.req = sd
        n.taps = None
        if it["symbol"] in BARS:   # an anchor per wire, in the order of the far ends
            pins = {p["anchor"]: p for b in it["blocks"] for p in b["pins"]}
            n.taps = []
            for s_ in "LR":
                for k, _, wid, ref in sorted((e for e in n.ends if e[1] == s_), key=lambda e: (pos.get(e[0], 0.0), _natural(e[2]))):
                    p = pins.get(ref, {})
                    n.taps.append(dict(id=k, model=ref, side=s_, text=p.get("n") or ("" if len(pins) < 2 else p.get("name", ""))))
        sy, _ = s.symfor(n, 0, 0)
        n.w, n.h = sy["w"], sy["h"]
        n.off = {a["id"]: (a["x"], a["y"]) for a in sy["anchors"]}
        n.act = {a["id"]: a["side"] for a in sy["anchors"]}

    def symfor(s, n: Node, x: float, y: float) -> tuple[Any, list[Any]]:
        """The node's symbol at (x, y), models back to the pin refs."""
        it = n.item2 or n.item
        assert it is not None
        sy, tx = _coil(it, x, y, n.req) if it["symbol"] == "coil" else S.build(it, x, y, n.req, n.taps)  # type: ignore[arg-type]
        for ref, ks in n.fan.items():
            a = next(a for a in sy["anchors"] if a["id"] == ref)
            sy["anchors"] = [b for b in sy["anchors"] if b is not a] + [Anchor(id=k, model=a["model"], x=a["x"], y=a["y"] + GRID * i, side=a["side"]) for i, k in enumerate(ks)]  # noqa: E501
            sy["prims"] += [dict(kind="line", stroke="normal", x1=a["x"], y1=a["y"], x2=a["x"], y2=a["y"] + GRID * (len(ks) - 1))]  # type: ignore[list-item]
            sy["prims"] += [dict(kind="circle", stroke="normal", fill="black", cx=a["x"], cy=a["y"] + GRID * i, r=0.9) for i in range(len(ks))]  # type: ignore[misc]
            sy["h"] = max(sy["h"], ceil_to(a["y"] - y + GRID * (len(ks) - 1) + 2.5))
        back = {k: ref for ref, ks in n.fan.items() for k in ks}
        back |= {e[0]: e[3] for e in n.ends}
        for a in sy["anchors"]: a["model"] = back.get(a["model"], a["model"])
        for t in tx: t["model"] = back.get(t["model"], t["model"])
        return sy, tx


def columns(env: Env, nodes: dict[str, Node], edges: list[Edge], seeds: list[str]) -> None:
    """Sets `col` of every node and the sides of the items' ends. Levels: distance from the seeds over the edges; the sides wanted at an end: towards the
    lower node on the left; in-line parts and harness connectors are mirrored so that the terminals facing the lower neighbours are on the left; columns:
    longest path over the edges oriented by those sides (else by level); ports sit in the first or last column; at the end blocks and bars face the
    columns their wires go to."""
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)     # node -> (other node, own pin ref)
    other: dict[tuple[str, str], str] = {}
    for el, u, ku, ru, v, kv, rv in edges:
        adj[u].append((v, ru)); adj[v].append((u, rv))
        other[el["wid"], u] = v; other[el["wid"], v] = u
    real = sorted(i for i, n in nodes.items() if n.kind in ("item", "macro"))
    lvl: dict[str, int] = {}
    todo: deque[str] = deque(s for s in seeds if s in nodes)
    for q0 in todo: lvl[q0] = 0
    for start in [None, *real]:
        if start is not None:
            if start in lvl: continue
            lvl[start] = 0; todo.append(start)
        while todo:
            u = todo.popleft()
            for v, _ in sorted(adj[u]):
                if v not in lvl and nodes[v].kind in ("item", "macro"): lvl[v] = lvl[u] + 1; todo.append(v)
    for g, nd in nodes.items():
        if nd.kind in ("gnd", "port"):
            nb = adj[g][0][0] if adj[g] else g
            lvl[g] = lvl.get(nb, 0) + (1 if nd.kind == "gnd" or nd.act.get("p") == "L" else -1)
    kk = lambda n: (lvl[n], RANK.get(nodes[n].sym, 2 if nodes[n].kind == "macro" else 6), _natural(n))  # noqa: E731
    for el, u, ku, ru, v, kv, rv in edges:
        for me, o, key, ref in ((u, v, ku, ru), (v, u, kv, rv)):
            if nodes[me].kind in ("item", "gnd"): nodes[me].ends.append((key, "L" if kk(o) < kk(me) else "R", el["wid"], ref))
    for iid in real:     # an in-line part or harness connector: the group of terminals facing the lower neighbours goes left
        n = nodes[iid]
        if n.kind != "item" or n.sym in ("block", *BARS): continue
        defs = env.defaults(n.item)  # type: ignore[arg-type]
        grp = {p["anchor"]: (i if n.sym == "harness" else int(defs.get(p["anchor"], "L") == "R")) for i, b in enumerate(n.item["blocks"]) for p in b["pins"]}  # type: ignore[index]  # noqa: E501
        score: dict[int, list[int]] = defaultdict(list)
        for o, own in adj[iid]:
            if own in grp: score[grp[own]].append(lvl[o])
        m0, m1 = (sum(score[g]) / len(score[g]) if score[g] else None for g in (0, 1))
        env.flip[iid] = m0 is not None and ((m1 is not None and m0 > m1) or (m1 is None and m0 > lvl[iid]))
        f = env.flip[iid]
        n.ends = [(k, ("R" if f else "L") if grp[ref] == 0 else ("L" if f else "R"), wid, ref) if ref in grp else (k, s_, wid, ref) for k, s_, wid, ref in n.ends]
    for n in nodes.values():
        if n.kind == "item": env.build(n, {})
    for el, u, ku, ru, v, kv, rv in edges:   # a ground mark goes to the side its in-line part's terminal faces
        for g, o, kg, ko in ((u, v, ku, kv), (v, u, kv, ku)):
            if nodes[g].kind == "gnd" and nodes[o].kind == "item" and nodes[o].sym not in ("block", *BARS) and nodes[o].act.get(ko) == "L":
                nodes[g].act, nodes[g].off = {kg: "R"}, {kg: (10.0, 5.0)}
    fixed = lambda n: n.kind in ("gnd", "port") or (n.kind == "item" and n.sym not in ("block", *BARS))  # noqa: E731
    succ: dict[str, set[str]] = defaultdict(set)
    for el, u, ku, ru, v, kv, rv in edges:
        su = nodes[u].act.get(ku, "") if fixed(nodes[u]) else ""
        sv = nodes[v].act.get(kv, "") if fixed(nodes[v]) else ""
        lo, hi = (u, v) if su == "R" or sv == "L" else (v, u) if su == "L" or sv == "R" else (u, v) if kk(u) < kk(v) else (v, u)
        succ[lo].add(hi)
    indeg = dict.fromkeys(nodes, 0)
    for u in succ:
        for v in succ[u]: indeg[v] += 1
    for n in nodes.values(): n.col = 0
    ready = [(kk(n), n) for n in nodes if not indeg[n]]
    heapq.heapify(ready)
    done: set[str] = set()
    while len(done) < len(nodes):
        if not ready: heapq.heappush(ready, min((kk(n), n) for n in nodes if n not in done))   # a cycle: start at its smallest
        _, u = heapq.heappop(ready)
        if u in done: continue
        done.add(u)
        for v in sorted(succ[u], key=kk):
            if v in done: continue
            nodes[v].col = max(nodes[v].col, nodes[u].col + 1); indeg[v] -= 1
            if not indeg[v]: heapq.heappush(ready, (kk(v), v))
    last = max((n.col for n in nodes.values() if n.kind != "port"), default=0) + 1
    for n in nodes.values():
        if n.kind == "port": n.col = last if n.act.get("p") == "L" else 0
    for n in nodes.values():                             # blocks and bars face the columns their wires go to
        if n.kind == "item" and n.sym in ("block", *BARS):
            n.ends = [(k, "R" if nodes[other.get((wid, n.id), n.id)].col > n.col or other.get((wid, n.id), n.id) == n.id else "L", wid, ref) for k, _, wid, ref in n.ends]  # noqa: E501
            env.build(n, {})


def solve(env: Env, nodes: dict[str, Node], edges: list[Edge], pin: str = "") -> tuple[float, float, dict[str, list[list[float]]], int]:
    """Rows, channels and wires of one container whose nodes have their columns: positions (relative to its top left, set on the nodes), its size, the points of
    every edge's wire (from its first node to its second) and the number of crossings."""
    for k in [k for k, n in nodes.items() if n.kind == "dummy"]: del nodes[k]      # lanes of an earlier run
    paths: list[tuple[Elem, list[Node], str, str, bool]] = []     # (piece, nodes from the left, key at the first, key at the last, reversed)
    for el, u, ku, ru, v, kv, rv in edges:
        rev = nodes[u].col > nodes[v].col or (nodes[u].col == nodes[v].col and u > v)
        pr = [nodes[v], nodes[u]] if rev else [nodes[u], nodes[v]]
        paths.append((el, pr, kv if rev else ku, ku if rev else kv, rev))
    for pi, (el, ns, k0, k1, rev) in enumerate(paths):
        if ns[1].col - ns[0].col > 1:
            mid = [Node(f"~{el['id']}~{c}", "dummy", None, 0.0, GRID) for c in range(ns[0].col + 1, ns[1].col)]
            for d in mid: d.col = int(d.id.rsplit("~", 1)[1]); d.off = {"~": (0.0, GRID)}; nodes[d.id] = d
            paths[pi] = (el, [ns[0], *mid, ns[1]], k0, k1, rev)
    cols: dict[int, list[Node]] = defaultdict(list)
    for n in sorted(nodes.values(), key=lambda n: (n.kind != "item", _natural(n.id))): cols[n.col].append(n)
    ncol = max(cols, default=0) + 1
    nb: dict[str, list[tuple[str, Node, str]]] = defaultdict(list)    # per node: (key here, other node, key there)
    hopkeys = lambda ns, k0, k1, i: (k0 if i == 0 else "~", k1 if i == len(ns) - 2 else "~")  # noqa: E731
    for el, ns, k0, k1, rev in paths:
        for i in range(len(ns) - 1):
            ka, kb = hopkeys(ns, k0, k1, i)
            nb[ns[i].id].append((ka, ns[i + 1], kb)); nb[ns[i + 1].id].append((kb, ns[i], ka))
    ypos: dict[str, float] = {}

    def want(n: Node, toward: int) -> float | None:
        """Row the node would like: the mean of where its wires' other ends are, less its own anchor offsets (toward: the side to prefer)."""
        ref = [(ka, m, kb) for ka, m, kb in nb[n.id] if m.id in ypos and (m.col - n.col) * toward > 0] or [(ka, m, kb) for ka, m, kb in nb[n.id] if m.id in ypos]
        return sum(ypos[m.id] + m.off[kb][1] - n.off[ka][1] for ka, m, kb in ref) / len(ref) if ref else None

    def stack(ns: list[Node], wants: list[float | None]) -> None:
        """Rows with the least total displacement from `wants` that keep the order and the gaps (pool adjacent violators), on the grid."""
        cum, c = [], 0.0
        for i, n in enumerate(ns):
            cum.append(c)
            c += n.h + (0.0 if n.kind == "dummy" and i + 1 < len(ns) and ns[i + 1].kind == "dummy" else GRID)
        pools: list[list[float]] = []
        for i, n in enumerate(ns):
            w = wants[i] if wants[i] is not None else ypos.get(n.id, cum[i])
            pools.append([w - cum[i], 1.0, i])  # type: ignore[operator]
            while len(pools) > 1 and pools[-2][0] / pools[-2][1] > pools[-1][0] / pools[-1][1]:
                b = pools.pop(); pools[-1][0] += b[0]; pools[-1][1] += b[1]
        for k, p in enumerate(pools):
            base = round(p[0] / p[1] / GRID) * GRID
            for i in range(int(p[2]), int(pools[k + 1][2]) if k + 1 < len(pools) else len(ns)): ypos[ns[i].id] = base + cum[i]

    def hops_of(c: int) -> list[tuple[str, float, float]]:
        return [(el["id"], ns[i].at(hopkeys(ns, k0, k1, i)[0]), ns[i + 1].at(hopkeys(ns, k0, k1, i)[1])) for el, ns, k0, k1, rev in paths for i in range(len(ns) - 1) if ns[i].col == c]  # noqa: E501

    def crossings() -> int:
        for n in nodes.values(): n.y = ypos[n.id]
        return sum(_cross([(a, b) for _, a, b in hops_of(c)]) for c in range(ncol - 1))

    def settle(c: int, toward: int, reorder: bool) -> None:
        ns = cols[c]
        for n in ns:
            if n.sym in BARS and any(m.id in ypos for _, m, _ in nb[n.id]):
                env.build(n, {ka: ypos[m.id] + m.off[kb][1] for ka, m, kb in nb[n.id] if m.id in ypos})
        ws = [want(n, toward) for n in ns]
        if reorder:
            order = sorted(range(len(ns)), key=lambda i: (ws[i] is None, ws[i] if ws[i] is not None else ypos.get(ns[i].id, 0.0), ns[i].kind != "item", _natural(ns[i].id)))  # noqa: E501
            ns[:] = [ns[i] for i in order]; ws = [ws[i] for i in order]
        stack(ns, ws)
    live = [n for n in nodes.values() if n.kind in ("item", "macro")] or list(nodes.values())
    if not live: return 0.0, 0.0, {}, 0
    c0 = max(live, key=lambda n: (len(nb[n.id]), -n.col)).col
    for npass in range(2):                               # outwards from the busiest column: the first pass orders, the second refines
        for c in [c0] + [c for d in range(1, ncol) for c in (c0 + d, c0 - d) if 0 <= c < ncol]:
            settle(c, 0 if c == c0 else -1 if c > c0 else 1, npass == 0 and c != c0)
    best = (crossings(), {c: list(v) for c, v in cols.items()}, dict(ypos))
    for _ in range(6):                                   # barycentre sweeps to the right and to the left; keep the fewest crossings
        for seq in (range(1, ncol), range(ncol - 2, -1, -1)):
            for c in seq: settle(c, -1 if seq.step > 0 else 1, True)
            x = crossings()
            if x < best[0]: best = (x, {c: list(v) for c, v in cols.items()}, dict(ypos))
    for cc, vv in best[1].items(): cols[cc][:] = vv
    ypos.update(best[2])
    if pin and len(cols[nodes[pin].col]) == 1: ypos[pin] = min(ypos.values())      # a node alone in its column goes to the top
    for n in nodes.values():
        if n.sym in BARS: env.build(n, {ka: ypos[m.id] + m.off[kb][1] for ka, m, kb in nb[n.id]})
    for n in nodes.values(): n.y = ypos[n.id]
    tr: dict[tuple[int, str], int] = {}
    dog: dict[tuple[int, str], float] = {}
    room, ntr = [0.0] * (ncol - 1), [0] * (ncol - 1)
    ncross = 0
    for c in range(ncol - 1):
        hs = hops_of(c)
        ncross += _cross([(a, b) for _, a, b in hs])
        t, dg, _ = R.tracks(hs)
        tr |= {(c, k): v for k, v in t.items()}; dog |= {(c, k): v for k, v in dg.items()}
        ntr[c] = max(t.values(), default=-1) + 1
        room[c] = max([text_w(R.label_text(el), SIZE) + 5 for el, ns, *_ in paths if ns[0].col == c], default=0.0)
    chw = [max(10.0, ceil_to(room[c]) + GRID * ntr[c]) for c in range(ncol - 1)]
    colw = [ceil_to(max((n.w for n in cols[c]), default=0.0)) for c in range(ncol)]
    cx = [0.0]
    for c in range(ncol - 1): cx.append(cx[-1] + colw[c] + chw[c])
    top = min(n.y for n in nodes.values())
    H = max(n.y + n.h for n in nodes.values()) - top
    for n in nodes.values(): n.x, n.y = cx[n.col], n.y - top
    out: dict[str, list[list[float]]] = {}
    for el, ns, k0, k1, rev in paths:
        pts = [(ns[0].x + ns[0].off[k0][0], ns[0].at(k0))]
        for i in range(len(ns) - 1):
            a, b = ns[i], ns[i + 1]
            ka, kb = hopkeys(ns, k0, k1, i)
            xt = lambda t: cx[a.col] + colw[a.col] + ceil_to(room[a.col]) + GRID * t  # noqa: E731
            if (a.col, el["id"]) in dog:
                ym = dog[(a.col, el["id"])] - top
                x1, x2 = xt(tr[(a.col, el["id"] + "|1")]), xt(tr[(a.col, el["id"] + "|2")])
                pts += [(x1, a.at(ka)), (x1, ym), (x2, ym), (x2, b.at(kb))]
            elif (a.col, el["id"]) in tr:
                pts += [(xt(tr[(a.col, el["id"])]), a.at(ka)), (xt(tr[(a.col, el["id"])]), b.at(kb))]
            pts.append((b.x + b.off[kb][0], b.at(kb)) if i == len(ns) - 2 else (cx[b.col] + colw[b.col], b.at(kb)))
        p = R.trace(pts)
        out[el["id"]] = p[::-1] if rev else p
    return cx[-1] + colw[-1], H, out, ncross


def _assign(its: dict[str, Elem], nbr: dict[str, list[tuple[str, str]]], deg: Counter[str]) -> tuple[dict[str, str], dict[str, str]]:
    """The block every item belongs to ("" = a node of the top level) and the name of every block. Power side: one block. Controllers (CONTROLLER wires or
    more): a block each. A device joins the controller it shares most wires with, looking through splices and harness connectors, else the block of the
    peripheral it shares most with; a splice, terminator or coil joins the block most of its neighbours are in (ties: the smallest block name)."""
    home: dict[str, str] = {}
    names = {"cl:power": "Power"}
    for i, it in its.items():
        if it["symbol"] in LADDER: home[i] = "cl:power"
        elif it["symbol"] == "block" and deg[i] >= CONTROLLER: home[i] = "cl:" + i; names["cl:" + i] = it["name"] or it["code"]
    transp = {i for i, it in its.items() if it["symbol"] in ("splice", "harness")}

    def reach(d: str, nx: str, w: str) -> set[str]:
        seen, out, stack = {w}, set(), [nx]
        while stack:
            x = stack.pop()
            if x not in transp: out.add(x); continue
            for y, w2 in nbr[x]:
                if w2 not in seen: seen.add(w2); stack.append(y)
        return out - {d}
    for rnd in range(4):
        for d in sorted(i for i, it in its.items() if it["symbol"] == "block" and i not in home):
            score: Counter[str] = Counter(home[t] for y, w in nbr[d] for t in reach(d, y, w) if t in home and home[t] != "cl:power")
            if score: home[d] = min(score, key=lambda c: (-score[c], c))
        for s in sorted(i for i, it in its.items() if it["symbol"] in ("splice", "harness", "terminator", "coil", *INLINE) and i not in home):
            score = Counter(home[y] for y, _ in nbr[s] if y in home and home[y] != "cl:power")
            if score: home[s] = min(score, key=lambda c: (-score[c], c))
    for s in sorted(i for i, it in its.items() if it["symbol"] in INLINE and i not in home): home[s] = "cl:power"
    return home, names


def draw(st: Any, meta: dict[str, str] | None = None) -> Geometry:
    """The overview of the whole project as one sheet of the size the content needs. meta: revision, date, drawn_by, source (as engine.draw)."""
    sc: Any = scene(st, "system")
    meta = dict(meta or {})
    its: dict[str, Elem] = {}
    for i in sc["items"]:
        if i["symbol"] != "ground":
            for part in _split_relay(_trim(i)): its[part["id"]] = part
    gnd = {i["id"] for i in sc["items"] if i["symbol"] == "ground"}
    owner = {p["anchor"]: iid for iid, i in its.items() for b in i["blocks"] for p in b["pins"]} | {p["anchor"]: g["id"] for g in sc["items"] if g["id"] in gnd for b in g["blocks"] for p in b["pins"]}  # noqa: E501
    wires = [w for w in sc["wires"] if not (owner[w["a"]] in gnd and owner[w["b"]] in gnd)]
    cnt: dict[str, int] = defaultdict(int)
    nodes: dict[str, Node] = {iid: Node(iid, "item", it) for iid, it in its.items()}
    ends: list[tuple[Elem, str, str]] = []
    for w in wires:
        u, v = owner[w["a"]], owner[w["b"]]
        for e in "ab": cnt[w[e]] += 1
        if u in gnd: u = f"~g:{w['id']}:a"; nodes[u] = Node(u, "gnd", None, 10.0, 10.0)
        if v in gnd: v = f"~g:{w['id']}:b"; nodes[v] = Node(v, "gnd", None, 10.0, 10.0)
        ends.append((dict(w, wid=w["id"], dash=w["cls"].startswith("CAN")), u, v))
    env = Env(cnt)
    for w, u, v in ends:
        for nid, ref in ((u, w["a"]), (v, w["b"])):
            if nodes[nid].kind == "gnd": k = env.key_at(nodes[nid], ref, w["id"]); nodes[nid].off, nodes[nid].act = {k: (0.0, 5.0)}, {k: "L"}
    nbr: dict[str, list[tuple[str, str]]] = defaultdict(list)   # item -> (other item, wire id), ground marks left out
    deg: Counter[str] = Counter()
    for w, u, v in ends:
        deg[u] += 1; deg[v] += 1
        if u in its and v in its: nbr[u].append((v, w["id"])); nbr[v].append((u, w["id"]))
    home, names = _assign(its, nbr, deg)
    owner_of: dict[str, str] = {}                        # a ground mark -> the node at the other end of its wire
    for w, u, v in ends:
        if nodes[u].kind == "gnd": owner_of[u] = v
        if nodes[v].kind == "gnd": owner_of[v] = u
    oh = lambda n: home.get(n) or (home[owner_of[n]] if n in owner_of and owner_of[n] in home else n)  # noqa: E731  (the block of a node, else the node itself)
    # ---- the top level: blocks as nodes, then the inner layout of every block
    blocks = sorted(set(home.values()))
    macros = {b: Node(b, "macro", None) for b in blocks}
    top_nodes: dict[str, Node] = dict(macros)
    for n in nodes.values():
        if oh(n.id) == n.id: top_nodes[n.id] = n
    inner: dict[str, list[Edge]] = defaultdict(list)
    top_edges: list[Edge] = []
    ports: dict[str, list[tuple[Node, str, str]]] = defaultdict(list)    # block -> (port node, wire id, end a/b)
    pieces: dict[str, list[tuple[str, str]]] = defaultdict(list)         # wire id -> [(kind, piece id)] in order a, top, b
    for w, u, v in ends:
        hu, hv = oh(u), oh(v)
        ku, kv = env.key_at(nodes[u], w["a"], w["id"]), env.key_at(nodes[v], w["b"], w["id"])
        if hu == hv and hu in macros:
            inner[hu].append((dict(w, id=w["id"]), u, ku, w["a"], v, kv, w["b"])); pieces[w["id"]].append(("i", w["id"])); continue
        a_n, a_k, b_n, b_k = u, ku, v, kv
        if hu in macros:
            pn = Node(f"port:{w['id']}:a", "port", None, 0.0, GRID); ports[hu].append((pn, w["id"], "a"))
            inner[hu].append((dict(w, id=w["id"] + "~a"), u, ku, w["a"], pn.id, "p", "")); pieces[w["id"]].append(("a", w["id"] + "~a"))
            a_n, a_k = hu, f"{w['id']}:a"
        if hv in macros:
            pn = Node(f"port:{w['id']}:b", "port", None, 0.0, GRID); ports[hv].append((pn, w["id"], "b"))
            inner[hv].append((dict(w, id=w["id"] + "~b"), pn.id, "p", "", v, kv, w["b"]))
            b_n, b_k = hv, f"{w['id']}:b"
        top_edges.append((dict(w, id=w["id"] + "~o"), a_n, a_k, "" if hu in macros else w["a"], b_n, b_k, "" if hv in macros else w["b"]))
        pieces[w["id"]].append(("o", w["id"] + "~o"))
        if hv in macros: pieces[w["id"]].append(("b", w["id"] + "~b"))
    seeds = [b for b in blocks if b == "cl:power"]
    columns(env, top_nodes, top_edges, seeds)
    # ---- inside every block
    inside: dict[str, tuple[dict[str, Node], float, float, dict[str, list[list[float]]]]] = {}
    ncross = 0
    for b in blocks:
        mem = {n.id: n for n in nodes.values() if oh(n.id) == b}
        for pn, wid, e in ports[b]:
            oe = next(x for x in top_edges if x[0]["wid"] == wid)
            me, ot = (oe[1], oe[4]) if e == "a" else (oe[4], oe[1])
            pn.act = {"p": "L" if top_nodes[ot].col >= top_nodes[me].col else "R"}   # a port on the right: its anchor takes the wire from the left
            pn.off = {"p": (0.0, GRID)}; mem[pn.id] = pn
        ed = inner[b]
        sd = [n.id for n in mem.values() if n.kind == "item" and n.sym == "battery"] if b == "cl:power" else []
        if not sd:       # the entry of a block: what its left ports feed, else its controller
            sd = sorted({x[4] if x[1].startswith("port:") else x[1] for x in ed if (x[1].startswith("port:") and mem[x[1]].act["p"] == "R") or (x[4].startswith("port:") and mem[x[4]].act["p"] == "R")})  # noqa: E501
            sd = sd or [b[3:]]
        columns(env, mem, ed, sd)
        w_, h_, ipts, nx = solve(env, mem, ed)
        ncross += nx
        inside[b] = (mem, w_, h_ + TOP + GRID, ipts)
        m = macros[b]
        m.w, m.h = w_, h_ + TOP + GRID
        for pn, wid, e in ports[b]:
            k = f"{wid}:{e}"
            m.off[k] = (pn.x + pn.off["p"][0], pn.y + pn.off["p"][1] + TOP)
            m.act[k] = "R" if pn.act["p"] == "L" else "L"
    # the top level: loose items are sided by their columns (done in columns), blocks have their ports' sides
    pin = "cl:power" if "cl:power" in macros else ""      # the power ladder sits at the top left
    tw, th, tpts, nx = solve(env, top_nodes, top_edges, pin)
    ncross += nx
    x0, y0 = MARGIN + PAD, MARGIN + PAD
    # ---- geometry
    syms: list[Any] = []; texts: list[Any] = []; rules: list[Any] = []
    abs_of: dict[str, tuple[float, float]] = {}
    for n in top_nodes.values():
        if n.kind == "macro":
            X, Y = x0 + n.x, y0 + n.y
            rules.append(dict(kind="rect", stroke="thin", dash=True, x=X, y=Y, w=n.w, h=n.h))
            texts.append(S.text(names[n.id], X + 2.5, Y + 5, "left", "name", model=""))
            for m in inside[n.id][0].values(): abs_of[m.id] = (X, Y + TOP)
        else: abs_of[n.id] = (x0, y0)
    allnodes = {m.id: m for b in blocks for m in inside[b][0].values()} | {n.id: n for n in top_nodes.values() if n.kind != "macro"}
    for nid in sorted(allnodes):
        n = allnodes[nid]
        if n.kind not in ("item", "gnd"): continue
        ox, oy = abs_of[nid]
        if n.kind == "item":
            sy, tx = env.symfor(n, ox + n.x, oy + n.y)
            syms.append(sy); texts += tx
        else:
            k, _, wid, ref = n.ends[0]
            syms.append(_ground_mark(ox + n.x, oy + n.y, wid, ref, n.act[k]))
    pts_of: dict[str, list[list[float]]] = {}
    for b in blocks:
        X, Y = x0 + macros[b].x, y0 + macros[b].y + TOP
        for pid, p in inside[b][3].items(): pts_of[pid] = [[x + X, y + Y] for x, y in p]
    for pid, p in tpts.items(): pts_of[pid] = [[x + x0, y + y0] for x, y in p]
    out: list[Any] = []
    for w, u, v in ends:
        wp: list[list[float]] = []
        for _, pid in pieces[w["id"]]: wp += pts_of[pid]
        a_key, b_key = env.key_at(nodes[u], w["a"], w["id"]), env.key_at(nodes[v], w["b"], w["id"])
        out.append(dict(id=w["id"], model=w["model"], label=w["label"], gauge=w["gauge"], colour=w["colour"], hex=w["hex"], weight=w["weight"], points=R.trace([(x, y) for x, y in wp]),  # noqa: E501
                        a=a_key, b=b_key, pair=w["pair"], shield=w["shield"], fault=w["fault"], dash=w["dash"]))
    texts += R.labels(dict(symbols=syms, wires=out, texts=texts, flags=[]))
    # ---- the sheet: as big as the content needs, in the standard frame
    W = max(330.0, ceil_to(tw + 2 * (MARGIN + PAD)))
    H = ceil_to(th + 2 * (MARGIN + PAD) + STRIP_H)
    size = f"{W:g}x{H:g}"
    info = dict(title=f"{sc['title']} overview", scope="overview", project=sc["project"], revision=meta.get("revision", ""), date=meta.get("date", ""),
                drawn_by=meta.get("drawn_by", ""), source=meta.get("source", ""))
    notes = [f"{len(out)} wires, each drawn once with label, gauge (AWG) and colour code; dashed wires are CAN.", "Dashed frames are blocks: the power side, and every controller with its peripherals.",  # noqa: E501
             "A ground mark right of a pin is that wire's end on the ground bus. Power flows from left to right."]
    sheet: dict[str, Any] = dict(n=1, of=1, size=size, w_mm=W, h_mm=H, grid_mm=5.0, symbols=syms, wires=out, texts=texts, flags=[], rules=rules, table=dict(sheet=1, rows=[]))  # noqa: E501
    sheet.update(S.furniture(info, size, 1, 1, list(dict.fromkeys(s["kind"] for s in syms)), notes))
    return dict(version=1, drawing=info, sheets=[sheet])  # type: ignore[typeddict-item,return-value,list-item]
