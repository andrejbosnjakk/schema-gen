"""Measurable quality checks over a Geometry (docs/drawing-model.md): pure functions, no rendering. Each returns a list of
findings {check, sheet, ids, msg}; [] means pass. Grid bucketing keeps a sheet with ~500 segments and ~1500 texts fast.

Assumptions (the contract does not say): a text belongs to a symbol when its `model` is the symbol's model or one of its
anchors' models; a text labels a wire when its `model` equals the wire's `model`; a wire may run inside the symbol it
ends on only in its first/last segment, and through the flag it ends on. Diagonal segments are left to off_grid."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterator

from .geometry import MIN_TEXT, Geometry, validate

EPS = 1e-4
Finding = dict[str, Any]
Seg = tuple[Any, int, float, float, float, float]   # wire, index of the segment in it, normalised x0 y0 x1 y1


class _Grid:
    """Bucket boxes by 20 mm cells; near() gives the ids whose cells touch a query box."""
    def __init__(self, cell: float = 20.0) -> None:
        self.c, self.d = cell, defaultdict(list)    # type: float, dict[tuple[int, int], list[int]]

    def _cells(self, x0: float, y0: float, x1: float, y1: float) -> Iterator[tuple[int, int]]:
        c = self.c
        for i in range(int(x0 // c), int(x1 // c) + 1):
            for j in range(int(y0 // c), int(y1 // c) + 1): yield i, j

    def add(self, k: int, x0: float, y0: float, x1: float, y1: float) -> None:
        for cell in self._cells(x0, y0, x1, y1): self.d[cell].append(k)

    def near(self, x0: float, y0: float, x1: float, y1: float) -> set[int]:
        return {k for cell in self._cells(x0, y0, x1, y1) for k in self.d.get(cell, ())}


def _f(check: str, sh: Any, ids: list[str], msg: str) -> Finding:
    return {"check": check, "sheet": sh.get("n"), "ids": ids, "msg": msg}


def _box(b: Any) -> tuple[float, float, float, float]:
    return b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]


def _grid_of(boxes: list[Any]) -> _Grid:
    g = _Grid()
    for k, b in enumerate(boxes): g.add(k, *_box(b))
    return g


def _texts(sh: Any) -> list[Any]:
    return [*sh.get("texts", []), *sh.get("notes", [])]


def _segs(sh: Any) -> list[Seg]:
    """Orthogonal, non-zero segments of the sheet's wires (diagonals are skipped: off_grid reports them)."""
    out: list[Seg] = []
    for w in sh.get("wires", []):
        pts = w.get("points") or []
        for k, ((xa, ya), (xb, yb)) in enumerate(zip(pts, pts[1:])):
            if (abs(xa - xb) < EPS) == (abs(ya - yb) < EPS): continue        # diagonal or zero length
            out.append((w, k, min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)))
    return out


def _horizontal(s: Seg) -> bool:
    return s[5] - s[3] < EPS


def _hits(s: Seg, b: Any) -> bool:
    """True when the segment runs through the interior of box b (touching an edge or a corner is not a hit)."""
    _, _, x0, y0, x1, y1 = s
    bx0, by0, bx1, by1 = _box(b)
    if _horizontal(s): return by0 + EPS < y0 < by1 - EPS and min(x1, bx1) - max(x0, bx0) > EPS
    return bx0 + EPS < x0 < bx1 - EPS and min(y1, by1) - max(y0, by0) > EPS


def _overlap(a: Any, b: Any) -> bool:
    ax0, ay0, ax1, ay1 = _box(a)
    bx0, by0, bx1, by1 = _box(b)
    return ax0 < bx1 - EPS and bx0 < ax1 - EPS and ay0 < by1 - EPS and by0 < ay1 - EPS


def _belongs(t: Any, sym: Any) -> bool:
    """The one place that decides which symbol a text belongs to (by model, see the module docstring)."""
    m = t.get("model", "")
    return bool(m) and (m == sym.get("model") or any(m == a.get("model") for a in sym.get("anchors", [])))


