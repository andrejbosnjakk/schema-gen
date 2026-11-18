"""The table of contents of the combined book (docs/drawing-model.md, Book): one line per drawing, sorted by display name: the name, the id in small grey type when it
differs from the name, how many sheets the drawing has and the book page it starts on. Names too long for their column go on to a second line; the contents go on to
further pages as needed. `sheets(entries, ...)` returns the pages as sheets of a geometry (title block `Contents`)."""
from __future__ import annotations

from typing import Any

from ..app.workspace import _natural
from . import symbols as S
from .geometry import SHEETS
from .style import SIZE, areas, wrap_all

ROW = 4.5
COLS = (0.0, 140.0, 330.0, 385.0)        # name, id, sheets (right edge), page (right edge): offsets from the area's left edge
NAME_W = 135.0
Entry = tuple[str, str, int]            # (display name, drawing id, number of sheets)


def order(entries: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """The entries sorted by display name (then id)."""
    return sorted(entries, key=lambda e: (_natural(e[0].lower()), _natural(e[1])))


def _lines(name: str) -> list[str]:
    return wrap_all(name, NAME_W, SIZE) or [""]


def split(entries: list[Entry], size: str = "A3") -> list[list[Entry]]:
    """The entries (in order) cut into pages: as many lines as the area holds, a header row included."""
    ah = areas(size)["area"][3]
    pgs: list[list[Entry]] = [[]]
    used = ROW
    for e in entries:
        h = ROW * len(_lines(e[0]))
        if pgs[-1] and used + h > ah: pgs.append([]); used = ROW
        pgs[-1].append(e); used += h
    return pgs


def sheets(entries: list[Entry], info: dict[str, str], first: int, size: str = "A3") -> list[dict[str, Any]]:
    """The contents pages for entries in order, the first drawing starting on book page `first` (the pages of the contents come before it: the caller gives the
    page after them). info: the title block data."""
    ax, ay, aw, _ = areas(size)["area"]
    pgs = split(entries, size)
    start = first
    out: list[dict[str, Any]] = []
    for n, pg in enumerate(pgs, 1):
        texts: list[Any] = []
        rules: list[Any] = [dict(kind="line", stroke="thin", x1=ax, y1=ay + ROW, x2=ax + COLS[3], y2=ay + ROW)]
        for t, x, al in (("DRAWING", COLS[0], "left"), ("ID", COLS[1], "left"), ("SHEETS", COLS[2], "right"), ("PAGE", COLS[3], "right")):
            texts.append(S.text(t, ax + x, ay + ROW / 2, al, "caption", SIZE))
        y = ay + ROW
        for name, ident, count in pg:
            ls = _lines(name)
            for i, t in enumerate(ls): texts.append(S.text(t, ax + COLS[0], y + ROW * (i + 0.5), "left", "pin", SIZE))
            if ident != name: texts.append(S.text(ident, ax + COLS[1], y + ROW / 2, "left", "part", SIZE))
            texts.append(S.text(str(count), ax + COLS[2], y + ROW / 2, "right", "pin", SIZE))
            texts.append(S.text(str(start), ax + COLS[3], y + ROW / 2, "right", "pin", SIZE))
            start += count
            y += ROW * len(ls)
            rules.append(dict(kind="line", stroke="thin", x1=ax, y1=y, x2=ax + COLS[3], y2=y))
        sh: dict[str, Any] = dict(n=n, of=len(pgs), size=size, w_mm=SHEETS[size][0], h_mm=SHEETS[size][1], grid_mm=5.0, symbols=[], wires=[], texts=texts, flags=[],
                                  rules=rules)
        sh.update(S.furniture(dict(info, title="Contents", scope="book"), size, n, len(pgs), [], ["Every drawing of this book, by name, with the page it starts on."]))
        out.append(sh)
    return out
