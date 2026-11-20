"""The overview: ONE sheet with the whole LV system, every conductor drawn exactly once (the "P&ID" view; contract in docs/drawing-model.md).

placement every component is a box; boxes are placed by a deterministic force layout that minimises the total wire length (springs along the wires,
          weighted by wire count; boxes repel only where they would touch; a faint left-to-right pull from the batteries), then moved apart on the grid
          so that every box keeps room for the wires around it. Parts wired together end up next to each other; there are no groups or frames.
sides     a terminal faces the side its wire goes to; an in-line part (breaker, switch, relay contacts, battery) is mirrored to face its neighbours;
          a harness connector is a slim bar with one tap per used pin and half, a splice a bar with a dot per wire, ground a mark at the end of a short
          stub at its pin (no routed ground bus), a relay's coil its own symbol, CAN wires are dashed.
routing   orthogonal on a 5 mm grid, wire by wire (short ones first), A* with a price for bends and crossings: a wire never enters a symbol, never runs
          on another wire, crosses only at right angles and only on a straight cell, and turns only on a free cell. Labels go above a free stretch of
          the wire (again every ~300 mm on long wires); one that finds no stretch is stacked on two lines or put below.
The sheet is as big as the content needs. Deterministic: sorted everywhere, no randomness."""
from __future__ import annotations

import heapq
import math
from collections import defaultdict, deque
from typing import Any

import numpy as np

from ..app.workspace import _natural
from . import route as R
from . import symbols as S
from .geometry import Anchor, Geometry
from .scope import scene
from .style import GRID, MARGIN, PAD, SIZE, STRIP_H, ceil_to, text_w

BARS = ("splice", "bus")
BARISH = (*BARS, "harness")                  # symbols with an anchor per wire, any side
FREE = ("block", "dcdc", *BARISH)            # terminals face whichever side their wire goes to
INLINE = ("breaker", "fuse", "switch", "relay", "battery", "terminator", "coil")      # two sides, mirrored as a whole
Elem = dict[str, Any]
Edge = tuple[Elem, str, str, str, str]       # (wire, node u, key at u, node v, key at v)
LONG, EVERY = 150.0, 300.0                   # a wire longer than LONG carries its label at both ends and every ~EVERY mm
BEND, CROSS = 2, 3                           # prices of a bend and of a crossing in cells of wire
BUDGET = 40000000                            # cells the search may look at in all (about 10 s); after that wires are routed without regard to each other
HW = 1.0                                     # weight of the heuristic in the search: a little longer wires, far fewer cells looked at
MARK = 5.0                                   # length of the ground mark (lead excluded)


class Node:
    """A symbol of the overview: its item, size, position, the anchors (`off`: key -> offset from the top left, `act`: key -> side) and its ends."""

    def __init__(s, id: str, item: Elem) -> None:
        s.id, s.item, s.w, s.h = id, item, 0.0, 0.0
        s.x = s.y = 0.0
        s.off: dict[str, tuple[float, float]] = {}
        s.act: dict[str, str] = {}
        s.ends: list[tuple[str, str, str, str]] = []   # (end key, side, wire id, pin ref)
        s.req: dict[str, str] = {}
        s.item2: Elem | None = None
        s.fan: dict[str, list[str]] = {}
        s.taps: list[Elem] | None = None
        s.stub = {"L": 0.0, "R": 0.0}                  # length of the ground stubs on each side

    @property
    def sym(s) -> str:
        return s.item["symbol"]

    @property
    def cx(s) -> float:
        return s.x + s.w / 2

    @property
    def cy(s) -> float:
        return s.y + s.h / 2


def _trim(it: Elem) -> Elem:
    """The item with the used pins only and no part numbers; a harness connector keeps both halves for every pin number in use; a splice has no label."""
    if it["symbol"] == "harness":
        used = {p["n"] for b in it["blocks"] for p in b["pins"] if not p["spare"]}
        bl = [dict(b, part="", mate="", pins=[p for p in b["pins"] if p["n"] in used and not p["spare"]]) for b in it["blocks"]]
    else: bl = [b for b in (dict(b, part="", mate="", pins=[p for p in b["pins"] if not p["spare"]]) for b in it["blocks"]) if b["pins"]]
    return dict(it, part="", location="", blocks=bl, **({"code": ""} if it["symbol"] == "splice" else {}))


def _split_relay(it: Elem) -> list[Elem]:
    """A relay as its contacts and its coil, its own item `<id>:coil`; a part whose contacts are not wired is its coil alone."""
    coil = it["attrs"].get("coil")
    if not coil: return [it]
    refs = {coil["a1"], coil["a2"]}
    pick = lambda keep: [b for b in (dict(b, pins=[p for p in b["pins"] if (p["anchor"] in refs) == keep]) for b in it["blocks"]) if b["pins"]]  # noqa: E731
    out = []
    if pick(False): out.append(dict(it, blocks=pick(False), attrs=dict(it["attrs"], coil=None)))
    if pick(True): out.append(dict(it, id=it["id"] + ":coil", name=(it["name"] or it["code"]) + " coil", symbol="coil", blocks=pick(True), attrs={}))
    return out


def _coil(it: Elem, x: float, y: float, sides: dict[str, str]) -> tuple[Elem, list[Any]]:
    """A relay's coil: a small box between its two terminals (first L, other R unless `sides` says otherwise) with the relay's name under it."""
    ps = [p for b in it["blocks"] for p in b["pins"]][:2]
    title, _ = S._head(it)
    B = S._B(it, x, y)
    W = ceil_to(max(20.0, S._tw(title, "name") + 2))
    s = [sides.get(p["anchor"], "L" if i == 0 else "R") for i, p in enumerate(ps)]
    if len(s) == 2 and s[0] == s[1]: s[1] = "R" if s[0] == "L" else "L"
    B.rect(5, 2.5, W - 10, 5, S.N, "white")
    B.line(0, 5, 5, 5); B.line(W - 5, 5, W, 5)
    for p, sd in zip(ps, s): B.anchor(p["anchor"], 0 if sd == "L" else W, 5, sd)
    B.text(title, W / 2, 11, "centre", "name")
    return dict(id=it["id"], kind="coil", model=it["model"], x=x, y=y, w=W, h=15.0, anchors=B.anchors, prims=B.prims), B.texts


