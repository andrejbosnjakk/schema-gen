"""PDF renderer: a Geometry (docs/drawing-model.md) as a vector PDF with one page per sheet (reportlab, BSD). Same look as the SVG:
black on white, the bundled Inter embedded (Helvetica when the font files are missing). Deterministic (reportlab invariant mode)."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .geometry import Geometry
from .render_svg import layers
from .style import DASH, GREY, GREY_ROLES, LINE, WIRE, baseline_dy, em, font_files, glyphs, is_bold

FILL = {"black": (0, 0, 0), "white": (1, 1, 1)}


def _fonts() -> tuple[str, str]:
    ff = font_files()
    if len(ff) < 2: return "Helvetica", "Helvetica-Bold"
    for name, k in (("Inter", "regular"), ("Inter-SemiBold", "bold")):
        if name not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont(name, str(ff[k])))
    return "Inter", "Inter-SemiBold"


def _hex(h: str) -> tuple[float, float, float]:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def _page(c: Canvas, sh: dict[str, Any], fonts: tuple[str, str]) -> None:
    H = sh["h_mm"]
    Y = lambda y: (H - y) * mm  # noqa: E731  (the geometry's y grows downwards)
    X = lambda x: x * mm  # noqa: E731
    c.setPageSize((sh["w_mm"] * mm, H * mm))
    c.setLineCap(0); c.setLineJoin(1)

    def path(pts: list[Any], closed: bool, fill: Any, stroke: str | None, width: float, dash: bool = False) -> None:
        c.setLineWidth(width * mm); c.setDash(*[d * mm for d in DASH]) if dash else c.setDash()
        p = c.beginPath()
        p.moveTo(X(pts[0][0]), Y(pts[0][1]))
        for x, y in pts[1:]: p.lineTo(X(x), Y(y))
        if closed: p.close()
        if fill: c.setFillColorRGB(*fill)
        c.drawPath(p, stroke=int(stroke is not None), fill=int(bool(fill)))

    def prim(p: dict[str, Any]) -> None:
        k, st, fill = p["kind"], p.get("stroke", "normal"), FILL.get(p.get("fill", "none"))
        sk = None if st == "none" else "k"
        c.setStrokeColorRGB(0, 0, 0)
        w = LINE.get(st, 0.35)
        if k == "line": path([(p["x1"], p["y1"]), (p["x2"], p["y2"])], False, None, sk, w, p.get("dash", False))
        elif k == "rect":
            x, y, rw, rh = p["x"], p["y"], p["w"], p["h"]
            path([(x, y), (x + rw, y), (x + rw, y + rh), (x, y + rh)], True, fill, sk, w, p.get("dash", False))
        elif k == "polyline": path(p["points"], bool(p.get("closed")), fill, sk, w, p.get("dash", False))
        elif k == "circle":
            c.setLineWidth(w * mm)
            if fill: c.setFillColorRGB(*fill)
            c.circle(X(p["cx"]), Y(p["cy"]), p["r"] * mm, stroke=int(sk is not None), fill=int(bool(fill)))
        elif k == "arc":
            n = max(2, int(abs(p["a1"] - p["a0"]) / 3) + 1)
            pts = [(p["cx"] + p["r"] * math.cos(math.radians(p["a0"] + (p["a1"] - p["a0"]) * i / (n - 1))),
                    p["cy"] + p["r"] * math.sin(math.radians(p["a0"] + (p["a1"] - p["a0"]) * i / (n - 1)))) for i in range(n)]
            path(pts, False, None, sk, w, p.get("dash", False))

    def text(t: dict[str, Any]) -> None:
        bold = is_bold(t.get("role", ""))
        c.setFont(fonts[1] if bold else fonts[0], em(t["size_mm"]) * mm)
        c.setFillColorRGB(*(_hex(GREY) if t.get("role") in GREY_ROLES else (0, 0, 0)))
        y = Y(t["y"] + baseline_dy(t["size_mm"]))
        s = glyphs(t["s"])
        {"left": c.drawString, "centre": c.drawCentredString, "right": c.drawRightString}[t["align"]](
            X(t["x"] + {"left": 0, "centre": t["w"] / 2, "right": t["w"]}[t["align"]]), y, s)

    for kind, _, v in layers(sh):
        if kind == "prims":
            for p in v: prim(p)
        elif kind == "text": text(v)
        else:
            pts = v["points"]
            c.setStrokeColorRGB(0, 0, 0)
            path(pts, False, None, "k", WIRE[v["weight"]], bool(v.get("fault")))


def pdf(geometry: Geometry | list[Geometry], path: str | Path) -> int:
    """Writes the geometry (or a list of them: one book, in that order) as a vector PDF, one page per sheet; returns the number of pages."""
    fonts = _fonts()
    gs = geometry if isinstance(geometry, list) else [geometry]
    c = Canvas(str(path), invariant=1, pageCompression=1)
    c.setTitle(gs[0]["drawing"].get("title", "")); c.setCreator("schemagen")
    for g in gs:
        for sh in g["sheets"]:
            _page(c, dict(sh), fonts)
            c.showPage()
    c.save()
    return sum(len(g["sheets"]) for g in gs)
