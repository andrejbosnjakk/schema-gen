"""Look of the drawings (docs/drawing-model.md): grid, line weights, text sizes and widths, fonts, sheet areas. All lengths in mm.

`size_mm` of a text is its CAP HEIGHT (the height of a capital letter at print size); the em (CSS font-size) is size_mm / CAP.
A text's bounding box is (x, y, w, h): w = text_w(s, size_mm), h = BOX * em, y = the top of the box; the baseline is at
y + ASC * em. `align` says what x means (left edge, centre, right edge). The minimum size_mm is 2.5 (0.1 in lettering)."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from .geometry import GRID, SHEETS  # noqa: F401  (re-exported: GRID = 5, SHEETS = {"A3": (420, 297), "A4": (297, 210)})

FONT_DIR = Path(__file__).with_name("fonts")
FONT_FAMILY = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif"
FONT_FILES = {"regular": FONT_DIR / "Inter-Regular.ttf", "bold": FONT_DIR / "Inter-SemiBold.ttf"}  # Inter 4 (OFL-1.1), Latin subset

# ---------------------------------------------------------------- line weights (mm)
LINE = {"thin": 0.18, "normal": 0.35, "thick": 0.5}            # prim strokes, as in the contract
WIRE = {"fine": 0.25, "light": 0.35, "medium": 0.5, "heavy": 0.7}  # wires by gauge class (scope.weight)
FRAME_STROKE = "thick"                                          # sheet frame
SYMBOL_STROKE = "normal"                                        # symbol outlines
DETAIL_STROKE = "thin"                                          # separators inside symbols
GREY = "#6b6b6b"                                                # spare pins, title-block captions
DASH = (1.5, 1.0)                                               # dashed prims: dash, gap

# ---------------------------------------------------------------- text
MIN_TEXT = 2.5
SIZE = 2.5          # body text (pins, labels, notes): cap height
SIZE_TITLE = 3.5    # drawing title
CAP, ASC, DESC = 0.7275, 0.969, 0.241   # Inter: cap height, ascender, descender per em
BOX = ASC + DESC                          # text box height per em
BOLD_ROLES = {"name", "head", "title", "flag"}
GREY_ROLES = {"spare", "caption"}
_W = {  # advance widths per 1000 em, Inter Regular / SemiBold, ASCII 32..126
    False: [281, 288, 466, 633, 642, 982, 644, 300, 365, 365, 501, 662, 288, 460, 288, 360, 631, 407, 610, 618, 646, 593, 620, 566, 619, 620, 288, 302,
            662, 662, 662, 511, 966, 690, 654, 730, 722, 601, 590, 746, 743, 269, 571, 672, 565, 903, 753, 765, 639, 765, 644, 642, 646, 744, 690, 985,
            682, 679, 629, 365, 360, 365, 471, 456, 323, 562, 612, 571, 612, 583, 370, 613, 591, 242, 242, 549, 242, 876, 591, 600, 612, 612, 376, 528,
            327, 591, 562, 818, 546, 562, 552, 426, 333, 426, 662],
    True: [252, 321, 523, 644, 650, 1004, 663, 326, 373, 373, 540, 673, 319, 465, 319, 379, 660, 423, 623, 636, 666, 612, 640, 576, 640, 640, 319, 329,
           673, 673, 673, 543, 999, 728, 659, 737, 722, 605, 588, 749, 746, 277, 580, 703, 565, 922, 759, 769, 645, 773, 652, 650, 660, 736, 728, 1020,
           720, 713, 652, 373, 379, 373, 481, 469, 351, 574, 624, 583, 624, 591, 389, 625, 612, 262, 262, 569, 262, 900, 612, 609, 624, 624, 397, 549,
           353, 612, 587, 839, 569, 588, 566, 455, 359, 455, 673]}
_EXTRA = {"Ω": 778, "×": 673, "±": 673, "−": 673, "–": 500, "•": 562, "°": 458, "µ": 614, "·": 330}
_FALLBACK = 780   # any other character: wider than nearly every Latin glyph
SAFETY = 1.03     # estimates are slightly wider than the font, never narrower


def glyphs(s: str) -> str:
    """The characters a renderer draws for s: Inter has no arrow, so U+2192 becomes '->'; the ohm sign becomes the Greek capital."""
    return s.replace("→", "->").replace("Ω", "Ω")


def em(size_mm: float) -> float:
    return size_mm / CAP


def is_bold(role: str) -> bool:
    return role in BOLD_ROLES


@lru_cache(maxsize=1 << 16)  # the layout measures the same few thousand strings over and over
def text_w(s: str, size_mm: float = SIZE, bold: bool = False) -> float:
    """Width in mm of s at cap height size_mm, from Inter's advance widths plus 3 %, rounded up to 0.05 mm (deterministic, conservative)."""
    t = _W[bold]
    u = sum(t[ord(c) - 32] if 32 <= ord(c) < 127 else _EXTRA.get(c, _FALLBACK) for c in glyphs(s))
    return math.ceil(u / 1000 * em(size_mm) * SAFETY * 20) / 20