def text_overlaps(g: Geometry) -> list[Finding]:
    """Text boxes (texts and notes) that overlap another text on the same sheet."""
    out: list[Finding] = []
    for sh in g["sheets"]:
        ts = _texts(sh)
        grid = _grid_of(ts)
        for i, t in enumerate(ts):
            for j in sorted(grid.near(*_box(t))):
                if j > i and _overlap(t, ts[j]):
                    out.append(_f("text_overlaps", sh, [t.get("s", ""), ts[j].get("s", "")], f"texts {t.get('s')!r} and {ts[j].get('s')!r} overlap"))
    return out


def text_symbol_overlaps(g: Geometry) -> list[Finding]:
    """Texts overlapping a symbol they do not belong to, and texts overlapping a flag of another model."""
    out: list[Finding] = []
    for sh in g["sheets"]:
        for what, items in (("symbol", sh.get("symbols", [])), ("flag", sh.get("flags", []))):
            grid = _grid_of(items)
            for t in _texts(sh):
                for k in sorted(grid.near(*_box(t))):
                    o = items[k]
                    own = _belongs(t, o) if what == "symbol" else bool(t.get("model")) and t.get("model") == o.get("model")
                    if not own and _overlap(t, o):
                        out.append(_f("text_symbol_overlaps", sh, [t.get("s", ""), o["id"]], f"text {t.get('s')!r} overlaps {what} {o['id']}"))
    return out


def wire_through_symbol(g: Geometry) -> list[Finding]:
    """Wire segments through the interior of any symbol or flag, the wire's own end symbol included: a wire reaches its anchor on the edge from outside."""
    out: list[Finding] = []
    for sh in g["sheets"]:
        syms, flags = sh.get("symbols", []), sh.get("flags", [])
        grid = _Grid()
        boxes = [*syms, *flags]
        for k, b in enumerate(boxes): grid.add(k, *_box(b))
        for s in _segs(sh):
            w, k = s[0], s[1]
            for j in sorted(grid.near(*s[2:])):
                b = boxes[j]
                if _hits(s, b):
                    out.append(_f("wire_through_symbol", sh, [w["id"], b["id"]], f"wire {w['id']} runs through {b['id']}"))
    return out


def wire_text_overlaps(g: Geometry) -> list[Finding]:
    """Wire segments through a text box; a text whose model is the wire's own model (its label) is allowed."""
    out: list[Finding] = []
    for sh in g["sheets"]:
        ts = _texts(sh)
        grid = _grid_of(ts)
        for s in _segs(sh):
            w = s[0]
            for j in sorted(grid.near(*s[2:])):
                t = ts[j]
                if t.get("model") != w.get("model") and _hits(s, t):
                    out.append(_f("wire_text_overlaps", sh, [w["id"], t.get("s", "")], f"wire {w['id']} runs through text {t.get('s')!r}"))
    return out


def off_grid(g: Geometry) -> list[Finding]:
    """Wires with points off the grid or non-orthogonal segments: validate()'s findings, on a copy without texts (its text
    overlap test is quadratic)."""
    lite: Any = {**g, "sheets": [{**sh, "texts": [], "notes": []} for sh in g["sheets"]]}
    out: list[Finding] = []
    for msg in validate(lite):
        m = re.match(r"sheet (\d+): wire (.+) (has points off the grid|is not orthogonal)$", msg)
        if m: out.append({"check": "off_grid", "sheet": int(m[1]), "ids": [m[2]], "msg": msg.split(": ", 1)[1]})
    return out


def wire_overlaps(g: Geometry) -> list[Finding]:
    """Two different wires sharing a collinear stretch of non-zero length."""
    out: list[Finding] = []
    for sh in g["sheets"]:
        segs = _segs(sh)
        grid = _Grid()
        for k, s in enumerate(segs): grid.add(k, *s[2:])
        seen: set[tuple[str, str]] = set()
        for i, s in enumerate(segs):
            for j in sorted(grid.near(*s[2:])):
                u = segs[j]
                if j <= i or u[0]["model"] == s[0]["model"] or _horizontal(s) != _horizontal(u): continue
                h = _horizontal(s)
                same = abs((s[3] if h else s[2]) - (u[3] if h else u[2])) < EPS
                span = (min(s[4], u[4]) - max(s[2], u[2])) if h else (min(s[5], u[5]) - max(s[3], u[3]))
                pair = tuple(sorted((s[0]["model"].removeprefix("conductor:"), u[0]["model"].removeprefix("conductor:"))))
                if same and span > EPS and pair not in seen:
                    seen.add(pair)  # type: ignore[arg-type]
                    out.append(_f("wire_overlaps", sh, list(pair), f"wires {pair[0]} and {pair[1]} run on top of each other"))
    return out


