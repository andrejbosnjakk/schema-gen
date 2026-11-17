"""Legibility of a sheet as printed: text that overlaps text, text that sits on a line that is not its own label's, anything outside the frame or inside
the title block / legend / notes / table, text that is too small. Measured on the PDF's own text boxes and lines (nothing of the engine)."""
from __future__ import annotations

from typing import Any

from .parse import SheetObs, _label_of
from .pdfread import Run

MIN_CAP_MM = 2.0   # smallest letter height at A3
A3_W = 420.0
SHRINK = 0.2       # text boxes are slightly smaller than the ink they hold; give lines the same benefit


def _box(r: Run) -> tuple[float, float, float, float]: return (r.x0 + SHRINK, r.top + SHRINK, r.x1 - SHRINK, r.bot - SHRINK)


def _hit_box(b: tuple[float, float, float, float], c: tuple[float, float, float, float]) -> bool:
    return b[0] < c[2] and c[0] < b[2] and b[1] < c[3] and c[1] < b[3]


def _hit_seg(b: tuple[float, float, float, float], a: tuple[float, float], z: tuple[float, float], half: float) -> bool:
    """A segment (axis-aligned or diagonal, as its bounding box thickened by half its width) runs through the box. Diagonals are tested by sampling."""
    n = max(2, int(max(abs(z[0] - a[0]), abs(z[1] - a[1])) / 0.25))
    for i in range(n + 1):
        x, y = a[0] + (z[0] - a[0]) * i / n, a[1] + (z[1] - a[1]) * i / n
        if b[0] - half < x < b[2] + half and b[1] - half < y < b[3] + half: return True
    return False


def findings(ob: SheetObs) -> list[dict[str, Any]]:
    """Legibility findings of one sheet: dicts with `kind` and a short `msg`."""
    out: list[dict[str, Any]] = []
    pg = ob.page
    fx0, fy0, fx1, fy1 = ob.frame
    sy0 = ob.strip[1]
    scale = A3_W / max(pg.w, pg.h * 420 / 297) if pg.w else 1.0
    tb = ob.table
    owned = {id(r): j for j, w in enumerate(ob.wires) for r in w.label_runs}
    runs = pg.runs

    def region(r: Run) -> str:
        if r.top >= sy0 - 0.2: return "strip"
        if tb and tb[1] - 0.3 <= r.top <= tb[3]: return "table"
        return "drawing"
    for r in runs:
        if r.cap * scale < MIN_CAP_MM - 1e-6: out.append(dict(kind="text_too_small", msg=f"'{r.s}' letters {r.cap * scale:.2f} mm high at A3"))
        if r.x0 < fx0 - 0.01 or r.x1 > fx1 + 0.01 or r.top < fy0 - 0.01 or r.bot > fy1 + 0.01: out.append(dict(kind="text_outside_frame", msg=f"'{r.s}' leaves the frame"))
    # text on text
    cells: dict[tuple[int, int], list[Run]] = {}
    for r in runs: cells.setdefault((int(r.x0 // 20), int(r.top // 10)), []).append(r)
    seen: set[tuple[int, int]] = set()
    for (cx, cy), rs in cells.items():
        near = [q for dx in (0, 1) for dy in (-1, 0, 1) for q in cells.get((cx + dx, cy + dy), [])] if rs else []
        for a in rs:
            for b in near:
                if a is b or (id(b), id(a)) in seen or (id(a), id(b)) in seen: continue
                seen.add((id(a), id(b)))
                if _hit_box(_box(a), _box(b)): out.append(dict(kind="text_overlaps_text", msg=f"'{a.s}' overlaps '{b.s}'"))
    # text on lines: wires (not its own), plain lines, outlines' edges
    lines: list[tuple[tuple[float, float], tuple[float, float], float, int]] = []
    for j, w in enumerate(pg.wires):
        for a, z in zip(w.pts, w.pts[1:]): lines.append((a, z, w.w / 2 + 0.2, j))
    for a, z, wd, st in pg.segs:
        if a[1] < sy0 - 0.5: lines.append((a, z, wd / 2, -1))
    for o in pg.outlines:
        if o.y0 < sy0 - 0.5:
            for a, z in zip(o.pts, o.pts[1:]): lines.append((a, z, 0.17, -2))
    for r in runs:
        if region(r) != "drawing": continue
        b = _box(r)
        for a, z, half, j in lines:
            if max(a[0], z[0]) + half < b[0] or min(a[0], z[0]) - half > b[2] or max(a[1], z[1]) + half < b[1] or min(a[1], z[1]) - half > b[3]: continue
            if owned.get(id(r)) == j: continue
            if _hit_seg(b, a, z, half):
                out.append(dict(kind="text_on_line", msg=f"'{r.s}' sits on a " + ("wire" if j >= 0 else "symbol line") + (f" ({'/'.join(ob.wires[j].labels)})" if j >= 0 else "")))
                break
    # drawing content inside the strip or the table
    furniture = [("title block, legend or notes", (fx0, sy0, fx1, fy1))] + ([("wire table", tb)] if tb else [])
    for name, (x0, y0, x1, y1) in furniture:
        for j, w in enumerate(pg.wires):
            if any(x0 - .2 < x < x1 + .2 and y0 + 0.2 < y < y1 + .2 for x, y in w.pts) or any(min(a[1], z[1]) < y0 < max(a[1], z[1]) for a, z in zip(w.pts, w.pts[1:])):
                out.append(dict(kind="graphics_in_furniture", msg=f"wire {'/'.join(ob.wires[j].labels) or '?'} runs into the {name}"))
        for o in pg.outlines:
            if o.x1 - o.x0 >= 6 and o.x0 < x1 and o.x1 > x0 and o.y0 < y1 - 0.2 and o.y1 > y0 + 0.2 and (name == "wire table" or o.y0 < y0 - 0.2):
                out.append(dict(kind="graphics_in_furniture", msg=f"a symbol or flag overlaps the {name}"))
    for r in runs:
        if region(r) == "drawing" and r.bot > sy0 + 0.2: out.append(dict(kind="graphics_in_furniture", msg=f"'{r.s}' reaches into the title block area"))
    return out
