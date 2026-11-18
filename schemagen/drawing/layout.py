"""Layout: places a scene (or a page of it) on a sheet (docs/drawing-model.md), then routes it (route.py). A purpose-built layered layout:

columns   the scope's components in the middle, what feeds them to the left, what they feed to the right, found by walking out from
          them through the wires (an in-line part or a harness connector has its two sides, so a breaker is fed on its LINE side);
          the scene's column hints break ties. A wire that passes a column rides a lane through it (a dummy node).
rows      each column is ordered by the barycentre of the rows its wires leave from and stacked with the least displacement
          (pool-adjacent-violators on the 5 mm grid), outwards from the focus, so far-end blocks sit level with the pins they serve.
          Pins face the side their wire goes to; a splice, bus or ground gets one anchor per wire, ordered like its far ends.
channels  between columns: a track per wire that changes row (route.tracks), and room for the wire's text on its first stretch.
Everything is deterministic: stable sorts with full tie-break keys, no randomness."""
from __future__ import annotations

import heapq
import math
from collections import Counter, defaultdict, deque
from functools import lru_cache
from typing import Any

from ..app.workspace import _natural
from . import route as R
from .geometry import Anchor
from . import symbols as S
from ..exporters.palette import words as colour_words
from .style import GRID, SIZE, areas, ceil_to, text_w

BARS = ("splice", "bus", "ground")
GAP = 5.0
SECOND = {"LOAD", "OUT", "B", "NO", "NC", "87", "87A", "2", "+", "OUT+"}   # terminal names of the second end of an in-line part
Elem = dict[str, Any]


class Node:
    """A symbol, a flag or a lane (dummy) in a column. off maps an end key to the anchor's offset from the node's top left."""
    def __init__(s, id: str, kind: str, col: int, w: float, h: float, item: Elem | None = None, flag: Elem | None = None) -> None:
        s.id, s.kind, s.col, s.w, s.h, s.item, s.flag = id, kind, col, w, h, item, flag
        s.x = s.y = 0.0
        s.off: dict[str, tuple[float, float]] = {}
        s.ends: list[tuple[str, str, Elem, str]] = []  # (end key, side wanted, element, pin ref) for taps and sides
        s.fan: dict[str, list[str]] = {}               # in-line parts: pin ref -> keys of its wires when several share it
        s.item2: Elem | None = None
        s.req: dict[str, str] = {}
        s.taps: list[dict[str, str]] | None = None
        s.act: dict[str, str] = {}                     # the side each anchor really has in the symbol
        s.sides: dict[str, str] = {}

    def at(s, key: str) -> float:
        return s.y + s.off[key][1]


@lru_cache(maxsize=1 << 16)  # a sort key, asked for the same few thousand ids again and again (read only)
def _nat(s: str) -> Any:
    return _natural(s)


def _hint(it: Elem) -> int:
    return int(it["column"])


def _defaults(it: Elem) -> dict[str, str]:
    """The side each anchor of the item has when the symbol is drawn without instructions."""
    sy, _ = S.build(it, 0, 0)
    out: dict[str, str] = {a["id"]: a["side"] for a in sy["anchors"]}
    if len(out) == 1 and it["symbol"] not in ("block", "harness", *BARS):      # one terminal shown: the name says which end of the part it is
        (a,) = out
        p = next(p for b in it["blocks"] for p in b["pins"] if p["anchor"] == a)
        if (next(b["id"] for b in it["blocks"] if p in b["pins"]) or p["n"] or p["name"]).upper() in SECOND: out[a] = "R"
    return out


