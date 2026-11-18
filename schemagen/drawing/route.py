"""Orthogonal wire routing on the grid (docs/drawing-model.md): wires run horizontally from their anchor, take a vertical track in
the channel between two columns of symbols where they change row, and go on horizontally; a wire that passes columns rides a lane
through each. `tracks` orders the vertical jogs of one channel (few crossings, no collinear overlap, no T junction), `trace` builds
a wire's points, `labels` puts the wire texts just above horizontal stretches where nothing else is."""
from __future__ import annotations

import re
from typing import Any

from . import symbols as S
from .style import SIZE, text_w

BAD = 1000  # an ordering that would lay two wires on top of each other or end one on the side of another


def _hit(y: float, lo: float, hi: float) -> int:
    """Cost of a horizontal stretch at y against a vertical jog spanning [lo, hi]: a crossing, or (at an end) a T junction."""
    return BAD if y in (lo, hi) else int(lo < y < hi)


def _tracks(jog: list[tuple[str, float, float]]) -> tuple[dict[str, int], list[tuple[str, str]]]:
    """Tracks for the given jogs, and the pairs the chosen order still lays on top of each other (no order does, or the forced orders form a cycle)."""
    span = {w: (min(a, b), max(a, b)) for w, a, b in jog}
    ends = {w: (a, b) for w, a, b in jog}
    base = {w: w.partition("|")[0] for w in ends}
    memo: dict[tuple[str, str], int] = {}  # the ordering asks for the same pair again and again

    def cost(p: str, q: str) -> int:  # p's track is left of q's
        if (p, q) not in memo: memo[p, q] = 0 if base[p] == base[q] else _hit(ends[p][1], *span[q]) + _hit(ends[q][0], *span[p])
        return memo[p, q]
    ws = [w for w, _, _ in jog]
    must = {p: [q for q in ws if q != p and cost(p, q) < BAD <= cost(q, p)] for p in ws}   # p must be left of each q
    pending = {q: sum(q in v for v in must.values()) for q in ws}
    order: list[str] = []
    while len(order) < len(ws):                    # a topological order of the forced pairs, the most left-leaning wire first
        rest = [w for w in ws if w not in order]
        ready = [w for w in rest if not pending[w]] or rest
        w = min(ready, key=lambda p: (sum(cost(p, q) - cost(q, p) for q in rest if q != p), ends[p][0] + ends[p][1], p))
        order.append(w)
        for q in must[w]: pending[q] -= 1
    for _ in range(len(order) ** 2 + 1):           # then adjacent swaps that lower the cost
        for i in range(len(order) - 1):
            if cost(order[i + 1], order[i]) < cost(order[i], order[i + 1]): order[i], order[i + 1] = order[i + 1], order[i]; break
        else: break
    t: dict[str, int] = {}
    for i, w in enumerate(order):
        t[w] = 1 + max((t[u] for u in order[:i] if span[u][0] <= span[w][1] and span[w][0] <= span[u][1]), default=-1)
    bad = [(order[i], order[j]) for i in range(len(order)) for j in range(i + 1, len(order)) if cost(order[i], order[j]) >= BAD]
    return t, bad


def tracks(hops: list[tuple[str, float, float]]) -> tuple[dict[str, int], dict[str, float], int]:
    """Track numbers (0, 1, ... from the left) of the wires in one channel that change row: hops are (wire id, y at the left, y at the right).
    The order minimises crossings (pairwise cost, adjacent swaps); wires whose vertical spans do not meet share a track. Two wires that swap
    rows exactly (one goes p to q, the other q to p) cannot be kept apart by any order: the later one gets a dogleg, a middle row `ym` and two
    tracks, `id|1` (from the left row to ym) and `id|2` (from ym to the right row). Returns tracks, doglegs {id: ym} and the pairs left."""
    jog = sorted(((w, a, b) for w, a, b in hops if a != b), key=lambda h: (h[1] + h[2], h[0]))
    dog: dict[str, float] = {}
    for _ in range(len(jog) + 1):
        cur = [(w, a, b) for w, a, b in jog if w not in dog]
        for w, a, b in jog:
            if w in dog: cur += [(f"{w}|1", a, dog[w]), (f"{w}|2", dog[w], b)]
        t, bad = _tracks(cur)
        todo = sorted({max(x, y) for x, y in bad if "|" not in x and "|" not in y} - set(dog))
        if not todo: break
        w = todo[0]
        a, b = next((a, b) for u, a, b in jog if u == w)
        used = {y for _, p, q in hops for y in (p, q)} | set(dog.values())
        mid = (a + b) / 2
        rows = [float(y) for y in range(int(min(a, b)) - 100, int(max(a, b)) + 105, 5) if y not in used and y not in (a, b)]   # a free row, near the middle
        dog[w] = min(rows, key=lambda y: (abs(y - mid) + (0 if min(a, b) < y < max(a, b) else 15), y))
    return t if jog else {}, dog, len(bad) if jog else 0