def crossings_by_sheet(g: Geometry) -> dict[int, int]:
    """Proper crossings per sheet number: a horizontal and a vertical segment of different wires meeting inside both."""
    res: dict[int, int] = {}
    for sh in g["sheets"]:
        segs = _segs(sh)
        hs = [s for s in segs if _horizontal(s)]
        grid = _Grid()
        for k, s in enumerate(hs): grid.add(k, *s[2:])
        n = 0
        for v in (s for s in segs if not _horizontal(s)):
            for k in grid.near(*v[2:]):
                h = hs[k]
                if h[0]["id"] != v[0]["id"] and h[2] + EPS < v[2] < h[4] - EPS and v[3] + EPS < h[3] < v[5] - EPS: n += 1
        res[sh["n"]] = n
    return res


def crossings(g: Geometry) -> int:
    """Total proper crossings between different wires over all sheets."""
    return sum(crossings_by_sheet(g).values())


def out_of_sheet(g: Geometry) -> list[Finding]:
    """Wire points, symbols, flags and texts outside the sheet's w_mm x h_mm."""
    out: list[Finding] = []
    for sh in g["sheets"]:
        W, H = sh["w_mm"], sh["h_mm"]
        for w in sh.get("wires", []):
            if any(not (-EPS <= x <= W + EPS and -EPS <= y <= H + EPS) for x, y in w.get("points", [])):
                out.append(_f("out_of_sheet", sh, [w["id"]], f"wire {w['id']} leaves the sheet"))
        for what, items in (("symbol", sh.get("symbols", [])), ("flag", sh.get("flags", [])), ("text", _texts(sh))):
            for b in items:
                x0, y0, x1, y1 = _box(b)
                if x0 < -EPS or y0 < -EPS or x1 > W + EPS or y1 > H + EPS:
                    i = b.get("id", b.get("s", ""))
                    out.append(_f("out_of_sheet", sh, [i], f"{what} {i} leaves the sheet"))
    return out


def min_text(g: Geometry) -> list[Finding]:
    """Texts smaller than MIN_TEXT (2.5 mm)."""
    return [_f("min_text", sh, [t.get("s", "")], f"text {t.get('s')!r} is {t.get('size_mm')} mm, minimum {MIN_TEXT:g}")
            for sh in g["sheets"] for t in _texts(sh) if t.get("size_mm", 0) < MIN_TEXT - EPS]


def gauge_unit(g: Geometry) -> list[Finding]:
    """A gauge that carries its unit already, or wire text that says AWG twice."""
    out: list[Finding] = []
    sheets: list[Any] = list(g["sheets"])
    for sh in sheets:
        for w in sh.get("wires", []):
            if re.search(r"awg", w.get("gauge", ""), re.I): out.append(_f("gauge_unit", sh, [w["id"]], f"wire {w['id']} gauge {w['gauge']!r} carries its unit"))
        for t in [*_texts(sh), *(sh.get("table") or {}).get("rows", [])]:
            s = t.get("s") if "s" in t else f"{t.get('gauge', '')} AWG"
            if re.search(r"awg\W*awg", s, re.I): out.append(_f("gauge_unit", sh, [s], f"{s!r} names the unit twice"))
    return out


CHECKS = (text_overlaps, text_symbol_overlaps, wire_through_symbol, wire_text_overlaps, off_grid, wire_overlaps, gauge_unit, out_of_sheet, min_text)


def report(g: Geometry) -> Any:
    """Everything in one summary: counts per check, crossings (total and per sheet, a metric that does not fail), findings,
    and ok = no findings."""
    found = {c.__name__: c(g) for c in CHECKS}
    by = crossings_by_sheet(g)
    return {"counts": {k: len(v) for k, v in found.items()}, "crossings": {"total": sum(by.values()), "by_sheet": by},
            "findings": [f for v in found.values() for f in v], "ok": not any(found.values())}
