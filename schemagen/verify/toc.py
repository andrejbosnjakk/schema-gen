"""The table of contents of the book, read from the book's own pages and checked against the book: one entry for every drawing, by its display name (the id in
small type when it differs), its sheet count, and the book page its first sheet is on. Knows only what a contents page looks like (a caption row DRAWING / ID /
SHEETS / PAGE, one line per drawing, a long name on a second line), nothing of the engine."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from . import expect as X
from .check import Drawing
from .parse import title_fields
from .pdfread import Sheet


@dataclass
class Entry:
    name: str
    ident: str
    sheets: int
    page: int
    at: int            # the contents page it is on


def _nat(s: str) -> list[Any]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]


def _sig(sheet: Sheet) -> str: return hashlib.sha1("\n".join(sorted(f"{r.s}@{r.x0:.0f},{r.top:.0f}" for r in sheet.runs)).encode()).hexdigest()


def entries(pages: list[Sheet]) -> tuple[list[Entry], list[int]]:
    """The entries of every contents page (a page whose title block says `Contents`), in order, and those pages' numbers."""
    out: list[Entry] = []
    nums: list[int] = []
    for k, pg in enumerate(pages, 1):
        if title_fields(pg).get("title") != "Contents": continue
        nums.append(k)
        cap = {r.s: r for r in pg.runs if r.s in ("DRAWING", "ID", "SHEETS", "PAGE") and r.top < 40}
        if len(cap) < 4: continue
        lines: dict[int, list[Any]] = {}
        for r in pg.runs:
            if cap["DRAWING"].bot - 0.1 < r.top < pg.h * 0.84: lines.setdefault(round(r.cy / 2.2), []).append(r)
        cur: Entry | None = None
        for _, rs in sorted(lines.items()):
            rs.sort(key=lambda r: r.x0)
            nums_ = [r for r in rs if r.s.isdigit() and r.x0 > cap["ID"].x0]
            name = " ".join(r.s for r in rs if r.x0 < cap["ID"].x0 - 1)
            ident = " ".join(r.s for r in rs if cap["ID"].x0 - 1 <= r.x0 < cap["SHEETS"].x0 - 10 and r not in nums_)
            if len(nums_) == 2:
                a, b = sorted(nums_, key=lambda r: r.x1)
                cur = Entry(name, ident, int(a.s), int(b.s), k)
                out.append(cur)
            elif cur is not None and name and not nums_: cur.name += " " + name
    return out, nums


def check_toc(ex: X.Expected, ds: dict[str, Drawing], pages: list[Sheet]) -> list[dict[str, Any]]:
    """Findings (kind `toc`) for a book whose contents are missing, wrong, unsorted or point at the wrong page."""
    es, nums = entries(pages)
    if not nums: return [dict(kind="toc", drawing="", sheet=None, msg="the book has no table of contents")]
    first: dict[str, int] = {}
    for k, pg in enumerate(pages, 1): first.setdefault(_sig(pg), k)
    out: list[dict[str, Any]] = []
    seen: dict[str, Entry] = {}
    for e in es:
        comp = e.ident or (ex.lead(e.name)[0] if e.name not in ex.display else e.name)
        if e.ident and e.ident not in ex.display: out.append(dict(kind="toc", drawing="", sheet=None, msg=f"contents entry '{e.name}' names the id '{e.ident}', which is no component"))
        elif comp is None or comp not in ex.display and not e.ident: out.append(dict(kind="toc", drawing="", sheet=None, msg=f"contents entry '{e.name}' names no component"))
        else:
            if comp in seen: out.append(dict(kind="toc", drawing=f"component-{comp}", sheet=None, msg=f"{comp} is in the contents twice"))
            seen[comp] = e
            if e.name != ex.display[comp]: out.append(dict(kind="toc", drawing=f"component-{comp}", sheet=None, msg=f"contents name '{e.name}' is not the display name '{ex.display[comp]}'"))
            if bool(e.ident) != (ex.display[comp] != comp): out.append(dict(kind="toc", drawing=f"component-{comp}", sheet=None, msg=f"contents entry '{e.name}': the id is shown when it differs from the name, only then"))
    for i, (a, b) in enumerate(zip(es, es[1:])):
        if (_nat(a.name), _nat(a.ident)) > (_nat(b.name), _nat(b.ident)): out.append(dict(kind="toc", drawing="", sheet=None, msg=f"contents: '{a.name}' stands before '{b.name}', not in alphabetical order"))
    for d in ds.values():
        comp = d.scope.removeprefix("component:")
        if not d.sheets or not d.scope.startswith("component:"): continue
        ent = seen.get(comp)
        if ent is None: out.append(dict(kind="toc", drawing=d.name, sheet=None, msg=f"{comp} is not in the contents")); continue
        if ent.sheets != len(d.sheets): out.append(dict(kind="toc", drawing=d.name, sheet=None, msg=f"contents say {ent.sheets} sheets for {comp}, the drawing has {len(d.sheets)}"))
        at = first.get(_sig(d.pages[0]))
        if at is None: continue            # not in the book: reported as a book finding
        if ent.page != at: out.append(dict(kind="toc", drawing=d.name, sheet=None, msg=f"contents say {comp} starts on page {ent.page}, it starts on page {at}"))
    return out