# ---------------------------------------------------------------- columns
def columns(page: Elem) -> tuple[dict[str, int], dict[str, int], dict[str, bool]]:
    """Column of every item, its level (distance from the focus, negative on the feeding side), and for in-line parts and harness
    connectors whether the second group of terminals is on the left."""
    items = {i["id"]: i for i in page["items"]}
    owner = {p["anchor"]: i["id"] for i in items.values() for b in i["blocks"] for p in b["pins"]}
    adj: dict[str, list[tuple[str, str, str]]] = defaultdict(list)   # u -> (v, anchor at u, anchor at v)
    edges: list[tuple[str, str, str, str]] = []
    for w in page["wires"]:
        u, v = owner[w["a"]], owner[w["b"]]
        if u != v: adj[u].append((v, w["a"], w["b"])); adj[v].append((u, w["b"], w["a"])); edges.append((u, v, w["a"], w["b"]))
    scope = set(page["scope"]["ids"]) if page["scope"]["kind"] != "system" else None
    focus = sorted((i for i, it in items.items() if it["role"] == "in_scope" or (it["role"] == "harness" and (scope is None or it["code"] in scope))), key=_nat)
    grouped = {i for i, it in items.items() if it["symbol"] not in ("block", *BARS)}
    defs = {i: _defaults(items[i]) for i in grouped}
    group = lambda u, a: 0 if defs[u].get(a, "L") == "L" else 1  # noqa: E731
    left: dict[str, int] = dict.fromkeys(grouped, 0)               # the group of terminals on the left
    lvl = dict.fromkeys(focus, 0)

    def lean(v: str, u: str) -> int:
        return sum(_hint(items[w]) - _hint(items[u]) for w, _, _ in adj[v] if w != u)
    q = deque(focus)
    while q:
        u = q.popleft()
        for v, au, av in sorted(adj[u], key=lambda t: (_nat(t[0]), t[1], t[2])):
            if v in lvl: continue
            if lvl[u]: d = 1 if lvl[u] > 0 else -1
            elif u in grouped: d = -1 if group(u, au) == left[u] else 1
            else: d = -1 if _hint(items[v]) < _hint(items[u]) or lean(v, u) < 0 else 1
            lvl[v] = lvl[u] + d
            if v in grouped: left[v] = group(v, av) if d > 0 else 1 - group(v, av)
            q.append(v)
    for i in items:
        lvl.setdefault(i, 1 if _hint(items[i]) >= 3 else -1)
    key = lambda i: (lvl[i], _hint(items[i]), _nat(items[i]["code"]))  # noqa: E731
    side = lambda u, a: None if u not in grouped else "L" if group(u, a) == left[u] else "R"  # noqa: E731
    succ: dict[str, set[str]] = defaultdict(set)
    for u, v, a, b in edges:
        su, sv = side(u, a), side(v, b)
        if su and (not sv or abs(lvl[u]) <= abs(lvl[v])): lo, hi = (v, u) if su == "L" else (u, v)
        elif sv: lo, hi = (u, v) if sv == "L" else (v, u)
        else: lo, hi = sorted((u, v), key=key)
        succ[lo].add(hi)
    indeg = dict.fromkeys(items, 0)
    for lo in succ:
        for hi in succ[lo]: indeg[hi] += 1
    col = dict.fromkeys(items, 0)
    ready = [(key(i), i) for i in items if not indeg[i]]
    heapq.heapify(ready)
    done: set[str] = set()
    while len(done) < len(items):
        if not ready: heapq.heappush(ready, min((key(i), i) for i in items if i not in done))   # a cycle: start at its smallest
        _, u = heapq.heappop(ready)
        if u in done: continue
        done.add(u)
        for v in sorted(succ[u], key=key):
            if v in done: continue
            col[v] = max(col[v], col[u] + 1); indeg[v] -= 1
            if not indeg[v]: heapq.heappush(ready, (key(v), v))
    for u in sorted((i for i in items if lvl[i] < 0 and i not in focus), key=key, reverse=True):  # noqa: E741   # feeders sit next to what they feed
        if succ[u]: col[u] = max(col[u], min(col[v] for v in succ[u]) - 1)
    base = min(col.values(), default=0)
    return {i: c - base for i, c in col.items()}, lvl, {i: bool(left[i]) for i in grouped}


# ---------------------------------------------------------------- one page
def _taps(it: Elem, ends: list[tuple[str, str, Elem, str]], pos: dict[str, float]) -> list[dict[str, str]]:
    """The taps of a splice, bus or ground: wires on each side in the order of their far ends (pos: far end key -> y)."""
    pins = {p["anchor"]: p for b in it["blocks"] for p in b["pins"]}
    out = []
    for s in "LR":
        mine = sorted((e for e in ends if e[1] == s), key=lambda e: (pos.get(e[0], 0.0), _nat(e[2]["id"])))
        for key, _, el, ref in mine:
            p = pins.get(ref, {})
            out.append(dict(id=key, model=ref, side=s, text=p.get("n") or ("" if len(pins) < 2 else p.get("name", ""))))
    return out


