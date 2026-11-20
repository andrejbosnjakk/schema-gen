"""Reads what a technician holds: a drawing PDF as text runs with positions, wires (a black casing over a coloured core, same path), junction dots,
filled outlines (symbols, flags), and plain line segments. Millimetres, y down. Uses pdfplumber; imports nothing of schemagen."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MM = 72 / 25.4
Pt = tuple[float, float]


@dataclass
class Run:
    """A piece of text drawn in one go: its words, box (mm) and font size (mm, the em)."""
    s: str
    x0: float; x1: float; top: float; bot: float
    em: float
    bold: bool = False

    @property
    def cx(self) -> float: return (self.x0 + self.x1) / 2
    @property
    def cy(self) -> float: return (self.top + self.bot) / 2
    @property
    def cap(self) -> float: return self.em * 0.72   # cap height of the usual sans fonts: 0.72 to 0.73 em


@dataclass
class Wire:
    pts: list[Pt]
    w: float                     # core width (mm)
    rgb: tuple[float, float, float]


@dataclass
class Outline:
    pts: list[Pt]
    x0: float; y0: float; x1: float; y1: float


@dataclass
class Sheet:
    n: int
    w: float; h: float
    runs: list[Run] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    segs: list[tuple[Pt, Pt, float, bool]] = field(default_factory=list)   # plain segments (a, b, width, straight: a path of its own of two points)
    dots: list[Pt] = field(default_factory=list)                     # centres of small filled black circles
    outlines: list[Outline] = field(default_factory=list)            # closed paths filled white (symbols, flags)
    boxes: list[Outline] = field(default_factory=list)               # closed paths without fill (frame, title block, table boxes)


def _mm(v: float) -> float: return round(v / MM, 3)


def _rgb(c: Any) -> tuple[float, float, float]:
    if c is None: return (0.0, 0.0, 0.0)
    if isinstance(c, (int, float)): return (float(c),) * 3
    c = tuple(c)
    if len(c) == 1: return (float(c[0]),) * 3
    if len(c) == 4: k = c[3]; return tuple(round((1 - v) * (1 - k), 3) for v in c[:3])  # type: ignore[return-value]
    return tuple(float(v) for v in c[:3])  # type: ignore[return-value]


def _runs(chars: list[dict[str, Any]]) -> list[Run]:
    """Characters in drawing order, joined while they touch (a space is a character): one run per drawn string."""
    out: list[Run] = []
    cur: list[dict[str, Any]] = []

    def flush() -> None:
        s = "".join(c["text"] for c in cur).strip()
        if s:
            lead = len(cur) - len("".join(c["text"] for c in cur).lstrip())
            first = cur[lead]
            out.append(Run(s, _mm(first["x0"]), _mm(cur[-1]["x1"]), _mm(first["top"]), _mm(first["bottom"]), _mm(first["size"]),
                           "bold" in first["fontname"].lower() or "semibold" in first["fontname"].lower()))
        cur.clear()
    for c in chars:
        if cur:
            p = cur[-1]
            if c["fontname"] != p["fontname"] or abs(c["size"] - p["size"]) > .05 or abs(c["top"] - p["top"]) > .8 or not -1.0 < c["x0"] - p["x1"] < 1.0: flush()
        cur.append(c)
    flush()
    return out



def read(path: str | Path) -> list[Sheet]:
    """Every page of a PDF as a Sheet."""
    import pdfplumber
    out: list[Sheet] = []
    opener = pdfplumber.open   # a PDF is read as bytes
    with opener(str(path)) as pdf:
        for n, p in enumerate(pdf.pages, 1):
            sh = Sheet(n, _mm(p.width), _mm(p.height))
            sh.runs = _runs(p.chars)
            paths: list[dict[str, Any]] = []
            for o in p.lines + p.curves:
                pts = [(_mm(x), _mm(y)) for x, y in o["pts"]]
                paths.append(dict(pts=pts, w=_mm(o["linewidth"]), stroke=_rgb(o.get("stroking_color")) if o["stroke"] else None,
                                  fill=_rgb(o.get("non_stroking_color")) if o["fill"] else None, dash=bool(o.get("dash") and o["dash"][0])))
            for o in p.rects:
                x0, y0, x1, y1 = _mm(o["x0"]), _mm(o["top"]), _mm(o["x1"]), _mm(o["bottom"])
                paths.append(dict(pts=[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], w=_mm(o["linewidth"]), stroke=_rgb(o.get("stroking_color")) if o["stroke"] else None,
                                  fill=_rgb(o.get("non_stroking_color")) if o["fill"] else None, dash=False))
            _classify(sh, paths)
            out.append(sh)
    return out


def _key(pts: list[Pt]) -> tuple[tuple[int, int], ...]: return tuple((round(x * 20), round(y * 20)) for x, y in pts)


def _classify(sh: Sheet, paths: list[dict[str, Any]]) -> None:
    """Wires are pairs of identical open paths, a black one 0.4 mm wider than the coloured one; closed paths are dots (small, black),
    outlines (white fill) or boxes (no fill); the rest are plain segments."""
    groups: dict[Any, list[dict[str, Any]]] = {}
    paths = [q for q in paths if not (q["stroke"] == (1.0, 1.0, 1.0) and q["fill"] is None)]    # white ink is not seen (the backing of a label on its wire)
    for q in paths:
        closed = len(q["pts"]) > 2 and q["pts"][0] == q["pts"][-1]
        q["closed"] = closed
        if not closed and q["stroke"] is not None and q["fill"] is None: groups.setdefault(_key(q["pts"]), []).append(q)
    used: set[int] = set()
    for g in groups.values():
        g.sort(key=lambda q: -q["w"])
        while len(g) >= 2:
            cas, core = g[0], g[-1]
            if abs(cas["w"] - core["w"] - 0.4) < 0.06 and cas["stroke"] == (0.0, 0.0, 0.0):
                sh.wires.append(Wire(core["pts"], core["w"], core["stroke"])); used |= {id(cas), id(core)}; g.pop(0); g.pop(-1)
            else: break
    for q in paths:
        if id(q) in used: continue
        pts = q["pts"]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bb = (min(xs), min(ys), max(xs), max(ys))
        if q["closed"]:
            if q["fill"] is not None and q["fill"] == (0.0, 0.0, 0.0) and bb[2] - bb[0] <= 2.4 and bb[3] - bb[1] <= 2.4:
                sh.dots.append((round((bb[0] + bb[2]) / 2, 2), round((bb[1] + bb[3]) / 2, 2)))
            elif q["fill"] is not None and q["fill"] != (0.0, 0.0, 0.0): sh.outlines.append(Outline(pts, *bb))
            elif q["fill"] is None: sh.boxes.append(Outline(pts, *bb))
        elif q["stroke"] is not None:
            for a, b in zip(pts, pts[1:]):
                if a != b: sh.segs.append((a, b, q["w"], len(pts) == 2))
    sh.dots = sorted(set(sh.dots))
