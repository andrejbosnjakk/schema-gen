"""SVG renderer: one sheet of a Geometry (docs/drawing-model.md) as a standalone SVG, black on white, mm units. Draws only what the
geometry holds (prims, wires, texts, flags, title block); every element carries data-model="<model id>" for the app. The output
is byte-deterministic: fixed number formatting, stable attribute order, no timestamps or generated ids."""
from __future__ import annotations

import base64
import math
from collections.abc import Iterator
from html import escape
from typing import Any

from .geometry import Geometry
from .style import FONT_FAMILY, GREY, GREY_ROLES, LINE, WIRE, em, baseline_dy, font_files, glyphs, is_bold
from .symbols import flag_shapes

FAMILY = FONT_FAMILY.replace("'", "")
FILL = {"black": "#000", "white": "#fff"}
Layer = tuple[str, str, Any]   # ("prims", model, [prim]) | ("text", model, text) | ("wire", model, wire)


def layers(sh: dict[str, Any]) -> Iterator[Layer]:
    """What a sheet draws, back to front: frame and title block, legend, symbols, wires, flags, texts, notes (shared with render_pdf)."""
    tb = sh.get("title_block") or {}
    yield "prims", "", tb.get("prims", [])
    for t in tb.get("texts", []): yield "text", "", t
    for e in sh.get("legend") or []:
        if isinstance(e, dict) and "prims" in e:
            yield "prims", "", e["prims"]
            for t in e.get("texts", []): yield "text", "", t
    yield "prims", "", sh.get("rules", [])
    for s in sh.get("symbols", []): yield "prims", s["model"], s["prims"]
    for w in sh.get("wires", []): yield "wire", w["model"], w
    for f in sh.get("flags", []):
        pr, tx = flag_shapes(f)
        yield "prims", f["model"], pr
        for t in tx: yield "text", f["model"], t
    for t in [*sh.get("texts", []), *sh.get("notes", [])]: yield "text", t["model"], t


def casing(w: dict[str, Any], colour: bool = True) -> float:
    """Line width of a wire's black casing (mm): a little wider than the class width when its colour is drawn inside."""
    return WIRE[w["weight"]] + (0.2 if colour and w.get("hex") and not w.get("fault") else 0.0)


def core(w: dict[str, Any]) -> float:
    return round(WIRE[w["weight"]] * 0.7, 3)


def num(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _style(p: dict[str, Any]) -> str:
    st = p.get("stroke", "normal")
    out = f' fill="{FILL.get(p.get("fill", "none"), "none")}"'
    if st == "none": return out + ' stroke="none"'
    out += f' stroke="#000" stroke-width="{num(LINE[st])}"'
    return out + (' stroke-dasharray="1.5 1"' if p.get("dash") else "")


def _prim(p: dict[str, Any]) -> str:
    k = p["kind"]
    if k == "line": return f'<line x1="{num(p["x1"])}" y1="{num(p["y1"])}" x2="{num(p["x2"])}" y2="{num(p["y2"])}"{_style(p)}/>'
    if k == "rect": return f'<rect x="{num(p["x"])}" y="{num(p["y"])}" width="{num(p["w"])}" height="{num(p["h"])}"{_style(p)}/>'
    if k == "circle": return f'<circle cx="{num(p["cx"])}" cy="{num(p["cy"])}" r="{num(p["r"])}"{_style(p)}/>'
    if k == "polyline":
        pts = " ".join(f"{num(x)},{num(y)}" for x, y in p["points"])
        return f'<{"polygon" if p.get("closed") else "polyline"} points="{pts}"{_style(p)} stroke-linejoin="round"/>'
    if k == "arc":
        a0, a1 = math.radians(p["a0"]), math.radians(p["a1"])
        x0, y0 = p["cx"] + p["r"] * math.cos(a0), p["cy"] + p["r"] * math.sin(a0)
        x1, y1 = p["cx"] + p["r"] * math.cos(a1), p["cy"] + p["r"] * math.sin(a1)
        return f'<path d="M{num(x0)} {num(y0)}A{num(p["r"])} {num(p["r"])} 0 {int(p["a1"] - p["a0"] > 180)} 1 {num(x1)} {num(y1)}"{_style({**p, "fill": "none"})}/>'
    return f'<path d="{escape(p["d"], quote=True)}"{_style(p)}/>'


def _text(t: dict[str, Any]) -> str:
    size = em(t["size_mm"])
    x = t["x"] + {"left": 0, "centre": t["w"] / 2, "right": t["w"]}[t["align"]]
    anchor = {"left": "start", "centre": "middle", "right": "end"}[t["align"]]
    fill = f' fill="{GREY}"' if t.get("role") in GREY_ROLES else ""
    bold = ' font-weight="600"' if is_bold(t.get("role", "")) else ""
    return (f'<text x="{num(x)}" y="{num(t["y"] + baseline_dy(t["size_mm"]))}" font-size="{num(size)}" text-anchor="{anchor}"{bold}{fill} '
            f'data-model="{escape(t["model"])}">{escape(glyphs(t["s"]))}</text>')


def _font_css() -> str:
    ff = font_files()
    faces = [f"@font-face{{font-family:Inter;font-weight:{w};src:url(data:font/ttf;base64,{base64.b64encode(ff[k].read_bytes()).decode()})}}"
             for k, w in (("regular", 400), ("bold", 600)) if k in ff]
    return f"<style>{''.join(faces)}</style>" if faces else ""


def svg(geometry: Geometry, sheet: int = 0, colour: bool = True, embed_font: bool = False) -> str:
    """Sheet number `sheet` (0 based) as SVG text. colour draws each wire in its colour inside a black casing (the code text stays, so a black-and-white
    print reads the same); embed_font embeds Inter."""
    sh: Any = geometry["sheets"][sheet]
    W, H = sh["w_mm"], sh["h_mm"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{num(W)}mm" height="{num(H)}mm" viewBox="0 0 {num(W)} {num(H)}" font-family="{FAMILY}">']
    if embed_font: out.append(_font_css())
    out.append(f'<rect width="{num(W)}" height="{num(H)}" fill="#fff"/>')
    for kind, model, v in layers(sh):
        if kind == "prims":
            if v: out.append(f'<g data-model="{escape(model)}">' + "".join(_prim(p) for p in v) + "</g>")
        elif kind == "text": out.append(_text(v))
        else:
            pts = " ".join(f"{num(x)},{num(y)}" for x, y in v["points"])
            wd = casing(v, colour)
            dash = ' stroke-dasharray="1.5 1"' if v.get("fault") else ""
            out.append(f'<polyline points="{pts}" fill="none" stroke="#000" stroke-width="{num(wd)}" stroke-linejoin="round"{dash} data-model="{escape(model)}"/>')  # noqa: E501
            if colour and v.get("hex") and not v.get("fault"):
                out.append(f'<polyline points="{pts}" fill="none" stroke="{escape(v["hex"])}" stroke-width="{num(core(v))}" stroke-linejoin="round"/>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