def text_h(size_mm: float = SIZE) -> float:
    return round(BOX * em(size_mm), 3)


def baseline_dy(size_mm: float) -> float:
    """Offset of the baseline below the top of a text box."""
    return ASC * em(size_mm)


def fit(s: str, size_mm: float, maxw: float, bold: bool = False) -> str:
    """s, shortened with '..' at the end until it is at most maxw mm wide."""
    if text_w(s, size_mm, bold) <= maxw: return s
    while s and text_w(s + "..", size_mm, bold) > maxw: s = s[:-1]
    return s + ".."


def wrap(s: str, width_mm: float, size_mm: float = SIZE, bold: bool = False, lines: int = 2) -> list[str]:
    """s broken at spaces into at most `lines` lines of at most width_mm (the last line shortened with '..'). Only for fictional reference sheets: drawings never cut text."""
    out: list[str] = []
    cur = ""
    for w in s.split():
        t = f"{cur} {w}" if cur else w
        if cur and text_w(t, size_mm, bold) > width_mm and len(out) < lines - 1: out.append(cur); cur = w
        else: cur = t
    return [*out, fit(cur, size_mm, width_mm, bold)] if cur else out


def wrap_words(words: list[str], width_mm: float, size_mm: float = SIZE, bold: bool = False) -> list[int]:
    """How many of the words go on each line when they are filled greedily into lines of at most width_mm (a word wider than that has a line of its own)."""
    out: list[int] = []
    cur = ""
    n = 0
    for w in words:
        t = f"{cur} {w}" if cur else w
        if cur and text_w(t, size_mm, bold) > width_mm: out.append(n); cur, n = w, 1
        else: cur, n = t, n + 1
    return [*out, n] if n else out


def wrap_all(s: str, width_mm: float, size_mm: float = SIZE, bold: bool = False) -> list[str]:
    """s broken at spaces into lines of at most width_mm, measured with the font's metrics; nothing is cut off (a word wider than a line is broken inside,
    each piece a line of its own). The one text wrapper of the drawings: table cells, notes, title block, box names."""
    out: list[str] = []
    cur = ""
    for w in s.split():
        while text_w(w, size_mm, bold) > width_mm and len(w) > 1:
            k = max(1, next((i for i in range(len(w) - 1, 0, -1) if text_w(w[:i], size_mm, bold) <= width_mm), 1))
            k = w[:k].rfind("-") + 1 or k          # after a hyphen when there is one
            if cur: out.append(cur); cur = ""
            out.append(w[:k]); w = w[k:]
        t = f"{cur} {w}" if cur else w
        if cur and text_w(t, size_mm, bold) > width_mm: out.append(cur); cur = w
        else: cur = t
    return [*out, cur] if cur else out


def ceil_to(v: float, step: float = GRID) -> float:
    return math.ceil(v / step - 1e-9) * step


# ---------------------------------------------------------------- sheets
MARGIN = 10.0        # frame distance from the paper edge (top, left); right and bottom are rounded down to the grid
STRIP_H = 35.0       # the strip along the bottom of the frame: legend, notes, title block
TITLE_W = 140.0      # title block width
LEGEND_W = 135.0     # legend width (3 columns of 45)
PAD = 5.0            # between the drawable area and the frame / strip


def areas(size: str) -> dict[str, tuple[float, float, float, float]]:
    """Rectangles (x, y, w, h), all on the grid: frame, area (drawable: put symbols and wires here), strip, title, legend and notes
    (notes is (0, 0, 0, 0) when the sheet is too narrow for it: A4)."""
    W, H = SHEETS[size]
    x0, y0 = MARGIN, MARGIN
    x1, y1 = math.floor((W - MARGIN) / GRID) * GRID, math.floor((H - MARGIN) / GRID) * GRID
    sy = y1 - STRIP_H
    nx = x0 + LEGEND_W
    nw = x1 - TITLE_W - nx
    return {"frame": (x0, y0, x1 - x0, y1 - y0), "area": (x0 + PAD, y0 + PAD, x1 - x0 - 2 * PAD, sy - PAD - y0 - PAD), "strip": (x0, sy, x1 - x0, STRIP_H),
            "title": (x1 - TITLE_W, sy, TITLE_W, STRIP_H), "legend": (x0, sy, LEGEND_W, STRIP_H),
            "notes": (nx, sy, nw, STRIP_H) if nw >= 40 else (0.0, 0.0, 0.0, 0.0)}


def font_files() -> dict[str, Any]:
    """Paths of the bundled Inter files that exist (regular, bold)."""
    return {k: p for k, p in FONT_FILES.items() if p.exists()}