def _bar(it: Elem, x: float, y: float, taps: list[Elem]) -> tuple[Elem, list[Any]]:
    """A harness connector: a slim bar, one tap per used pin and half, the pin number at the tap, the name above. A pin's taps on the two sides share a row."""
    title, code = S._head(it)
    hd = [(title, "name")] + ([(code, "part")] if code else [])
    half = ceil_to(max([5.0, *(S._tw(t["text"]) + 3 for t in taps), *((S._tw(t, r) + 2) / 2 for t, r in hd)]))
    B = S._B(it, x, y)
    y0 = 5 * len(hd) + 10
    rows: list[tuple[Elem | None, Elem | None]] = []
    for pin in dict.fromkeys(t["pin"] for t in taps):
        ls = [t for t in taps if t["pin"] == pin and t["side"] == "L"]
        rs = [t for t in taps if t["pin"] == pin and t["side"] == "R"]
        rows += [(ls[i] if i < len(ls) else None, rs[i] if i < len(rs) else None) for i in range(max(len(ls), len(rs)))]
    for i, (t, r) in enumerate(hd): B.text(t, half, 3.75 + 5 * i, "centre", r)
    if rows: B.line(half, y0 - 2.5, half, y0 + 5 * (len(rows) - 1) + 2.5)
    for i, row in enumerate(rows):
        yy = y0 + 5 * i
        for tp in row:
            if tp is None: continue
            L = tp["side"] == "L"
            B.line(half, yy, 0 if L else 2 * half, yy)
            B.text(tp["text"], half - 1.5 if L else half + 1.5, yy - 2.5, "right" if L else "left", "pin", model=tp["model"])
            B.anchor(tp["id"], 0 if L else 2 * half, yy, tp["side"], tp["model"])
    return dict(id=it["id"], kind="harness", model=it["model"], x=x, y=y, w=2 * half, h=ceil_to(y0 + 5 * max(0, len(rows) - 1) + 2.5), anchors=B.anchors, prims=B.prims), B.texts  # noqa: E501


class Env:
    """What building symbols needs: how many wire ends each pin has, which in-line parts are mirrored."""

    def __init__(s, cnt: dict[str, int]) -> None:
        s.cnt = cnt
        s.flip: dict[str, bool] = {}

    def key_at(s, n: Node, ref: str, wid: str) -> str:
        """The key of a wire's end: the pin ref, or ref#id where the symbol has an anchor per wire (bars, shared pins)."""
        return f"{ref}#{wid}" if n.sym in BARISH or s.cnt[ref] > 1 else ref

    def defaults(s, it: Elem) -> dict[str, str]:
        sy = _coil(it, 0, 0, {})[0] if it["symbol"] == "coil" else S.build(it, 0, 0)[0]
        return {a["id"]: a["side"] for a in sy["anchors"]}

    def build(s, n: Node, pos: dict[str, float]) -> None:
        """Sizes the item's symbol from the sides its ends want; `pos` (key -> y of the far end) orders the taps of a bar."""
        it = n.item
        sd: dict[str, str] = {}
        rowwise = it["symbol"] in ("block", "dcdc")
        for k, s_, _, ref in n.ends: sd.setdefault(k if rowwise or it["symbol"] in BARISH else ref, s_)
        multi: dict[str, list[str]] = defaultdict(list)
        for k, _, wid, ref in sorted(n.ends, key=lambda e: _natural(e[2])):
            if k != ref and it["symbol"] not in BARISH: multi[ref].append(k)
        n.item2, n.fan, n.taps = None, {}, None
        if multi and rowwise:   # one row per wire at a shared pin
            n.item2 = dict(it, blocks=[dict(b, pins=[q for p in b["pins"] for q in ([dict(p, anchor=k) for k in multi[p["anchor"]]] if p["anchor"] in multi else [p])]) for b in it["blocks"]])  # noqa: E501
        elif multi: n.fan = multi
        n.req = sd
        if it["symbol"] in BARS:   # an anchor per wire, in the order of the far ends
            pins = {p["anchor"]: p for b in it["blocks"] for p in b["pins"]}
            n.taps = []
            for s_ in "LR":
                for k, _, wid, ref in sorted((e for e in n.ends if e[1] == s_), key=lambda e: (pos.get(e[0], 0.0), _natural(e[2]))):
                    p = pins.get(ref, {})
                    n.taps.append(dict(id=k, model=ref, side=s_, text=p.get("n") or ("" if len(pins) < 2 else p.get("name", ""))))
        elif it["symbol"] == "harness":   # a tap per wire, the pins in order
            info = {p["anchor"]: (p["n"], i) for i, b in enumerate(it["blocks"]) for p in b["pins"]}
            n.taps = [dict(id=k, model=ref, side=s_, text=info[ref][0], pin=info[ref][0], half=info[ref][1], wid=wid) for k, s_, wid, ref in n.ends]
            n.taps.sort(key=lambda t: (_natural(t["pin"]), t["half"], _natural(t["wid"])))
        sy, _ = s.symfor(n, 0, 0)
        n.w, n.h = sy["w"], sy["h"]
        n.off = {a["id"]: (a["x"], a["y"]) for a in sy["anchors"]}
        n.act = {a["id"]: a["side"] for a in sy["anchors"]}

    def symfor(s, n: Node, x: float, y: float) -> tuple[Any, list[Any]]:
        """The node's symbol at (x, y), models back to the pin refs."""
        it = n.item2 or n.item
        if it["symbol"] == "coil": sy, tx = _coil(it, x, y, n.req)
        elif it["symbol"] == "harness": sy, tx = _bar(it, x, y, n.taps or [])
        else: sy, tx = S.build(it, x, y, n.req, n.taps)  # type: ignore[arg-type,assignment]
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