def place(page: Elem, size: str = "A3", fside: dict[str, str] | None = None, spread: int = 0, reserve: float = 0.0) -> Elem:
    """Lays out and routes one page: returns the sheet's symbols, wires, texts, flags, the natural extent (`w`, `h`, before `spread`) and `bad`
    (pairs of wires in one channel that need a dogleg: should be 0). spread 1: use the sheet, rows stretched up to 2x and channels widened (2: channels only).
    reserve: height kept free at the foot of the area (for the wire table)."""
    col, lvl, flip = columns(page)
    items = {i["id"]: i for i in page["items"]}
    owner = {p["anchor"]: i["id"] for i in items.values() for b in i["blocks"] for p in b["pins"]}
    nodes: dict[str, Node] = {iid: Node(iid, "item", col[iid], 0, 0, item=it) for iid, it in items.items()}
    paths: list[tuple[Elem, list[Node], str, str, bool]] = []     # (element, nodes from the left, key at the first, key at the last, reversed)

    cnt = Counter([w[e] for w in page["wires"] for e in "ab"] + [f["at"] for f in page["flags"]])

    def key_at(iid: str, ref: str, eid: str) -> str:
        """The key of a wire's end at a pin: the pin ref, or ref#id when the symbol has an anchor per wire (bars, and pins that several wires share)."""
        return f"{ref}#{eid}" if items[iid]["symbol"] in BARS or cnt[ref] > 1 else ref

    def end(iid: str, ref: str, other_col: int, el: Elem) -> str:
        k = key_at(iid, ref, el["id"])
        nodes[iid].ends.append((k, "R" if other_col > col[iid] else "L", el, ref))
        return k
    for w in page["wires"]:
        a, b = owner[w["a"]], owner[w["b"]]
        ka, kb = end(a, w["a"], col[b], w), end(b, w["b"], col[a], w)
        rev = col[a] > col[b]
        pr = [nodes[a], nodes[b]]
        paths.append((w, pr[::-1] if rev else pr, kb if rev else ka, ka if rev else kb, rev))
    for f in page["flags"]:
        a = owner[f["at"]]
        it = items[a]
        have = [e[1] for e in nodes[a].ends if e[3] == f["at"]] if it["symbol"] not in BARS else []
        if fside and f["id"] in fside: sd = fside[f["id"]]
        elif have: sd = have[0]
        elif it["symbol"] in BARS:
            sides = [e[1] for e in nodes[a].ends]
            sd = "R" if sides.count("L") >= sides.count("R") and lvl[a] >= 0 or sides.count("L") > sides.count("R") else "L"
        elif it["symbol"] == "block": sd = "L" if lvl[a] < 0 else "R"
        else:
            sd = _defaults(it).get(f["at"], "R")
            if flip.get(a): sd = "R" if sd == "L" else "L"
        fn = Node(f["id"], "flag", col[a] + (1 if sd == "R" else -1), 0, 0, flag=f)
        nodes[f["id"]] = fn
        ka = end(a, f["at"], fn.col, f)
        fl = S.flag(f["id"], f["model"], f["kind"], f["text"], f["target"], f.get("sheet"))
        fn.w, fn.h = fl["w"], fl["h"]
        fn.off = {"f": (0.0 if sd == "R" else fl["w"], 5.0)}
        paths.append((f, [nodes[a], fn] if sd == "R" else [fn, nodes[a]], ka if sd == "R" else "f", "f" if sd == "R" else ka, sd == "L"))
    shift = -min([n.col for n in nodes.values()] + [0])
    for n in nodes.values(): n.col += shift
    for k, (el, ns, k0, k1, rev) in enumerate(paths):            # lanes: a wire that passes columns rides one through each
        if ns[1].col - ns[0].col > 1:
            mid = [Node(f"~{el['id']}~{c}", "dummy", c, 0, GRID) for c in range(ns[0].col + 1, ns[1].col)]
            for d in mid: d.off = {"~": (0.0, GRID)}; nodes[d.id] = d
            paths[k] = (el, [ns[0], *mid, ns[1]], k0, k1, rev)
    cols: dict[int, list[Node]] = defaultdict(list)
    for n in sorted(nodes.values(), key=lambda n: (n.kind != "item", _nat(n.id))): cols[n.col].append(n)
    ncol = max(cols, default=-1) + 1
    nb: dict[str, list[tuple[str, Node, str]]] = defaultdict(list)    # per node: (key here, other node, key there)
    hopkeys = lambda ns, k0, k1, i: (k0 if i == 0 else "~", k1 if i == len(ns) - 2 else "~")  # noqa: E731
    for el, ns, k0, k1, rev in paths:
        for i in range(len(ns) - 1):
            ka, kb = hopkeys(ns, k0, k1, i)
            nb[ns[i].id].append((ka, ns[i + 1], kb)); nb[ns[i + 1].id].append((kb, ns[i], ka))

    def build(n: Node, pos: dict[str, float]) -> None:
        it = n.item
        assert it is not None
        sd: dict[str, str] = {}
        rowwise = it["symbol"] in ("block", "harness", "dcdc")
        for k, s_, _, ref in n.ends: sd.setdefault(k if rowwise or it["symbol"] in BARS else ref, s_)
        multi: dict[str, list[str]] = defaultdict(list)
        for k, _, _, ref in sorted(n.ends, key=lambda e: _nat(e[2]["id"])):
            if k != ref and it["symbol"] not in BARS: multi[ref].append(k)
        n.item2, n.fan = None, {}
        if multi and rowwise:   # one row per wire at a shared pin
            n.item2 = dict(it, blocks=[dict(b, pins=[q for p in b["pins"] for q in ([dict(p, anchor=k) for k in multi[p["anchor"]]] if p["anchor"] in multi else [p])])  # noqa: E501
                                       for b in it["blocks"]])
        elif multi: n.fan = multi
        if it["symbol"] == "harness" and len(it["blocks"]) == 2:
            for i, b in enumerate(it["blocks"]):
                for p in b["pins"]:
                    for k in multi.get(p["anchor"], [p["anchor"]]): sd[k] = "L" if (i == 0) != flip.get(it["id"], False) else "R"
        n.req, n.taps = sd, _taps(it, n.ends, pos) if it["symbol"] in BARS else None
        sy, _ = symfor(n, 0, 0)
        n.w, n.h = sy["w"], sy["h"]
        n.off = {a["id"]: (a["x"], a["y"]) for a in sy["anchors"]}
        n.act = {a["id"]: a["side"] for a in sy["anchors"]}

    def symfor(n: Node, x: float, y: float) -> tuple[Any, list[Any]]:
        """The node's symbol at (x, y): with a row or anchor per wire where several wires share a pin, models back to the pin refs."""
        sy, tx = S.build(n.item2 or n.item, x, y, n.req, n.taps)  # type: ignore[arg-type]
        for ref, ks in n.fan.items():
            a = next(a for a in sy["anchors"] if a["id"] == ref)
            sy["anchors"] = [b for b in sy["anchors"] if b is not a] + [Anchor(id=k, model=a["model"], x=a["x"], y=a["y"] + GRID * i, side=a["side"]) for i, k in enumerate(ks)]  # noqa: E501
            sy["prims"] += [dict(kind="line", stroke="normal", x1=a["x"], y1=a["y"], x2=a["x"], y2=a["y"] + GRID * (len(ks) - 1))]
            sy["prims"] += [dict(kind="circle", stroke="normal", fill="black", cx=a["x"], cy=a["y"] + GRID * i, r=0.9) for i in range(len(ks))]
            sy["h"] = max(sy["h"], ceil_to(a["y"] - y + GRID * (len(ks) - 1) + 2.5))
        back = {k: ref for ref, ks in n.fan.items() for k in ks} | {e[0]: e[3] for e in n.ends}
        for a in sy["anchors"]: a["model"] = back.get(a["model"], a["model"])
        if n.item and n.item["symbol"] not in ("block", "harness", *BARS) and n.item["role"] != "in_scope":   # no wire here: a dashed lead, not a loose wire
            used = {e[3] for e in n.ends}
            for a in (a for a in sy["anchors"] if a["model"] not in used):
                for pr in sy["prims"]:
                    if pr["kind"] == "line" and ((pr["x1"], pr["y1"]) == (a["x"], a["y"]) or (pr["x2"], pr["y2"]) == (a["x"], a["y"])): pr["dash"] = True
        for t in tx: t["model"] = back.get(t["model"], t["model"])
        return sy, tx
    for n in nodes.values():
        if n.kind == "item": build(n, {})
    wrongside = {f["id"]: nodes[owner[f["at"]]].act[k] for f, k in ((f, f["at"]) for f in page["flags"]) if k in nodes[owner[f["at"]]].act
                 and nodes[owner[f["at"]]].act[k] != ("R" if nodes[f["id"]].col > nodes[owner[f["at"]]].col else "L")}
    if wrongside: return place(page, size, dict(fside or {}, **wrongside), spread, reserve)   # a flag on the side where the symbol's terminal is not
    ring = [w for w, ns, k0, k1, rev in paths if w in page["wires"] and (owner[w["a"]] == owner[w["b"]] or any(m.act.get(k, "") not in ("", "R" if o.col > m.col else "L") for m, k, o in ((ns[0], k0, ns[-1]), (ns[-1], k1, ns[0]))))]  # noqa: E501
    if ring:   # a wire that would have to run back through a symbol (a loop in the wiring, or both ends on one part): two off-sheet flags, each naming the other end
        ids = {w["id"] for w in ring}
        stubs: list[Elem] = [dict(id=f"flag:{w['id']}:{e}", model=w["model"], kind="off_sheet", at=at, target=to, target_item="", text="→ " + _words(page, to), label=w["label"], gauge=w["gauge"],  # noqa: E501
                   colour=w["colour"], hex=w["hex"], cls=w["cls"], weight=w["weight"], stub=e) for w in ring for e, at, to in ((1, w["a"], w["b"]), (2, w["b"], w["a"]))]  # noqa: E501
        return place(dict(page, wires=[w for w in page["wires"] if w["id"] not in ids], flags=page["flags"] + stubs), size, None, spread, reserve)
    # ---- rows
    focus = [n for n in nodes.values() if n.kind == "item" and n.item and n.item["role"] == "in_scope"] or [n for n in nodes.values() if n.kind == "item"]
    c0 = max(focus, key=lambda n: (len(nb[n.id]), -n.col)).col if focus else 0
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
            c += n.h + (0.0 if n.kind == "dummy" and i + 1 < len(ns) and ns[i + 1].kind == "dummy" else GAP)
        pools: list[list[float]] = []
        for i, n in enumerate(ns):
            w = wants[i] if (wants[i] is not None) else ypos.get(n.id, cum[i])
            assert w is not None
            pools.append([w - cum[i], 1.0, i])
            while len(pools) > 1 and pools[-2][0] / pools[-2][1] > pools[-1][0] / pools[-1][1]:
                b = pools.pop(); pools[-1][0] += b[0]; pools[-1][1] += b[1]
        for k, p in enumerate(pools):
            base = round(p[0] / p[1] / GRID) * GRID
            for i in range(int(p[2]), int(pools[k + 1][2]) if k + 1 < len(pools) else len(ns)): ypos[ns[i].id] = base + cum[i]
    def crossings() -> int:
        n = 0
        for c in range(ncol - 1):
            hs = [(ypos[ns[i].id] + ns[i].off[hopkeys(ns, k0, k1, i)[0]][1], ypos[ns[i + 1].id] + ns[i + 1].off[hopkeys(ns, k0, k1, i)[1]][1])
                  for el, ns, k0, k1, rev in paths for i in range(len(ns) - 1) if ns[i].col == c]
            n += sum((a[0] - b[0]) * (a[1] - b[1]) < 0 for i, a in enumerate(hs) for b in hs[i + 1:])
        return n

    def settle(c: int, toward: int, reorder: bool) -> None:
        ns = cols[c]
        for n in ns:
            if n.kind == "item" and n.item["symbol"] in BARS and any(m.id in ypos for _, m, _ in nb[n.id]):  # type: ignore[index]
                build(n, {ka: ypos[m.id] + m.off[kb][1] for ka, m, kb in nb[n.id] if m.id in ypos})
        ws = [want(n, toward) for n in ns]
        if reorder:
            order = sorted(range(len(ns)), key=lambda i: (ws[i] is None, ws[i] if ws[i] is not None else ypos.get(ns[i].id, 0.0), ns[i].kind != "item", _nat(ns[i].id)))  # noqa: E501
            ns[:] = [ns[i] for i in order]; ws = [ws[i] for i in order]
        stack(ns, ws)
    for npass in range(2):                                        # outwards from the focus column: the first pass orders, the second refines
        for c in [c0] + [c for d in range(1, ncol) for c in (c0 + d, c0 - d) if 0 <= c < ncol]:
            settle(c, 0 if c == c0 else -1 if c > c0 else 1, npass == 0 and c != c0)
    best = (crossings(), {c: list(v) for c, v in cols.items()}, dict(ypos))
    for _ in range(8):                                            # barycentre sweeps to the right and to the left; keep the fewest crossings
        for seq in (range(1, ncol), range(ncol - 2, -1, -1)):
            for c in seq: settle(c, -1 if seq.step > 0 else 1, True)
            x = crossings()
            if x < best[0]: best = (x, {c: list(v) for c, v in cols.items()}, dict(ypos))
    for c, v in best[1].items(): cols[c][:] = v
    ypos.update(best[2])
    def rebar() -> None:
        for n in nodes.values():
            if n.kind == "item" and n.item["symbol"] in BARS: build(n, {ka: ypos[m.id] + m.off[kb][1] for ka, m, kb in nb[n.id]})  # type: ignore[index]

    def extent() -> tuple[float, float]:
        return min(ypos[n.id] for n in nodes.values()), max(ypos[n.id] + n.h for n in nodes.values())
    rebar()
    ax, ay, aw, ah = areas(size)["area"]
    ah -= reserve
    top, bottom = extent() if nodes else (0.0, 0.0)
    nat_h = bottom - top
    stretched = False
    if spread == 1 and nodes:    # stretch the rows by the factor that leaves the fewest crossings (not when anything would overlap)
        base = dict(ypos)
        pick: tuple[int, float, dict[str, float]] = (crossings(), 1.0, base)
        for f in sorted({min(2.0, ah / max(1.0, nat_h)), 2.0 if 2 * nat_h <= ah else 1.0, 1.5 if 1.5 * nat_h <= ah else 1.0} - {1.0}, reverse=True):
            for n in nodes.values(): ypos[n.id] = top + math.floor((base[n.id] - top) * f / GRID + 1e-9) * GRID
            rebar()
            gap = lambda a, b: a.h + (0.0 if a.kind == b.kind == "dummy" else GAP)  # noqa: E731
            if any(ypos[b.id] < ypos[a.id] + gap(a, b) - 1e-9 for ns in cols.values() for a, b in zip(ns, ns[1:])): continue
            if (x := crossings()) < pick[0] or (x == pick[0] and pick[1] == 1.0): pick = (x, f, dict(ypos))
        ypos.update(pick[2]); rebar()
        stretched = pick[1] > 1.0
    for n in nodes.values(): n.y = ypos[n.id]
    # ---- channels: tracks and widths
    tr: dict[tuple[int, str], int] = {}
    dog: dict[tuple[int, str], float] = {}
    room = [0.0] * max(ncol - 1, 0)
    ntr = [0] * max(ncol - 1, 0)
    nbad = 0
    for c in range(ncol - 1):
        hops: list[tuple[str, float, float]] = []
        for el, ns, k0, k1, rev in paths:
            for i in range(len(ns) - 1):
                if ns[i].col != c: continue
                ka, kb = hopkeys(ns, k0, k1, i)
                hops.append((el["id"], ns[i].at(ka), ns[i + 1].at(kb)))
                if i == 0: room[c] = max(room[c], text_w(R.label_text(el), SIZE) + 5)
        t, dg, bad = R.tracks(hops)
        nbad += bad
        tr |= {(c, k): v for k, v in t.items()}
        dog |= {(c, k): v for k, v in dg.items()}
        ntr[c] = max(t.values(), default=-1) + 1
    chw = [max(10.0, ceil_to(room[c]) + GRID * ntr[c]) for c in range(ncol - 1)]
    colw = [ceil_to(max((n.w for n in cols[c]), default=0.0)) for c in range(ncol)]
    nat_w = sum(colw) + sum(chw)
    if stretched and nat_w > aw: return place(page, size, fside, 2, reserve)      # the stretch cost tracks and the page no longer fits: do without
    if spread and ncol > 1: chw = [w + min(40.0, max(0.0, (aw - nat_w) // (ncol - 1) // GRID * GRID)) for w in chw]
    cx = [0.0]
    for c in range(ncol - 1): cx.append(cx[-1] + colw[c] + chw[c])
    total_w = cx[-1] + colw[-1] if ncol else 0.0
    y0 = min((n.y for n in nodes.values()), default=0.0)
    total_h = max((n.y + n.h for n in nodes.values()), default=0.0) - y0
    ox = ax + max(0.0, (aw - total_w) // 2 // GRID * GRID)
    oy = ay + max(0.0, (ah - total_h) // 2 // GRID * GRID) - y0
    for n in nodes.values(): n.x, n.y = ox + cx[n.col], n.y + oy
    # ---- geometry
    syms: list[Any] = []; texts: list[Any] = []; flags: list[Any] = []; wires: list[Any] = []
    for n in sorted(nodes.values(), key=lambda n: n.id):
        if n.kind == "item" and n.item:
            sy, tx = symfor(n, n.x, n.y)
            syms.append(sy); texts += tx
        elif n.kind == "flag" and n.flag:
            f = n.flag
            flags.append(S.flag(f["id"], f["model"], f["kind"], f["text"], f["target"], f.get("sheet"), n.x, n.y, "L" if n.off["f"][0] == 0.0 else "R"))
            if f.get("covers"): flags[-1]["covers"] = f["covers"]
    for el, ns, k0, k1, rev in paths:
        ka = hopkeys(ns, k0, k1, 0)[0]
        pts = [(ns[0].x + ns[0].off[ka][0], ns[0].at(ka))]
        for i in range(len(ns) - 1):
            a, b = ns[i], ns[i + 1]
            ka, kb = hopkeys(ns, k0, k1, i)
            xt = lambda t: ox + cx[a.col] + colw[a.col] + ceil_to(room[a.col]) + GRID * t  # noqa: E731
            if (a.col, el["id"]) in dog:
                ym = dog[(a.col, el["id"])] + oy
                x1, x2 = xt(tr[(a.col, el["id"] + "|1")]), xt(tr[(a.col, el["id"] + "|2")])
                pts += [(x1, a.at(ka)), (x1, ym), (x2, ym), (x2, b.at(kb))]
            elif (a.col, el["id"]) in tr:
                pts += [(xt(tr[(a.col, el["id"])]), a.at(ka)), (xt(tr[(a.col, el["id"])]), b.at(kb))]
            pts.append((b.x + b.off[kb][0], b.at(kb)) if i == len(ns) - 2 else (ox + cx[b.col] + colw[b.col], b.at(kb)))
        p = R.trace(pts)
        if rev: p = p[::-1]
        if el.get("kind") in ("off_sheet", "continuation"):      # a flag's stub: from the anchor to the flag
            wires.append(dict(id=el["model"].removeprefix("conductor:") + ("~" if el.get("stub") == 2 else ""), model=el["model"], label=el["label"], gauge=el["gauge"], colour=el["colour"], hex=el["hex"],  # noqa: E501
                              weight=el["weight"], points=p, a=key_at(owner[el["at"]], el["at"], el["id"]), b=el["id"], pair="", shield="", fault=None,
                              silent="covers" in el))
        else:
            wires.append(dict(id=el["id"], model=el["model"], label=el["label"], gauge=el["gauge"], colour=el["colour"], hex=el["hex"], weight=el["weight"],
                              points=p, a=key_at(owner[el["a"]], el["a"], el["id"]), b=key_at(owner[el["b"]], el["b"], el["id"]), pair=el["pair"],
                              shield=el["shield"], fault=el["fault"]))
    sh: dict[str, Any] = dict(symbols=syms, wires=wires, texts=texts, flags=flags)
    sh["texts"] = texts + R.labels(sh)
    for w in wires: w.pop("silent", None)
    return dict(sh, w=nat_w, h=nat_h, bad=nbad)


# ---------------------------------------------------------------- pages
def _words(sc: Elem, ref: str) -> str:
    """What a pin is, in words: `ECU engine control unit J1-3`."""
    for it in sc["items"]:
        for b in it["blocks"]:
            for p in b["pins"]:
                if p["anchor"] == ref:
                    nm = f" ({it['name']})" if it["name"] and S.flat(it["name"]) != S.flat(it["code"]) and not it["name"].startswith(it["code"]) and len(it["name"]) <= 24 else ""  # noqa: E501
                    pin = "-".join(x for x in (b["id"] if b["id"] and (len(it["blocks"]) > 1 or p["n"]) else "", p["n"]) if x)
                    return f"{it['code']} {pin}{nm}".strip()
    return ref.removeprefix("pin:")


def _cid(e: Elem) -> str:
    return e["model"].removeprefix("conductor:")


def _flag(sc: Elem, e: Elem, at: str, other: str, sheet: int | None, text: str | None = None) -> Elem:
    """A continuation flag at anchor `at` for conductor e, which goes on at `other` on another sheet."""
    return dict(id=f"cont:{_cid(e)}", model=e["model"], kind="continuation", at=at, target=other, target_item="", text="→ " + (text or _words(sc, other)), label=e["label"],  # noqa: E501
                gauge=e["gauge"], colour=e["colour"], hex=e["hex"], cls=e["cls"], weight=e["weight"], sheet=sheet)


def _page(sc: Elem, elems: list[tuple[str, Elem]], nums: dict[str, list[int]] | None = None, me: int = 0) -> Elem:
    """The sub-scene of some elements (wires and flags): their items with only the pins they use (an item that is in scope keeps the spare pins
    between its first and last used pin), a wire is drawn on every page that shows both its ends, and every other conductor at a drawn anchor that
    is drawn elsewhere gets a continuation flag (a summary flag at a bus or ground with many). nums maps a conductor to the sheets it is on."""
    nums = nums or {}
    all_ = len(elems) == len(sc["wires"]) + len(sc["flags"]) and not any(e["id"].startswith("cont:") for _, e in elems)
    wires = [e for k, e in elems if k == "w"]
    flags = [e for k, e in elems if k == "f"]
    used = {a for w in wires for a in (w["a"], w["b"])} | {f["at"] for f in flags}
    items = []
    for it in sc["items"]:
        if all_: items.append(it); continue
        scoped = it["role"] in ("in_scope", "harness")
        if not any(p["anchor"] in used for b in it["blocks"] for p in b["pins"]): continue
        pn = sorted({p["n"] for b in it["blocks"] for p in b["pins"] if p["anchor"] in used}, key=_nat)
        blocks = []
        for b in it["blocks"]:
            if it["symbol"] not in ("block", "harness", "dcdc"): blocks.append(b); continue    # an in-line part keeps both terminals, a bar its node
            idx = [i for i, p in enumerate(b["pins"]) if p["anchor"] in used]
            if it["symbol"] == "harness":
                pins = [p for p in b["pins"] if _nat(pn[0]) <= _nat(p["n"]) <= _nat(pn[-1])]
            else:
                lo, hi = (min(idx), max(idx)) if idx else (1, 0)
                pins = [p for i, p in enumerate(b["pins"]) if p["anchor"] in used or (scoped and lo <= i <= hi and p["spare"])]
            if pins and (idx or it["symbol"] == "harness"): blocks.append(dict(b, pins=pins))
        items.append(dict(it, blocks=blocks, partial=it["partial"] or sum(len(b["pins"]) for b in blocks) < sum(len(b["pins"]) for b in it["blocks"])))
    shown = {p["anchor"]: it for it in items for b in it["blocks"] for p in b["pins"] if not p["spare"]}
    have = {_cid(e) for _, e in elems}
    if not all_:
        for w in sc["wires"]:
            if w["id"] not in have and w["a"] in shown and w["b"] in shown: wires.append(w); have.add(w["id"])
    byitem: dict[str, list[tuple[str, Elem, str]]] = defaultdict(list)    # item -> (anchor, element drawn elsewhere, other end)
    for k, e in [*(("w", w) for w in sc["wires"]), *(("f", f) for f in sc["flags"])]:
        if _cid(e) in have: continue
        for a in ((e["a"], e["b"]) if k == "w" else (e["at"],)):
            if a in shown: byitem[shown[a]["id"]].append((a, e, (e["b"] if e["a"] == a else e["a"]) if k == "w" else e["target"]))
    cont: list[Elem] = []
    for iid, lst in sorted(byitem.items()):
        it = next(x for x in items if x["id"] == iid)
        lst.sort(key=lambda t: (_nat(_cid(t[1])), t[0]))
        sheet = lambda e: min((n for n in nums.get(_cid(e), []) if n != me), default=None)  # noqa: E731
        mk = [_flag(sc, e, a, o, sheet(e), e["text"].removeprefix("→ ") if "a" not in e else None) for a, e, o in lst]
        if it["symbol"] in ("bus", "ground") and it["role"] != "in_scope" and len(mk) >= 4:
            cov = [dict(id=_cid(e), at=a, target=o, label=e["label"], gauge=e["gauge"], colour=e["colour"], text=(e.get("text") or _words(sc, o)).removeprefix("→ "))
                   for a, e, o in lst if "covers" not in e]
            cov += [c for _, e, _ in lst for c in e.get("covers", [])]
            sh = sorted({m["sheet"] for m in mk if m["sheet"]})
            mk = [dict(mk[0], id=f"cont:+{_cid(mk[0])}", text=f"+ {len(cov)} more wires on {it['code']}" + (f" (sheet {', '.join(map(str, sh))})" if sh else ""),
                       sheet=sh[0] if sh else None, covers=cov, at=cov[0]["at"], target=cov[0]["target"])]
        cont += mk
    return dict(scope=sc["scope"], title=sc["title"], project=sc["project"], items=items, wires=wires, flags=sorted(flags + cont, key=lambda f: _nat(f["id"])))


def paginate(sc: Elem, size: str = "A3") -> list[Elem]:
    """One page when the scene fits the sheet. Too wide: cut between two columns (the cut conductors end in a continuation flag on both sheets,
    naming the other sheet and what they go to); too tall: halve the wires, top to bottom in the unpaginated layout, at the boundary between
    connectors of the scope's components nearest the middle. Repeat until every page fits."""
    _, _, aw, ah = areas(size)["area"]
    elems: list[tuple[str, Elem]] = [("w", w) for w in sc["wires"]] + [("f", f) for f in sc["flags"]]
    group: dict[str, str] = {}
    for it in sc["items"]:
        if it["role"] == "in_scope" or (it["role"] == "harness" and (sc["scope"]["kind"] == "system" or it["code"] in sc["scope"]["ids"])):
            for b in it["blocks"]:
                for p in b["pins"]: group[p["anchor"]] = f"{it['id']}/{b['id']}"
    eg = lambda e: group.get(e[1].get("a", "") if e[0] == "w" else e[1]["at"]) or group.get(e[1].get("b", "")) or ""  # noqa: E731

    memo: dict[Any, Elem] = {}

    def fit(es: list[tuple[str, Elem]]) -> Elem:
        """The natural layout of a page of elements (kept: a page is measured several times)."""
        key = tuple((k, e["id"], e.get("own", "")) for k, e in es)
        if key not in memo: memo[key] = place(_page(sc, es), size)
        return memo[key]

    def across(es: list[tuple[str, Elem]]) -> list[list[tuple[str, Elem]]] | None:
        """The page cut between columns into sheets: the first holds the scope's components and as many neighbouring columns as fit the width,
        then the columns to the right, then those to the left, each as wide as fits. A cut conductor ends in a continuation flag on both sides."""
        pg = _page(sc, es)
        col, _, _ = columns(pg)
        owner = {p["anchor"]: i["id"] for i in pg["items"] for b in i["blocks"] for p in b["pins"]}
        top = max(col.values(), default=0)
        if top < 1: return None
        x0: dict[int, float] = {}
        x1: dict[int, float] = {}
        for s_ in fit(es)["symbols"]:
            c = col[s_["id"]]
            x0[c], x1[c] = min(x0.get(c, s_["x"]), s_["x"]), max(x1.get(c, 0.0), s_["x"] + s_["w"])
        for c in range(top + 1):
            x0.setdefault(c, next((x0[k] for k in range(c, top + 1) if k in x0), 0.0)); x1.setdefault(c, next((x1[k] for k in range(c, -1, -1) if k in x1), 0.0))

        def mk(a: int, b: int, start: Any) -> list[tuple[str, Elem]]:
            out: list[tuple[str, Elem]] = []
            for kind, e in es:
                ends: list[tuple[str, Any]] = [(e["at"], None)] if kind == "f" else [(e["a"], e["b"]), (e["b"], e["a"])]
                ins = [(x, o) for x, o in ends if a <= col[owner[x]] <= b]
                if len(ins) == len(ends): out.append((kind, e))
                for x, o in ins if len(ends) > len(ins) else []:
                    out.append(("f", dict(_flag(sc, e, x, o, None), peer=f"{_cid(e)}|{start(col[owner[o]])}", own=f"{_cid(e)}|{start(col[owner[x]])}",
                                          pair=e["pair"], shield=e["shield"], fault=e["fault"])))
            return out
        ok = lambda a, b: x1[b] - x0[a] <= aw and fit(mk(a, b, lambda c: c))["w"] <= aw  # noqa: E731
        mine = lambda i: i["role"] == "in_scope" or (i["role"] == "harness" and (sc["scope"]["kind"] == "system" or i["code"] in sc["scope"]["ids"]))  # noqa: E731
        foc = [col[i["id"]] for i in pg["items"] if mine(i)]
        lo, hi = (min(foc), max(foc)) if foc else (0, top)
        if foc and not ok(lo, hi):          # the scope's columns do not all fit: start from the first component named, the rest follows on later sheets
            ids = sc["scope"]["ids"]
            first = min((i for i in pg["items"] if mine(i) and i["code"] in ids), key=lambda i: ids.index(i["code"]), default=None)
            if first: lo = hi = col[first["id"]]
        if not ok(lo, hi): return None
        while hi < top and ok(lo, hi + 1): hi += 1
        while lo > 0 and ok(lo - 1, hi): lo -= 1
        rs = [(lo, hi)]
        a = hi + 1
        while a <= top:
            b = a
            while b < top and ok(a, b + 1): b += 1
            rs.append((a, b)); a = b + 1
        b = lo - 1
        while b >= 0:
            a = b
            while a > 0 and ok(a - 1, b): a -= 1
            rs.append((a, b)); b = a - 1
        if len(rs) < 2: return None
        start = lambda c: next(r[0] for r in rs if r[0] <= c <= r[1])  # noqa: E731
        return [mk(a, b, start) for a, b in rs]

    def split(es: list[tuple[str, Elem]]) -> list[list[tuple[str, Elem]]]:
        r = fit(es)
        if (r["w"] <= aw and r["h"] <= ah) or len(es) < 2: return [es]
        if r["w"] > aw and (ps := across(es)): return [q for p in ps for q in split(p)]
        y = {w["id"]: min(p[1] for p in w["points"]) for w in r["wires"]}
        ey = lambda e: y.get(_cid(e[1]) if e[0] == "f" else e[1]["id"], 0.0)  # noqa: E731
        named = [(ey(e), eg(e)) for e in es if eg(e)]
        near = lambda e: eg(e) or min(named, key=lambda t: abs(t[0] - ey(e)))[1] if named else ""  # noqa: E731
        gy: dict[str, list[float]] = defaultdict(list)
        for e in es: gy[near(e)].append(ey(e))
        rank = {g: i for i, g in enumerate(sorted(gy, key=lambda g: (sum(gy[g]) / len(gy[g]), g)))}
        es = sorted(es, key=lambda e: (rank[near(e)], ey(e), e[1]["id"]))
        n = len(es)
        cuts = [k for k in range(1, n) if near(es[k - 1]) != near(es[k])]      # between connectors first, else through the middle
        k = min(cuts, key=lambda k: abs(k - n / 2)) if cuts else n // 2
        return split(es[:k]) + split(es[k:])
    parts = split(elems)
    if len(parts) == 1: return [_page(sc, elems)]
    nums: dict[str, list[int]] = defaultdict(list)
    own: dict[str, int] = {}
    for i, es in enumerate(parts, 1):
        for _, e in es:
            nums[_cid(e)].append(i)
            if "own" in e: own[e["own"]] = i
    out = []
    for i, es in enumerate(parts, 1):
        es = [(k, dict(e, sheet=own[e["peer"]]) if "peer" in e else e) for k, e in es]
        out.append(_page(sc, es, nums, i))
    return out


def notes(pg: Elem, sh: Elem, table: str = "") -> list[str]:
    """The sheet's notes: a worked example of the wire text with the colour codes used on the sheet spelled out, where the wire table is,
    simulation faults, what contacts, spare pins and dashed stubs look like. The strip holds five lines; the first ones matter most."""
    els = [*pg["wires"], *pg["flags"], *(c for f in pg["flags"] for c in f.get("covers", []))]
    ex = next((w for w in pg["wires"] if w["gauge"] and w["colour"]), None) or next((w for w in els if w["gauge"] and w["colour"]), None)
    out = []
    if ex: out.append(f"Wire text {R.label_text(ex)} = wire {ex['label']}, {R.unit(ex['gauge'])}, {colour_words(ex['colour'])}.")
    codes = sorted({w["colour"] for w in els if w["colour"]})
    cur = "Colours:"
    for c in codes:
        item = f" {c} {colour_words(c)}" + ("," if c != codes[-1] else ".")
        if text_w(cur + item, SIZE) > 118 and cur != "Colours:": out.append(cur); cur = "  " + item.strip()
        else: cur += item
    if codes: out.append(cur)
    out += [f"Wire table: {table}."] if table else []
    out += [f"{w['label']} dashed: {w['fault']['status']}" + (f" ({w['fault']['reason']})" if w["fault"]["reason"] else "") for w in pg["wires"] if w["fault"]]
    kinds = {s["kind"] for s in sh["symbols"]}
    if kinds & {"switch", "relay"}: out.append("Contacts are drawn unpowered: switches open, relays de-energised.")
    if any(p["spare"] for it in pg["items"] for b in it["blocks"] for p in b["pins"]): out.append("Spare pins are grey and have no wire.")
    if any(pr.get("dash") for s in sh["symbols"] for pr in s["prims"]): out.append("A dashed stub on a part: that terminal has no wire on this drawing.")
    return out