def trace(pts: list[tuple[float, float]]) -> list[list[float]]:
    """The wire's points without repeated or collinear middle points."""
    out: list[tuple[float, float]] = []
    for p in pts:
        if out and out[-1] == p: continue
        if len(out) >= 2 and ((out[-2][0] == out[-1][0] == p[0]) or (out[-2][1] == out[-1][1] == p[1])): out.pop()
        out.append(p)
    return [[x, y] for x, y in out]


def unit(gauge: str) -> str:
    """`22` -> `22 AWG`; a gauge that is not a number (`TBD`) stays as written."""
    return f"{gauge} AWG" if re.fullmatch(r"\d+(\.\d+)?", gauge or "") else (gauge or "")


def label_text(w: dict[str, Any]) -> str:
    """`L05  22 AWG  RD`: label, then gauge with its unit, then colour code."""
    return " ".join(x for x in (w.get("label", ""), unit(w.get("gauge", "")), w.get("colour", "")) if x)


def _boxes(sh: dict[str, Any]) -> list[tuple[float, float, float, float, str]]:
    """Everything a label must stay clear of: symbols, flags, texts, as (x0, y0, x1, y1, model)."""
    b = [(s["x"], s["y"], s["x"] + s["w"], s["y"] + s["h"], "") for s in sh["symbols"]]
    b += [(f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"], "") for f in sh["flags"]]
    b += [(t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"], "") for t in sh["texts"]]
    return b


def _segments(wires: list[dict[str, Any]]) -> list[tuple[str, float, float, float, float]]:
    out = []
    for w in wires:
        for (xa, ya), (xb, yb) in zip(w["points"], w["points"][1:]): out.append((w["id"], min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)))
    return out


def labels(sh: dict[str, Any], long_mm: float = 150.0) -> list[Any]:
    """A text per wire (two on wires longer than long_mm) placed above a horizontal stretch, preferring the stretches at the ends and
    then the longest; it must overlap no symbol, flag, text or wire. The bounding box is real; the text's model is the wire's."""
    boxes = _boxes(sh)
    segs = _segments(sh["wires"])
    out: list[Any] = []

    def free(x0: float, y0: float, x1: float, y1: float, boxes: list[Any], segs: list[Any]) -> bool:
        if any(x0 < c - 1e-6 and a < x1 - 1e-6 and y0 < d - 1e-6 and b < y1 - 1e-6 for a, b, c, d, _ in boxes): return False
        return not any(x0 < c + 1e-6 and a < x1 - 1e-6 and y0 < d + 1e-6 and b < y1 + 1e-6 for _, a, b, c, d in segs)

    def put(w: dict[str, Any], h: tuple[float, float, float], s: str) -> bool:
        x0, x1, y = h                                             # a horizontal stretch (x0 < x1) at y: the text goes above it
        tw = text_w(s, SIZE)
        n = int((x1 - x0 - tw - 5) / 2.5) + 1 if x1 - x0 >= tw + 5 else 0
        if not n: return False
        t0 = S.text(s, x0 + 2.5, y - 2.5, "left", "wire", model=w["model"])      # every probe sits in this band: only what meets it can be in the way
        near = lambda a, b, c, d: c > x0 and a < x1 + 5 and d > t0["y"] - 1 and b < t0["y"] + t0["h"] + 1  # noqa: E731
        bx, sg = [b for b in boxes if near(*b[:4])], [g for g in segs if near(*g[1:])]
        for k in range(n):
            t = S.text(s, x0 + 2.5 + 2.5 * k, y - 2.5, "left", "wire", model=w["model"])
            if free(t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"], bx, sg):
                out.append(t); boxes.append((t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"], w["model"])); return True
        return False
    for w in sh["wires"]:
        if w.get("silent"): continue
        s = label_text(w)
        pts = w["points"]
        hs = [(min(a[0], b[0]), max(a[0], b[0]), a[1]) for a, b in zip(pts, pts[1:]) if a[1] == b[1] and a[0] != b[0]]
        length = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(pts, pts[1:]))
        want = 2 if length > long_mm and len(hs) > 1 else 1
        mid = sorted(hs[1:-1], key=lambda h: h[0] - h[1])
        cand = [hs[0], hs[-1], *mid] if want == 2 else hs[:1] + sorted(hs[1:], key=lambda h: h[0] - h[1])
        got = 0
        for h in cand:
            got += put(w, h, s)
            if got >= want: break
    return out