# ---------------------------------------------------------------- placement
def _box(n: Node, pad: float) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) of a node with its ground stubs and `pad` mm around."""
    return n.x - n.stub["L"] - pad, n.y - pad, n.x + n.w + n.stub["R"] + pad, n.y + n.h + pad


def _spread(ns: list[Node], pads: list[float], P: np.ndarray, gap: float, rounds: int, snap: bool) -> None:
    """Moves the boxes (centres P) apart, pairwise along the axis of the smaller overlap, until none overlaps by more than `gap` less than their pads."""
    hw = np.array([(n.w + n.stub["L"] + n.stub["R"]) / 2 + p for n, p in zip(ns, pads)])
    hh = np.array([n.h / 2 + p for n, p in zip(ns, pads)])
    sh = np.array([(n.stub["R"] - n.stub["L"]) / 2 for n in ns])      # the stubs make the box off-centre
    idx = np.arange(len(ns))
    for _ in range(rounds):
        C = P.copy(); C[:, 0] += sh
        dx = C[None, :, 0] - C[:, None, 0]; dy = C[None, :, 1] - C[:, None, 1]       # [i, j]: from i to j
        ox = hw[:, None] + hw[None, :] - np.abs(dx) - gap; oy = hh[:, None] + hh[None, :] - np.abs(dy) - gap
        hit = (ox > 0) & (oy > 0) & (idx[:, None] != idx[None, :])
        if not hit.any(): break
        sx = np.where(dx != 0, np.sign(dx), np.where(idx[:, None] < idx[None, :], 1.0, -1.0)); sy = np.where(dy != 0, np.sign(dy), np.where(idx[:, None] < idx[None, :], 1.0, -1.0))  # noqa: E501
        alongx = hit & (ox <= oy); alongy = hit & (ox > oy)
        F = np.zeros_like(P)
        F[:, 0] = -(np.where(alongx, ox * sx, 0.0)).sum(1) / 2 * 0.55
        F[:, 1] = -(np.where(alongy, oy * sy, 0.0)).sum(1) / 2 * 0.55
        P += np.clip(F, -40, 40)
        if snap: P[:] = np.round(P / GRID) * GRID


def _place(ns: list[Node], edges: list[tuple[int, int, float]], x0: np.ndarray) -> np.ndarray:
    """Centres of the boxes: springs along the wires (weighted), a pull from the left for the sources, overlap pushed apart; fixed iteration count."""
    n = len(ns)
    P = x0.copy()
    deg = np.zeros(n)
    for i, j, w in edges: deg[i] += w; deg[j] += w
    pads = [6.0 + 2.5 * min(d, 40) for d in deg]
    ei = np.array([e[0] for e in edges], dtype=int); ej = np.array([e[1] for e in edges], dtype=int); ew = np.array([e[2] for e in edges])
    for it in range(500):
        step = 0.8 * (1 - it / 700)
        F = np.zeros_like(P)
        if len(edges):
            d = P[ej] - P[ei]
            np.add.at(F, ei, d * ew[:, None]); np.add.at(F, ej, -d * ew[:, None])
        F /= np.maximum(deg, 1)[:, None]                     # a node moves towards the weighted mean of its neighbours
        P += F * step
        P -= (P - x0.mean(0)) * 0.03                     # a faint gravity: a part with no wire stays near the others
        _spread(ns, pads, P, 2.0, 1, False)
    _spread(ns, pads, P, 2.0, 300, False)
    P[:] = np.round(P / GRID) * GRID
    _spread(ns, pads, P, 0.0, 300, True)
    return P


# ---------------------------------------------------------------- routing
class Grid:
    """The routing grid (5 mm): blocked cells (symbols, stubs), reserved cells (a pin's first cell belongs to its wire), and what routed wires use of the rest."""

    def __init__(s, x0: float, y0: float, x1: float, y1: float) -> None:
        s.x0, s.y0 = x0, y0
        s.W, s.H = int((x1 - x0) / GRID) + 3, int((y1 - y0) / GRID) + 3
        s.blk = bytearray(s.W * s.H)
        s.nores = [0] * (s.W * s.H)
        s.use: dict[int, dict[str, int]] = {}      # cell -> wire -> what it uses of it
        s.paths: dict[str, list[int]] = {}
        s.spent = 0                                # cells looked at by the search so far (a budget, so the drawing time stays bounded and deterministic)
        s.occ = bytearray(s.W * s.H)               # 1 a wire passes horizontally, 2 vertically, 4 a wire ends or turns here
        s.ids: dict[str, int] = {}                 # wire id -> a number (the reservations hold numbers)
        s.res = [0] * (s.W * s.H)                  # the two cells in front of a pin belong to its wire ...
        s.res2 = [0] * (s.W * s.H)                 # ... and the row farther out: nobody else runs along it or turns on it (crossing is fine)
        s.res1 = [0] * (s.W * s.H)                 # the first cell only: the reservation of a wire that cannot get through otherwise
        for ix in range(s.W): s.blk[ix] = s.blk[(s.H - 1) * s.W + ix] = 1
        for iy in range(s.H): s.blk[iy * s.W] = s.blk[iy * s.W + s.W - 1] = 1
        s.delta = (1, -1, s.W, -s.W)                # E W S N

    def cell(s, x: float, y: float) -> int:
        return (round((y - s.y0) / GRID) + 1) * s.W + round((x - s.x0) / GRID) + 1

    def xy(s, c: int) -> tuple[float, float]:
        return s.x0 + (c % s.W - 1) * GRID, s.y0 + (c // s.W - 1) * GRID

    def block(s, x0: float, y0: float, x1: float, y1: float) -> None:
        for iy in range(round((y0 - s.y0) / GRID) + 1, round((y1 - s.y0) / GRID) + 2):
            for ix in range(round((x0 - s.x0) / GRID) + 1, round((x1 - s.x0) / GRID) + 2): s.blk[iy * s.W + ix] = 1

    def route(s, wid: str, start: int, d0: int, goal: int, dg: int, margin: int, strict: bool = True, cap: int = 1500000) -> list[tuple[int, int]] | None:
        """Cells (with the direction of travel) from `start` (leaving in d0) to `goal` (arriving in dg); None when there is no way inside the window."""
        W, blk, occ, res, delta = s.W, s.blk, s.occ, s.res if strict else s.res1, s.delta
        res2 = s.res2 if strict else s.nores
        me = s.ids.setdefault(wid, len(s.ids) + 1)
        sx, sy, gx, gy = start % W, start // W, goal % W, goal // W
        lo_x, hi_x, lo_y, hi_y = min(sx, gx) - margin, max(sx, gx) + margin, min(sy, gy) - margin, max(sy, gy) + margin
        g0 = {start * 4 + d0: 0}
        heap = [(HW * (abs(sx - gx) + abs(sy - gy)), 0, start * 4 + d0)]
        came: dict[int, int] = {}
        goal_state = goal * 4 + dg
        n = 0
        while heap:
            f, ng, st = heapq.heappop(heap)
            g = -ng
            if g > g0.get(st, 1 << 30): continue
            if st == goal_state:
                path = [st]
                while path[-1] in came: path.append(came[path[-1]])
                s.spent += n
                return [(q >> 2, q & 3) for q in reversed(path)]
            n += 1
            if n > cap: s.spent += n; return None
            c, d = st >> 2, st & 3
            nxt = []
            c2 = c + delta[d]
            if not blk[c2] and res[c2] in (0, me) and (d > 1 or res2[c2] in (0, me)) and lo_x <= c2 % W <= hi_x and lo_y <= c2 // W <= hi_y:
                b = occ[c2]
                if d < 2: ok, cross = not (b & 5), b & 2
                else: ok, cross = not (b & 6), b & 1
                if ok: nxt.append((c2 * 4 + d, 1 + (CROSS if cross else 0)))
            if not occ[c] and res[c] in (0, me) and res2[c] in (0, me):     # turn here: a free cell only
                for nd in ((2, 3) if d < 2 else (0, 1)): nxt.append((c * 4 + nd, BEND))
            for st2, cost in nxt:
                g2 = g + cost
                if g2 < g0.get(st2, 1 << 30):
                    g0[st2] = g2; came[st2] = st
                    q = st2 >> 2
                    heapq.heappush(heap, (g2 + HW * (abs(q % W - gx) + abs(q // W - gy)), -g2, st2))
        s.spent += n
        return None

    def probe(s, wid: str, start: int, d0: int, goal: int, dg: int, strict: bool = True) -> tuple[int, list[tuple[int, int]]] | None:
        """The cheapest wire of the shape out - across - in (one vertical run) or a straight run, tried column by column from the middle; (crossings, cells)."""
        W, blk, occ = s.W, s.blk, s.occ
        res, res2 = (s.res, s.res2) if strict else (s.res1, s.nores)
        me = s.ids.setdefault(wid, len(s.ids) + 1)
        sx, sy, gx, gy = start % W, start // W, goal % W, goal // W
        dx0, dxg = (1 if d0 == 0 else -1), (1 if dg == 0 else -1)

        def hrun(y: int, x0: int, x1: int) -> int:
            """Crossings of a horizontal run from x0 to x1 inclusive, -1 when a cell is not free for it."""
            n = 0
            for x in range(min(x0, x1), max(x0, x1) + 1):
                c = y * W + x
                b = occ[c]
                if blk[c] or res[c] not in (0, me) or res2[c] not in (0, me) or b & 5: return -1
                n += b & 2 > 0
            return n

        def turn(c: int) -> bool:
            return not blk[c] and not occ[c] and res[c] in (0, me) and res2[c] in (0, me)

        def make(xc: int) -> list[tuple[int, int]]:
            out = [(sy * W + x, d0) for x in range(sx, xc + dx0, dx0)]
            if sy != gy:
                dv = 2 if gy > sy else 3
                out.append((sy * W + xc, dv))
                out += [(y * W + xc, dv) for y in range(sy + (1 if gy > sy else -1), gy, 1 if gy > sy else -1)]
                out += [(gy * W + xc, dv), (gy * W + xc, dg)]
            out += [(gy * W + x, dg) for x in range(xc + dxg, gx + dxg, dxg)]
            return out
        if sy == gy:
            if d0 == dg and (gx - sx) * dx0 >= 0 and (n := hrun(sy, sx, gx)) >= 0: return n, [(sy * W + x, d0) for x in range(sx, gx + dx0, dx0)]
            return None
        lo, hi = (sx, gx - 1) if dx0 == dxg == 1 else (gx + 1, sx) if dx0 == dxg == -1 else (max(sx, gx + 1), max(sx, gx + 1) + 12) if dx0 == 1 else (min(sx, gx - 1) - 12, min(sx, gx - 1))  # noqa: E501
        if lo > hi: return None
        mid = (lo + hi) // 2
        best: tuple[int, int] | None = None
        step = 1 if gy > sy else -1
        for xc in sorted(range(lo, hi + 1), key=lambda x: (abs(x - mid), x))[:60]:
            if not turn(sy * W + xc) or not turn(gy * W + xc): continue
            a, b = hrun(sy, sx, xc), hrun(gy, xc, gx)
            if a < 0 or b < 0: continue
            n = a + b
            for y in range(sy + step, gy, step):
                c = y * W + xc
                if blk[c] or res[c] not in (0, me) or occ[c] & 6: n = -1; break
                n += occ[c] & 1 > 0
            if n >= 0 and (best is None or n < best[0]):
                best = (n, xc)
                if n == 0: break
        return (best[0], make(best[1])) if best else None

    def take(s, wid: str, path: list[tuple[int, int]]) -> None:
        s.paths[wid] = [c for c, _ in path]
        for k, (c, d) in enumerate(path):
            end = k in (0, len(path) - 1) or path[k - 1][1] != d
            bits = 4 if end else (1 if d < 2 else 2)
            s.use.setdefault(c, {})[wid] = s.use.get(c, {}).get(wid, 0) | bits
            s.occ[c] |= bits

    def release(s, wid: str) -> None:
        """Takes a routed wire off the grid again (to route another one first)."""
        for c in set(s.paths.pop(wid)):
            u = s.use[c]
            u.pop(wid)
            s.occ[c] = 0
            for b in u.values(): s.occ[c] |= b

    def near(s, cells: list[int], r: int) -> list[str]:
        """The routed wires with a cell within r cells (a square) of one of `cells`."""
        out: set[str] = set()
        for c in cells:
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1): out.update(s.use.get(c + dy * s.W + dx, ()))
        return sorted(out)


def _label_lines(w: Elem) -> list[str]:
    return [R.label_text(w)]


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
    wires = [dict(w, dash=w["cls"].startswith("CAN")) for w in sc["wires"] if not (owner[w["a"]] in gnd and owner[w["b"]] in gnd)]
    cnt: dict[str, int] = defaultdict(int)
    for w in wires:
        for e in "ab": cnt[w[e]] += 1
    env = Env(cnt)
    nodes = {iid: Node(iid, it) for iid, it in its.items()}
    order = sorted(nodes)
    edges: list[Edge] = []
    stubs: list[tuple[Elem, str, str, str]] = []      # (wire, node, key, side wanted later) of a wire whose other end is ground
    ends_of: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for w in wires:
        u, v = owner[w["a"]], owner[w["b"]]
        gu, gv = u in gnd, v in gnd
        ku = env.key_at(nodes[u], w["a"], w["id"]) if not gu else ""
        kv = env.key_at(nodes[v], w["b"], w["id"]) if not gv else ""
        if gu: stubs.append((w, v, kv, "b"))
        elif gv: stubs.append((w, u, ku, "a"))
        else: edges.append((w, u, ku, v, kv)); adj[u].append((v, w["a"])); adj[v].append((u, w["b"]))
        for nid, key, ref, g in ((u, ku, w["a"], gu), (v, kv, w["b"], gv)):
            if not g: ends_of[nid].append((key, "R", w["id"], ref))
    stub_of = {(w["id"], nid): k for w, nid, k, _ in stubs}
    # ---- levels (for the first picture only): distance from the batteries
    lvl: dict[str, int] = {}
    todo: deque[str] = deque(i for i in order if nodes[i].sym == "battery")
    for q in todo: lvl[q] = 0
    for start in [None, *order]:
        if start is not None:
            if start in lvl: continue
            lvl[start] = 0; todo.append(start)
        while todo:
            u = todo.popleft()
            for v, _ in sorted(adj[u]):
                if v not in lvl: lvl[v] = lvl[u] + 1; todo.append(v)

    def set_sides(pos: dict[str, tuple[float, float]], flips: bool) -> None:
        """The side every end faces: towards where its wire goes; in-line parts are mirrored as a whole; ground stubs go to the side with fewer wires."""
        for iid in order:
            n = nodes[iid]
            ends = []
            for key, _, wid, ref in ends_of[iid]:
                o = next((e for e in edges if e[0]["id"] == wid), None)
                other = None
                if o is not None: other = o[3] if o[1] == iid and o[2] == key else o[1]
                if other is None: side = "G"                         # a ground stub: decided below
                elif other == iid: side = "R"
                else: side = "R" if pos[other][0] > pos[iid][0] or (pos[other][0] == pos[iid][0] and pos[other][1] > pos[iid][1]) else "L"
                ends.append((key, side, wid, ref))
            nl, nr = sum(e[1] == "L" for e in ends), sum(e[1] == "R" for e in ends)
            gs = "L" if nr > nl else "R"
            ends = [(k, gs if s == "G" else s, wid, ref) for k, s, wid, ref in ends]
            n.ends = ends
            if n.sym in INLINE and flips:
                defs = env.defaults(n.item)
                grp = {p["anchor"]: int(defs.get(p["anchor"], "L") == "R") for b in n.item["blocks"] for p in b["pins"]}
                mean: dict[int, list[float]] = {0: [], 1: []}
                for k, s_, wid, ref in ends:
                    o = next((e for e in edges if e[0]["id"] == wid), None)
                    if o is not None and ref in grp: mean[grp[ref]].append(pos[o[3] if o[1] == iid else o[1]][0])
                m0 = sum(mean[0]) / len(mean[0]) if mean[0] else None
                m1 = sum(mean[1]) / len(mean[1]) if mean[1] else None
                cxn = pos[iid][0]
                env.flip[iid] = m0 is not None and ((m1 is not None and m0 > m1) or (m1 is None and m0 > cxn))
                f = env.flip[iid]
                n.ends = [(k, ("R" if f else "L") if grp.get(ref, 0) == 0 else ("L" if f else "R"), wid, ref) for k, s_, wid, ref in ends]

    def stub_len(w: Elem) -> float:
        return ceil_to(text_w(R.label_text(w), SIZE) + 6, GRID) + MARK

    def measure() -> None:
        for n in nodes.values():
            env.build(n, {})
            n.stub = {"L": 0.0, "R": 0.0}
        for w, nid, key, _ in stubs:
            n = nodes[nid]
            side = next(s for k, s, wid, _ in n.ends if k == key and wid == w["id"])
            side = n.act.get(key, side)
            n.stub[side] = max(n.stub[side], stub_len(w))
    pos0 = {i: (lvl[i] * 160.0, 0.0) for i in order}
    set_sides(pos0, False)
    measure()
    col_y: dict[int, float] = defaultdict(float)
    for i in order:
        n = nodes[i]
        n.x = lvl[i] * 160.0; n.y = col_y[lvl[i]]; col_y[lvl[i]] += n.h + 25
    for i in order:
        nodes[i].y -= col_y[lvl[i]] / 2
    idx = {i: k for k, i in enumerate(order)}
    ns = [nodes[i] for i in order]
    wmap: dict[tuple[int, int], float] = defaultdict(float)
    for w, u, ku, v, kv in edges:
        if u != v: wmap[tuple(sorted((idx[u], idx[v])))] += 1.0       # type: ignore[index]
    el = [(i, j, wt) for (i, j), wt in sorted(wmap.items())]
    P = _place(ns, el, np.array([[n.x + n.w / 2, n.y + n.h / 2] for n in ns], dtype=float))
    scale = 1.0
    sheet: dict[str, Any] = {}
    for attempt in range(4):
        Pa = (P - P.mean(0)) * scale + P.mean(0)
        pos = {i: (float(Pa[idx[i], 0]), float(Pa[idx[i], 1])) for i in order}
        set_sides(pos, True)
        measure()
        Q = Pa.copy()
        for k, n in enumerate(ns): Q[k] = (pos[n.id][0], pos[n.id][1])
        _spread(ns, [6.0 + 2.5 * min(len(ends_of[n.id]), 40) for n in ns], Q, 2.0, 300, False)
        Q[:] = np.round(Q / GRID) * GRID
        _spread(ns, [6.0 + 2.5 * min(len(ends_of[n.id]), 40) for n in ns], Q, 0.0, 300, True)
        for k, n in enumerate(ns): n.x, n.y = float(Q[k, 0] - n.w / 2) // GRID * GRID, float(Q[k, 1] - n.h / 2) // GRID * GRID
        x_lo = min(_box(n, 0)[0] for n in ns) - 150; y_lo = min(_box(n, 0)[1] for n in ns) - 150
        x_hi = max(_box(n, 0)[2] for n in ns) + 150; y_hi = max(_box(n, 0)[3] for n in ns) + 150
        x_lo, y_lo = math.floor(x_lo / GRID) * GRID, math.floor(y_lo / GRID) * GRID
        grid = Grid(x_lo, y_lo, x_hi, y_hi)
        for n in ns:
            grid.block(n.x, n.y, n.x + n.w, n.y + n.h)
        anchor_pt: dict[tuple[str, str], tuple[float, float, str]] = {}
        for n in ns:
            for kk_, (ox, oy) in n.off.items(): anchor_pt[n.id, kk_] = (n.x + ox, n.y + oy, n.act[kk_])
        d_out = {"L": 1, "R": 0}
        stubw: dict[str, list[Any]] = {}
        for w, nid, key, _ in stubs:                         # ground stubs: straight out, a mark at the end
            ax, ay, side = anchor_pt[nid, key]
            ln = stub_len(w)
            ex = ax + ln - MARK if side == "R" else ax - ln + MARK
            c0, c1 = sorted((grid.cell(ax, ay), grid.cell(ex + (MARK if side == "R" else -MARK), ay)))
            for c in range(c0, c1 + 1): grid.blk[c] = 1
            stubw[w["id"]] = [(ax, ay), (ex, ay), side]
        for w, u, ku, v, kv in edges:
            for nid, key in ((u, ku), (v, kv)):
                ax, ay, side = anchor_pt[nid, key]
                free = 0                        # cells in front of the pin before a symbol: the facing pin gets the other half
                while free < 14 and not grid.blk[grid.cell(ax + (free + 1) * (GRID if side == "R" else -GRID), ay)]: free += 1
                for k in range(1, max(2, free // 2) + 1):
                    cc = grid.cell(ax + k * (GRID if side == "R" else -GRID), ay)
                    wn = grid.ids.setdefault(w["id"], len(grid.ids) + 1)
                    if k <= 2: grid.res[cc] = wn
                    else: grid.res2[cc] = wn
                    if k == 1: grid.res1[cc] = wn
        ok = True
        wp: dict[str, Any] = {}
        todo_w = sorted(edges, key=lambda e: (abs(anchor_pt[e[1], e[2]][0] - anchor_pt[e[3], e[4]][0]) + abs(anchor_pt[e[1], e[2]][1] - anchor_pt[e[3], e[4]][1]), _natural(e[0]["id"])))  # noqa: E501
        by_id = {e[0]["id"]: e for e in edges}
        queue = deque(todo_w)
        late = 0
        tries: dict[str, int] = defaultdict(int)
        while queue:
            item = queue.popleft()
            w, u, ku, v, kv = item
            ax, ay, sa = anchor_pt[u, ku]
            bx, by, sb = anchor_pt[v, kv]
            ca = grid.cell(ax + (GRID if sa == "R" else -GRID), ay)
            cb = grid.cell(bx + (GRID if sb == "R" else -GRID), by)
            da, db = d_out[sa], d_out[sb] ^ 1               # leave a in its side's direction; arrive at b moving towards its anchor
            path, pr = None, grid.probe(w["id"], ca, da, cb, db)
            if pr and pr[0] <= 8: path = pr[1]
            for strict, margin, cap in (() if path or grid.spent > BUDGET else ((True, 10, 100), (True, 30, 150), (True, 80, 200), (False, 80, 200), (False, 10000, 200))):  # noqa: E501
                path = grid.route(w["id"], ca, da, cb, db, margin, strict, cap * (1 + 6 * tries[w["id"]]) * (abs(ca % grid.W - cb % grid.W) + abs(ca // grid.W - cb // grid.W) + 30))  # noqa: E501
                if path: break
            if path is None and pr: path = pr[1]
            if path is None and grid.spent > BUDGET:        # the search budget is used up: ignore the other wires (the gates may then fail) rather than run on
                saved, grid.occ = grid.occ, bytearray(len(grid.occ))
                path = grid.route(w["id"], ca, da, cb, db, 10000, False, 400000)
                grid.occ = saved
                late += path is not None
            if path is None:                                # rip up what is near its ends, route this wire first, then the others again
                victims = grid.near([ca, cb], (3, 6, 10, 10)[tries[w["id"]]]) if tries[w["id"]] < 4 else []
                if not victims: ok = False; break
                tries[w["id"]] += 1
                for vid in victims:
                    grid.release(vid); wp.pop(vid, None); queue.append(by_id[vid])
                queue.appendleft(item)
                continue
            grid.take(w["id"], path)
            wp[w["id"]] = R.trace([(ax, ay)] + [grid.xy(c) for c, _ in path] + [(bx, by)])
        if ok: break
        scale *= 1.25
    else:
        raise RuntimeError("overview: a wire has no route")
    # ---- geometry
    syms: list[Any] = []; texts: list[Any] = []; out: list[Any] = []
    for n in sorted(ns, key=lambda n: n.id):
        sy, tx = env.symfor(n, n.x, n.y)
        syms.append(sy); texts += tx
    for w, nid, key, _ in stubs:
        (ax, ay), (ex, _), side = stubw[w["id"]]
        pts = [[ax, ay], [ex, ay]]
        a_key = key
        mk = _ground_mark(ex, ay, w["id"], w["a"] if stub_of.get((w["id"], nid)) == key and owner[w["a"]] in gnd else w["b"], side)
        syms.append(mk)
        wp[w["id"]] = pts if side == "R" else pts
        stubw[w["id"]].append(a_key)
    for w in wires:
        pts = wp[w["id"]]
        gu, gv = owner[w["a"]] in gnd, owner[w["b"]] in gnd
        if w["id"] in stubw:
            (ax, ay), (ex, ey), side, key = stubw[w["id"]]
            mkey = f"{w['a'] if gu else w['b']}#{w['id']}"
            if gu: pts, a, b = [[ex, ay], [ax, ay]], mkey, key
            else: pts, a, b = [[ax, ay], [ex, ay]], key, mkey
        else:
            a, b = env.key_at(nodes[owner[w["a"]]], w["a"], w["id"]), env.key_at(nodes[owner[w["b"]]], w["b"], w["id"])
        out.append(dict(id=w["id"], model=w["model"], label=w["label"], gauge=w["gauge"], colour=w["colour"], hex=w["hex"], weight=w["weight"], points=[list(p) for p in pts],  # noqa: E501
                        a=a, b=b, pair=w["pair"], shield=w["shield"], fault=w["fault"], dash=w["dash"]))
    # ---- shift everything to the sheet's drawing area, then labels
    xs = [s["x"] for s in syms] + [s["x"] + s["w"] for s in syms] + [p[0] for w in out for p in w["points"]]
    ys = [s["y"] for s in syms] + [s["y"] + s["h"] for s in syms] + [p[1] for w in out for p in w["points"]]
    dx, dy = MARGIN + PAD - min(xs), MARGIN + PAD - min(ys)
    for s in syms:
        s["x"] += dx; s["y"] += dy
        for a in s["anchors"]: a["x"] += dx; a["y"] += dy
        for q in s["prims"]:
            for kx in ("x", "x1", "x2", "cx"):
                if kx in q: q[kx] += dx
            for ky in ("y", "y1", "y2", "cy"):
                if ky in q: q[ky] += dy
            if "points" in q: q["points"] = [[px + dx, py + dy] for px, py in q["points"]]
    for t in texts: t["x"] += dx; t["y"] += dy
    for w in out: w["points"] = [[p[0] + dx, p[1] + dy] for p in w["points"]]
    unlabeled = _labels(syms, out, texts)
    W = max(330.0, ceil_to(max(xs) - min(xs) + 2 * (MARGIN + PAD)))
    H = ceil_to(max(ys) - min(ys) + 2 * (MARGIN + PAD) + STRIP_H)
    size = f"{W:g}x{H:g}"
    info = dict(title=f"{sc['title']} overview", scope="overview", project=sc["project"], revision=meta.get("revision", ""), date=meta.get("date", ""),
                drawn_by=meta.get("drawn_by", ""), source=meta.get("source", ""))
    notes = [f"{len(out)} wires, each drawn once with label, gauge (AWG) and colour code; dashed wires are CAN.",
             "A ground mark at the end of a short stub is that wire's end on the ground bus. Parts wired together are placed next to each other."]
    sheet = dict(n=1, of=1, size=size, w_mm=W, h_mm=H, grid_mm=5.0, symbols=syms, wires=out, texts=texts, flags=[], rules=[], table=dict(sheet=1, rows=[]))
    sheet.update(S.furniture(info, size, 1, 1, list(dict.fromkeys(s["kind"] for s in syms)), notes))
    sheet["late"] = late                                  # wires routed after the budget ran out
    sheet["unlabeled"] = unlabeled                         # prototype counters
    sheet["late"] = late
    return dict(version=1, drawing=info, sheets=[sheet])  # type: ignore[typeddict-item,return-value,list-item]


def _ground_mark(x: float, y: float, wid: str, ref: str, side: str) -> Elem:
    """A ground mark on its side at (x, y) (the end of a stub): three bars across the wire; its anchor takes the wire from `side`'s inside."""
    d = 1 if side == "R" else -1
    pr = [dict(kind="line", stroke="normal", x1=x + d * dx, y1=y - h, x2=x + d * dx, y2=y + h) for dx, h in ((1.5, 2.0), (3.0, 1.2), (4.5, 0.5))]
    pr.append(dict(kind="line", stroke="normal", x1=x, y1=y, x2=x + d * 1.5, y2=y))
    bx = x if side == "R" else x - MARK
    return dict(id=f"ground:{wid}", kind="ground", model=ref, x=bx, y=y - 2.5, w=MARK, h=5.0, anchors=[dict(id=f"{ref}#{wid}", model=ref, x=x, y=y, side="L" if side == "R" else "R")], prims=pr)  # noqa: E501


def _labels(syms: list[Any], wires: list[Any], texts: list[Any]) -> int:
    """Puts every wire's label (`L01 22 AWG RD`) above a free stretch of the wire, at both ends of a long wire and about every EVERY mm in between; a label
    that finds no stretch is stacked on two lines, or put below. Appends the texts; returns the number of wires that got none."""
    segs: list[tuple[int, float, float, float, float]] = []      # (wire index, x0, y0, x1, y1) normalised
    for k, w in enumerate(wires):
        p = w["points"]
        segs += [(k, min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])) for a, b in zip(p, p[1:])]
    H = [s for s in segs if s[2] == s[4]]; V = [s for s in segs if s[1] == s[3]]
    cross: list[tuple[float, float]] = []
    for h in H:
        for v in V:
            if v[0] != h[0] and h[1] < v[1] < h[3] and v[2] < h[2] < v[4]: cross.append((v[1], h[2]))
    cell = 40.0
    buckets: dict[tuple[int, int], list[tuple[str, Any]]] = defaultdict(list)

    def put(kind: str, item: Any, x0: float, y0: float, x1: float, y1: float) -> None:
        for i in range(int(x0 // cell), int(x1 // cell) + 1):
            for j in range(int(y0 // cell), int(y1 // cell) + 1): buckets[i, j].append((kind, item))
    for s in segs: put("seg", s, s[1], s[2], s[3], s[4])
    for s in syms: put("box", (s["x"], s["y"], s["x"] + s["w"], s["y"] + s["h"]), s["x"], s["y"], s["x"] + s["w"], s["y"] + s["h"])
    for t in texts: put("box", (t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"]), t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"])
    for c in cross: put("cross", c, c[0], c[1], c[0], c[1])

    def free(k: int, bx0: float, by0: float, bx1: float, by1: float) -> bool:
        seen: set[int] = set()
        for i in range(int((bx0 - 3) // cell), int((bx1 + 3) // cell) + 1):
            for j in range(int((by0 - 3) // cell), int((by1 + 3) // cell) + 1):
                for kind, it in buckets.get((i, j), ()):
                    if id(it) in seen: continue
                    seen.add(id(it))
                    if kind == "box":
                        if it[0] < bx1 + 0.3 and bx0 < it[2] + 0.3 and it[1] < by1 + 0.3 and by0 < it[3] + 0.3: return False
                    elif kind == "seg":
                        if it[0] == k and False: continue
                        if it[1] < bx1 + 0.3 and bx0 < it[3] + 0.3 and it[2] < by1 + 0.3 and by0 < it[4] + 0.3 and not (it[0] == k and it[2] == it[4] and it[2] >= by1 - 0.3 and it[2] <= by1 + 0.6): return False  # noqa: E501
                    elif bx0 - 3 < it[0] < bx1 + 3 and by0 - 3 < it[1] < by1 + 3: return False
        return True
    unlabeled = 0
    new: list[Any] = []

    def add(k: int, lines: list[str], x: float, y: float, below: bool) -> bool:
        """The lines stacked above (or below) the horizontal stretch at y, the first line at x."""
        ts = []
        for r, ln in enumerate(lines):
            cy = y - 2.5 - 4.5 * (len(lines) - 1 - r) if not below else y + 2.5 + 4.5 * r
            ts.append(S.text(ln, x, cy, "left", "wire", model=wires[k]["model"]))
        bx0, by0 = min(t["x"] for t in ts), min(t["y"] for t in ts)
        bx1, by1 = max(t["x"] + t["w"] for t in ts), max(t["y"] + t["h"] for t in ts)
        if not free(k, bx0, by0, bx1, by1): return False
        for t in ts:
            new.append(t); put("box", (t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"]), t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"])
        return True
    for k, w in enumerate(wires):
        lab = R.label_text(w)
        words = lab.split(" ", 1)
        two = [words[0], words[1]] if len(words) == 2 else [lab]
        pts = w["points"]
        length = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(pts, pts[1:]))
        n_lab = 1 if length <= LONG else max(2, round(length / EVERY) + 1)
        targets = [length * i / (n_lab - 1) if n_lab > 1 else 0.0 for i in range(n_lab)]
        runs, run0 = [], 0.0                                # horizontal stretches: (arc start, x0, x1, y, increasing)
        for a, b in zip(pts, pts[1:]):
            if a[1] == b[1] and a[0] != b[0]: runs.append((run0, min(a[0], b[0]), max(a[0], b[0]), a[1], b[0] > a[0]))
            run0 += abs(a[0] - b[0]) + abs(a[1] - b[1])
        got = 0
        for ti, t in enumerate(targets):
            done = False
            for lines, below in (([lab], False), (two, False), ([lab], True), (two, True)):
                tw = max(text_w(ln, SIZE) for ln in lines)
                cand = []
                for arc0, x0, x1, y, inc in runs:
                    if x1 - x0 < 10: continue
                    need = min(0.5 * tw, x1 - x0)                # the label overlaps its stretch by this much, the rest may overhang the end
                    xx = x0 - tw + need
                    while xx <= x1 - need + 1e-6:
                        mid = (xx + tw / 2 - x0) if inc else (x1 - xx - tw / 2)
                        cand.append((abs(arc0 + mid - t) + (0.0 if x0 <= xx and xx + tw <= x1 else 30.0), xx, y)); xx += 2.5
                for _, xx, y in sorted(cand):
                    if add(k, lines, xx, y, below): done = True; break
                if done: break
            got += done
            if not done and ti == 0: break
        if not got: unlabeled += 1
    texts += new
    return unlabeled
