"""The overview: ONE sheet with the whole LV system, every conductor drawn exactly once (the "P&ID" view; prototype, contract in docs/drawing-model.md).

columns   power flows left to right: a column per step of distance from the sources (batteries), found by a breadth-first walk over the wires, then pushed
          right so that every wire runs from a column to a later one (longest path); in-line parts (breaker, switch, relay, battery, DC/DC, harness
          connector) keep their two sides; a wire that passes columns rides a lane (a dummy node) through each.
rows      barycentre sweeps in both directions, stacked on the grid (as layout.py); the sweep with the fewest crossings is kept.
channels  a vertical track per wire that changes row (route.tracks).
symbols   devices: the used pins only; splices and buses: the bar symbols with a dot per wire; in-line parts and harness connectors: the existing
          symbols; ground: a small mark per wire right of its pin, no routed ground bus.
The sheet is as big as the content needs (it may exceed A0). Deterministic: stable sorts, no randomness."""
from __future__ import annotations

import heapq
from bisect import bisect_left
from collections import defaultdict, deque
from typing import Any

from ..app.workspace import _natural
from . import route as R
from . import symbols as S
from .geometry import SHEETS, Anchor, Geometry
from .scope import scene
from .style import GRID, MARGIN, PAD, SIZE, STRIP_H, ceil_to, text_w

BARS = ("splice", "bus")
ROWWISE = ("block", "harness", "dcdc")
RANK = {"battery": 0, "dcdc": 1, "breaker": 1, "fuse": 1, "switch": 1, "relay": 1, "bus": 2, "splice": 3, "harness": 3, "terminator": 4, "block": 5}
Elem = dict[str, Any]


class Node:
    """A symbol, a ground mark or a lane (dummy) in a column; `off` maps an end key to its anchor's offset from the top left."""

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


def _trim(it: Elem) -> Elem:
    """The item with the used pins only and no part numbers; a harness connector keeps both halves' rows for every pin number in use."""
    if it["symbol"] == "harness":
        used = {p["n"] for b in it["blocks"] for p in b["pins"] if not p["spare"]}
        bl = [dict(b, part="", mate="", pins=[p for p in b["pins"] if p["n"] in used]) for b in it["blocks"]]
    else: bl = [b for b in (dict(b, part="", mate="", pins=[p for p in b["pins"] if not p["spare"]]) for b in it["blocks"]) if b["pins"]]
    return dict(it, part="", location="", blocks=bl)


def _ground_mark(x: float, y: float, wid: str, ref: str) -> Elem:
    """A ground mark lying on its side at (x, y): lead, then three bars (10 x 10 mm); its anchor takes the wire from the left."""
    ln = lambda x1, y1, x2, y2: dict(kind="line", stroke="normal", x1=x + x1, y1=y + y1, x2=x + x2, y2=y + y2)  # noqa: E731
    pr = [ln(0, 5, 3, 5)] + [ln(dx, 5 - h, dx, 5 + h) for dx, h in ((3, 2.5), (5, 1.5), (7, 0.5))]
    return dict(id=f"ground:{wid}", kind="ground", model=ref, x=x, y=y, w=10.0, h=10.0, anchors=[dict(id=f"{ref}#{wid}", model=ref, x=x, y=y + 5, side="L")], prims=pr)  # noqa: E501


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


def draw(st: Any, meta: dict[str, str] | None = None) -> Geometry:
    """The overview of the whole project as one sheet of the size the content needs. meta: revision, date, drawn_by, source (as engine.draw)."""
    sc: Any = scene(st, "system")
    meta = dict(meta or {})
    its: dict[str, Elem] = {i["id"]: _trim(i) for i in sc["items"] if i["symbol"] != "ground"}
    gnd = {i["id"] for i in sc["items"] if i["symbol"] == "ground"}
    owner = {p["anchor"]: i["id"] for i in sc["items"] for b in i["blocks"] for p in b["pins"]}
    nodes: dict[str, Node] = {iid: Node(iid, "item", it) for iid, it in its.items()}
    wires = [w for w in sc["wires"] if not (owner[w["a"]] in gnd and owner[w["b"]] in gnd)]
    cnt: dict[str, int] = defaultdict(int)
    ends: list[tuple[Elem, str, str]] = []                 # (wire, node at a, node at b)
    for w in wires:
        u, v = owner[w["a"]], owner[w["b"]]
        for e in "ab": cnt[w[e]] += 1
        if u in gnd: u = f"~g:{w['id']}:a"; nodes[u] = Node(u, "gnd", None, 10.0, 10.0)
        if v in gnd: v = f"~g:{w['id']}:b"; nodes[v] = Node(v, "gnd", None, 10.0, 10.0)
        ends.append((w, u, v))
    wend = {w["id"]: (u, v) for w, u, v in ends}

    def key_at(nid: str, ref: str, wid: str) -> str:
        """The key of a wire's end: the pin ref, or ref#id where the symbol has an anchor per wire (bars, ground marks, shared pins)."""
        n = nodes[nid]
        return f"{ref}#{wid}" if n.kind == "gnd" or n.item["symbol"] in BARS or cnt[ref] > 1 else ref  # type: ignore[index]
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)     # node -> (other node, own pin ref)
    for w, u, v in ends:
        adj[u].append((v, w["a"])); adj[v].append((u, w["b"]))
    for w, u, v in ends:
        for nid, ref in ((u, w["a"]), (v, w["b"])):
            if nodes[nid].kind == "gnd": k = key_at(nid, ref, w["id"]); nodes[nid].off, nodes[nid].act = {k: (0.0, 5.0)}, {k: "L"}
    # ---- levels: distance from the sources over the wires (ground marks hang off their part)
    real = sorted(i for i, nd in nodes.items() if nd.kind == "item")
    lvl: dict[str, int] = {}
    todo = deque(n for n in real if its[n]["symbol"] == "battery")
    for q0 in todo: lvl[q0] = 0
    for start in [None, *real]:
        if start is not None:
            if start in lvl: continue
            lvl[start] = 0; todo.append(start)
        while todo:
            u = todo.popleft()
            for v, _ in sorted(adj[u]):
                if v not in lvl and nodes[v].kind == "item": lvl[v] = lvl[u] + 1; todo.append(v)
    for g, nd in nodes.items():
        if nd.kind == "gnd": lvl[g] = lvl[adj[g][0][0]] + 1
    kk = lambda n: (lvl[n], RANK[its[n]["symbol"]] if n in its else 6, _natural(n))  # noqa: E731
    # ---- the side wanted at every end: towards the lower node on the left
    for w, u, v in ends:
        for me, other, ref in ((u, v, w["a"]), (v, u, w["b"])):
            nodes[me].ends.append((key_at(me, ref, w["id"]), "L" if kk(other) < kk(me) else "R", w["id"], ref))
    flip: dict[str, bool] = {}
    for iid in real:                                     # an in-line part or harness connector: the group of terminals facing the lower neighbours goes left
        it, n = its[iid], nodes[iid]
        if it["symbol"] in ("block", *BARS): continue
        defs = {a["id"]: a["side"] for a in S.build(it, 0, 0)[0]["anchors"]}
        grp = {p["anchor"]: (i if it["symbol"] == "harness" else int(defs.get(p["anchor"], "L") == "R")) for i, b in enumerate(it["blocks"]) for p in b["pins"]}
        score: dict[int, list[int]] = defaultdict(list)
        for other, own in adj[iid]:
            if own in grp: score[grp[own]].append(lvl[other])
        m0, m1 = (sum(score[g]) / len(score[g]) if score[g] else None for g in (0, 1))
        flip[iid] = m0 is not None and ((m1 is not None and m0 > m1) or (m1 is None and m0 > lvl[iid]))
        n.ends = [(k, ("R" if flip[iid] else "L") if grp[ref] == 0 else ("L" if flip[iid] else "R"), wid, ref) if ref in grp else (k, s_, wid, ref) for k, s_, wid, ref in n.ends]  # noqa: E501

    def build(n: Node, pos: dict[str, float]) -> None:
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
                    for k in multi.get(p["anchor"], [p["anchor"]]): sd[k] = "L" if (i == 0) != flip.get(it["id"], False) else "R"
        n.req = sd
        n.taps = None
        if it["symbol"] in BARS:   # an anchor per wire, in the order of the far ends
            pins = {p["anchor"]: p for b in it["blocks"] for p in b["pins"]}
            n.taps = []
            for s_ in "LR":
                for k, _, wid, ref in sorted((e for e in n.ends if e[1] == s_), key=lambda e: (pos.get(e[0], 0.0), _natural(e[2]))):
                    p = pins.get(ref, {})
                    n.taps.append(dict(id=k, model=ref, side=s_, text=p.get("n") or ("" if len(pins) < 2 else p.get("name", ""))))
        sy, _ = symfor(n, 0, 0)
        n.w, n.h = sy["w"], sy["h"]
        n.off = {a["id"]: (a["x"], a["y"]) for a in sy["anchors"]}
        n.act = {a["id"]: a["side"] for a in sy["anchors"]}

    def symfor(n: Node, x: float, y: float) -> tuple[Any, list[Any]]:
        """The node's symbol at (x, y): an anchor per wire where several wires share a pin; models back to the pin refs."""
        sy, tx = S.build(n.item2 or n.item, x, y, n.req, n.taps)  # type: ignore[arg-type]
        for ref, ks in n.fan.items():
            a = next(a for a in sy["anchors"] if a["id"] == ref)
            sy["anchors"] = [b for b in sy["anchors"] if b is not a] + [Anchor(id=k, model=a["model"], x=a["x"], y=a["y"] + GRID * i, side=a["side"]) for i, k in enumerate(ks)]  # noqa: E501
            sy["prims"] += [dict(kind="line", stroke="normal", x1=a["x"], y1=a["y"], x2=a["x"], y2=a["y"] + GRID * (len(ks) - 1))]  # type: ignore[list-item]
            sy["prims"] += [dict(kind="circle", stroke="normal", fill="black", cx=a["x"], cy=a["y"] + GRID * i, r=0.9) for i in range(len(ks))]  # type: ignore[misc]
            sy["h"] = max(sy["h"], ceil_to(a["y"] - y + GRID * (len(ks) - 1) + 2.5))
        back = {k: ref for ref, ks in n.fan.items() for k in ks} | {e[0]: e[3] for e in n.ends}
        for a in sy["anchors"]: a["model"] = back.get(a["model"], a["model"])
        for t in tx: t["model"] = back.get(t["model"], t["model"])
        return sy, tx
    for n in nodes.values():
        if n.kind == "item": build(n, {})
    # ---- columns: longest path over the wires, oriented by the sides of in-line parts and ground marks, else by level
    fixed = lambda n: n.kind == "gnd" or n.item["symbol"] not in ("block", *BARS)  # noqa: E731
    succ: dict[str, set[str]] = defaultdict(set)
    for w, u, v in ends:
        su = nodes[u].act.get(key_at(u, w["a"], w["id"]), "") if fixed(nodes[u]) else ""
        sv = nodes[v].act.get(key_at(v, w["b"], w["id"]), "") if fixed(nodes[v]) else ""
        lo, hi = (u, v) if su == "R" or sv == "L" else (v, u) if su == "L" or sv == "R" else (u, v) if kk(u) < kk(v) else (v, u)
        succ[lo].add(hi)
    indeg = dict.fromkeys(nodes, 0)
    for u in succ:
        for v in succ[u]: indeg[v] += 1
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
    for n in nodes.values():                             # blocks and bars face the columns their wires go to
        if n.kind == "item" and n.item["symbol"] in ("block", *BARS):  # type: ignore[index]
            far = lambda wid: next((o for o in wend[wid] if o != n.id), n.id)  # noqa: E731
            n.ends = [(k, "R" if nodes[far(wid)].col > n.col else "L", wid, ref) for k, _, wid, ref in n.ends]
            build(n, {})
    paths: list[tuple[Elem, list[Node], str, str, bool]] = []     # (wire, nodes from the left, key at the first, key at the last, reversed)
    loops = 0
    for w, u, v in ends:
        ku, kv = key_at(u, w["a"], w["id"]), key_at(v, w["b"], w["id"])
        rev = nodes[u].col > nodes[v].col or (nodes[u].col == nodes[v].col and u > v)
        loops += nodes[u].col == nodes[v].col
        pr = [nodes[v], nodes[u]] if rev else [nodes[u], nodes[v]]
        paths.append((w, pr, kv if rev else ku, ku if rev else kv, rev))
    for pi, (el, ns, k0, k1, rev) in enumerate(paths):
        if ns[1].col - ns[0].col > 1:
            mid = [Node(f"~{el['id']}~{c}", "dummy", None, 0.0, GRID) for c in range(ns[0].col + 1, ns[1].col)]
            for d in mid: d.col = int(d.id.rsplit("~", 1)[1]); d.off = {"~": (0.0, GRID)}; nodes[d.id] = d
            paths[pi] = (el, [ns[0], *mid, ns[1]], k0, k1, rev)
    cols: dict[int, list[Node]] = defaultdict(list)
    for n in sorted(nodes.values(), key=lambda n: (n.kind != "item", _natural(n.id))): cols[n.col].append(n)
    ncol = max(cols) + 1
    nb: dict[str, list[tuple[str, Node, str]]] = defaultdict(list)    # per node: (key here, other node, key there)
    hopkeys = lambda ns, k0, k1, i: (k0 if i == 0 else "~", k1 if i == len(ns) - 2 else "~")  # noqa: E731
    for el, ns, k0, k1, rev in paths:
        for i in range(len(ns) - 1):
            ka, kb = hopkeys(ns, k0, k1, i)
            nb[ns[i].id].append((ka, ns[i + 1], kb)); nb[ns[i + 1].id].append((kb, ns[i], ka))
    # ---- rows
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
            if n.kind == "item" and n.item["symbol"] in BARS and any(m.id in ypos for _, m, _ in nb[n.id]):  # type: ignore[index]
                build(n, {ka: ypos[m.id] + m.off[kb][1] for ka, m, kb in nb[n.id] if m.id in ypos})
        ws = [want(n, toward) for n in ns]
        if reorder:
            order = sorted(range(len(ns)), key=lambda i: (ws[i] is None, ws[i] if ws[i] is not None else ypos.get(ns[i].id, 0.0), ns[i].kind != "item", _natural(ns[i].id)))  # noqa: E501
            ns[:] = [ns[i] for i in order]; ws = [ws[i] for i in order]
        stack(ns, ws)
    c0 = max((n for n in nodes.values() if n.kind == "item"), key=lambda n: (len(nb[n.id]), -n.col)).col
    for npass in range(2):                               # outwards from the busiest column: the first pass orders, the second refines
        for c in [c0] + [c for d in range(1, ncol) for c in (c0 + d, c0 - d) if 0 <= c < ncol]:
            settle(c, 0 if c == c0 else -1 if c > c0 else 1, npass == 0 and c != c0)
    best = (crossings(), {c: list(v) for c, v in cols.items()}, dict(ypos))
    for _ in range(6):                                   # barycentre sweeps to the right and to the left; keep the fewest crossings
        for seq in (range(1, ncol), range(ncol - 2, -1, -1)):
            for c in seq: settle(c, -1 if seq.step > 0 else 1, True)
            x = crossings()
            if x < best[0]: best = (x, {c: list(v) for c, v in cols.items()}, dict(ypos))
    for c, v in best[1].items(): cols[c][:] = v
    ypos.update(best[2])
    for n in nodes.values():
        if n.kind == "item" and n.item["symbol"] in BARS: build(n, {ka: ypos[m.id] + m.off[kb][1] for ka, m, kb in nb[n.id]})  # type: ignore[index]
    for n in nodes.values(): n.y = ypos[n.id]
    # ---- channels: tracks and widths
    tr: dict[tuple[int, str], int] = {}
    dog: dict[tuple[int, str], float] = {}
    room, ntr = [0.0] * (ncol - 1), [0] * (ncol - 1)
    for c in range(ncol - 1):
        t, dg, _ = R.tracks(hops_of(c))
        tr |= {(c, k): v for k, v in t.items()}; dog |= {(c, k): v for k, v in dg.items()}
        ntr[c] = max(t.values(), default=-1) + 1
        room[c] = max([text_w(R.label_text(el), SIZE) + 5 for el, ns, *_ in paths if ns[0].col == c], default=0.0)
    chw = [max(10.0, ceil_to(room[c]) + GRID * ntr[c]) for c in range(ncol - 1)]
    colw = [ceil_to(max((n.w for n in cols[c]), default=0.0)) for c in range(ncol)]
    cx = [0.0]
    for c in range(ncol - 1): cx.append(cx[-1] + colw[c] + chw[c])
    top = min(n.y for n in nodes.values())
    total_w, total_h = cx[-1] + colw[-1], max(n.y + n.h for n in nodes.values()) - top
    x0, y0 = MARGIN + PAD, MARGIN + PAD
    for n in nodes.values(): n.x, n.y = x0 + cx[n.col], n.y - top + y0
    # ---- geometry
    syms: list[Any] = []; texts: list[Any] = []; out: list[Any] = []
    for n in sorted(nodes.values(), key=lambda n: n.id):
        if n.kind == "item":
            sy, tx = symfor(n, n.x, n.y)
            syms.append(sy); texts += tx
        elif n.kind == "gnd":
            k, _, wid, ref = n.ends[0]
            syms.append(_ground_mark(n.x, n.y, wid, ref))
    for el, ns, k0, k1, rev in paths:
        pts = [(ns[0].x + ns[0].off[k0][0], ns[0].at(k0))]
        for i in range(len(ns) - 1):
            a, b = ns[i], ns[i + 1]
            ka, kb = hopkeys(ns, k0, k1, i)
            xt = lambda t: x0 + cx[a.col] + colw[a.col] + ceil_to(room[a.col]) + GRID * t  # noqa: E731
            if (a.col, el["id"]) in dog:
                ym = dog[(a.col, el["id"])] - top + y0
                x1, x2 = xt(tr[(a.col, el["id"] + "|1")]), xt(tr[(a.col, el["id"] + "|2")])
                pts += [(x1, a.at(ka)), (x1, ym), (x2, ym), (x2, b.at(kb))]
            elif (a.col, el["id"]) in tr:
                pts += [(xt(tr[(a.col, el["id"])]), a.at(ka)), (xt(tr[(a.col, el["id"])]), b.at(kb))]
            pts.append((b.x + b.off[kb][0], b.at(kb)) if i == len(ns) - 2 else (x0 + cx[b.col] + colw[b.col], b.at(kb)))
        p = R.trace(pts)
        if rev: p = p[::-1]
        u, v = wend[el["id"]]
        out.append(dict(id=el["id"], model=el["model"], label=el["label"], gauge=el["gauge"], colour=el["colour"], hex=el["hex"], weight=el["weight"], points=p,
                        a=key_at(u, el["a"], el["id"]), b=key_at(v, el["b"], el["id"]), pair=el["pair"], shield=el["shield"], fault=el["fault"]))
    texts += R.labels(dict(symbols=syms, wires=out, texts=texts, flags=[]))
    # ---- the sheet: as big as the content needs, in the standard frame
    W = max(330.0, ceil_to(total_w + 2 * (MARGIN + PAD)))
    H = ceil_to(total_h + 2 * (MARGIN + PAD) + STRIP_H)
    SHEETS["OV"] = (W, H)                                # frame, strip and title block are placed by style.areas(size)
    info = dict(title=f"{sc['title']} overview", scope="overview", project=sc["project"], revision=meta.get("revision", ""), date=meta.get("date", ""),
                drawn_by=meta.get("drawn_by", ""), source=meta.get("source", ""))
    notes = [f"{len(out)} wires, each drawn once with label, gauge (AWG) and colour code.", "A ground mark right of a pin is that wire's end on the ground bus.",
             "Splices and buses are bars with a dot per wire. Power flows from left to right."]
    sheet: dict[str, Any] = dict(n=1, of=1, size="OV", w_mm=W, h_mm=H, grid_mm=5.0, symbols=syms, wires=out, texts=texts, flags=[], rules=[], table=dict(sheet=1, rows=[]))  # noqa: E501
    sheet.update(S.furniture(info, "OV", 1, 1, list(dict.fromkeys(s["kind"] for s in syms)), notes))
    sheet["loops"] = loops                               # wires whose two ends share a column (a bracket in a channel); counted for the prototype
    return dict(version=1, drawing=info, sheets=[sheet])  # type: ignore[typeddict-item,return-value,list-item]
