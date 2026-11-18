"""The wire table of a drawing (docs/drawing-model.md): one row per conductor, once per drawing, under the sheet that draws it first, so a person can work
through a sheet wire by wire. A page's `table` is its rows as data (`sheet["table"] = {"sheet": n where it is drawn, "rows": [...]}`); the table itself is
drawn as texts and `rules` (prims) under the drawing when it fits there, else after the last drawing sheet (a strip drawing: from the free room under its last sheet
on, then on table sheets). A cell that is too long for its column goes on to further lines of the row; nothing is cut off. Text for the wire's two ends comes from
the page's own items (the same words as the flags), colours from exporters/palette.py."""
from __future__ import annotations

import re
from typing import Any

from ..app.workspace import _natural
from ..exporters.palette import words as colour_words
from . import symbols as S
from .route import unit
from .scope import short, short_name
from .style import SIZE, areas, text_w, wrap_all

Elem = dict[str, Any]
ROW = 4.5                      # pitch of a line of text (mm); a text box is 4.2 mm high
WIREW = 52.0                   # width of the wire column
HEAD = ("", "LABEL", "WIRE", "FROM", "TO", "SEE")
SEE = re.compile(r"\s*(\(drawing [^)]*\))$")
GAP = 5.0                      # between a drawing and the table under it
MIN_FREE = 40.0                 # room under a drawing from which a table is carried on there (mm)


def _end(it: Elem, b: Elem, p: Elem) -> str:
    """A terminal in words: `EFIS, J1, pin 2 (GND)`; a splice, bus or ground by what it is."""
    code = it["code"]
    if it["symbol"] == "splice": return f"splice {code}"
    if it["symbol"] == "bus": return f"bus {code}"
    if it["symbol"] == "ground": return f"ground bus {code}"
    code = short_name(it["name"] or code)         # the Name column, as on the drawing
    pin = f"pin {p['n']}" if p["n"] else ""
    where = b["id"] if b["id"] and (len(it["blocks"]) > 1 or p["n"] or not p["name"]) else ""
    nm = f"({p['name']})" if p["name"] and p["n"] else ""
    return short(", ".join(x for x in (code, where, " ".join(x for x in (pin, nm) if x)) if x))


def _cid(e: Elem) -> str:
    return e["model"].removeprefix("conductor:")


def rows(pg: Elem) -> list[Elem]:
    """The table rows of a page: every conductor it draws as a wire, a flag or under a summary flag, in the natural order of its label."""
    at = {p["anchor"]: _end(it, b, p) for it in pg["items"] for b in it["blocks"] for p in b["pins"]}
    out: dict[str, Elem] = {}

    def add(cid: str, e: Elem, a: str, b: str, frm: str, to: str) -> None:
        out.setdefault(cid, dict(id=cid, label=e["label"], gauge=e["gauge"], colour=e["colour"], a=a, b=b, frm=frm, to=to))
    for w in pg["wires"]: add(w["id"], w, w["a"], w["b"], at.get(w["a"], w["a"]), at.get(w["b"], w["b"]))
    for f in pg["flags"]:
        for c in f.get("covers") or [None]:
            e, a, b, text = (c, c["at"], c["target"], c.get("text", "")) if c else (f, f["at"], f["target"], f["text"].removeprefix("→ "))
            sheet = f" (sheet {f['sheet']})" if f.get("sheet") and f["kind"] == "continuation" else ""
            cid = c["id"] if c else _cid(f)
            if cid in out and out[cid]["b"] == a and a in at: out[cid]["to"] = at[a]; continue      # both ends on bars of one sheet: the row says both
            add(cid, e, a, b, at.get(a, a), (text or b.removeprefix("pin:")) + sheet)
    for r in out.values():          # where the far end is drawn goes in a column of its own
        m = SEE.search(r["to"])
        r["to"], r["see"] = (r["to"][:m.start()], m.group(1)) if m else (r["to"], "")
    return sorted(out.values(), key=lambda r: (_natural(r["label"]), _natural(r["id"])))


def columns(rs: list[Elem], size: str = "A3") -> tuple[float, ...]:
    """The column offsets (tick box, label, wire, from, to, see, right edge) of the tables of a drawing: the label column as wide as its longest label, the
    rest of the width shared by FROM, TO and SEE (9 : 10 : 10)."""
    total = areas(size)["area"][2]
    lw = min(50.0, max(18.0, max((text_w(r["label"]) for r in rs), default=0.0) + 3.0))
    x = [0.0, 8.0, 8.0 + lw, 8.0 + lw + WIREW]
    rest = total - x[3]
    return (*x, x[3] + rest * 9 / 29, x[3] + rest * 19 / 29, total)


def cells(r: Elem, cols: tuple[float, ...]) -> list[list[str]]:
    """The lines of each cell of a row (label, wire, from, to, see), each broken to its column."""
    wire = " ".join(x for x in (unit(r["gauge"]), colour_words(r["colour"])) if x)
    txt = [r["label"], wire, r["frm"], r["to"], r["see"]]
    return [wrap_all(t, cols[i + 2] - cols[i + 1] - 2, SIZE) or [""] for i, t in enumerate(txt)]


def row_h(r: Elem, cols: tuple[float, ...]) -> float:
    """Height of a row: a line of text for each line its longest cell needs."""
    return ROW * max(len(c) for c in cells(r, cols))


def height(rs: list[Elem], cols: tuple[float, ...]) -> float:
    """Height a table of these rows with its caption row takes at the foot of a sheet, with a gap above it."""
    return ROW + sum(row_h(r, cols) for r in rs) + GAP


def _rule(ax: float, y: float, cols: tuple[float, ...]) -> Elem:
    return dict(kind="line", stroke="thin", x1=ax, y1=y, x2=ax + cols[6], y2=y)


def draw(lines: list[tuple[str, Any]], size: str, y: float, cols: tuple[float, ...]) -> tuple[list[Elem], list[Elem]]:
    """Rules and texts of a table whose caption row is at y: lines are ("head", text) or ("row", row)."""
    ax = areas(size)["area"][0]
    rules: list[Elem] = []
    texts: list[Any] = []
    for i, h in enumerate(HEAD):
        if h: texts.append(S.text(h, ax + cols[i], y + ROW / 2, "left", "caption", SIZE))
    rules.append(_rule(ax, y + ROW, cols))
    y0 = y + ROW
    for kind, v in lines:
        if kind == "head":
            texts.append(S.text(v, ax + cols[1], y0 + ROW / 2, "left", "head", SIZE)); y0 += ROW
            rules.append(_rule(ax, y0, cols)); continue
        cs, h = cells(v, cols), row_h(v, cols)
        rules.append(dict(kind="rect", stroke="thin", fill="none", x=ax + 1, y=y0 + ROW / 2 - 1.25, w=2.5, h=2.5))
        for i, c in enumerate(cs):
            for j, t in enumerate(c):
                if t: texts.append(S.text(t, ax + cols[i + 1], y0 + ROW * (j + 0.5), "left", "pin", SIZE))
        y0 += h
        rules.append(_rule(ax, y0, cols))
    return rules, texts


def flow(groups: list[tuple[int, list[Elem]]], size: str, cols: tuple[float, ...], free: float = 0.0) -> tuple[list[tuple[list[tuple[str, Any]], list[int]]], bool]:
    """The rows of the sheets in `groups` ((sheet number, rows)) in order, headed by `Sheet n`, cut into tables: the first holds up to `free` mm (the room
    under the last drawing sheet, a caption row included) when that is worth using (MIN_FREE), every further one fills a table sheet.
    Returns (lines, sheets shown) per table, and whether the first table is the one under the drawing."""
    ah = areas(size)["area"][3]
    under = free - GAP >= MIN_FREE
    caps = [free - GAP] * under + [ah] * 10 ** 3
    out: list[tuple[list[tuple[str, Any]], list[int]]] = [([], [])]
    used = ROW                                   # the caption row
    for n, rs in groups:
        for i, r in enumerate(rs):
            lines, shown = out[-1]
            head = 0.0 if n in shown else ROW
            if lines and used + head + row_h(r, cols) > caps[len(out) - 1]:
                out.append(([], [])); used, head = ROW, ROW
                lines, shown = out[-1]
            if head: lines.append(("head", f"Sheet {n}" + (" (continued)" if i else ""))); shown.append(n); used += head
            lines.append(("row", r)); used += row_h(r, cols)
    return [t for t in out if t[0]], under


def inline(rs: list[Elem], size: str, cols: tuple[float, ...]) -> tuple[list[Elem], list[Elem]]:
    """The table of one sheet at the foot of the drawing area."""
    ay, ah = areas(size)["area"][1:4:2]
    return draw([("row", r) for r in rs], size, ay + ah - height(rs, cols) + GAP, cols)


def row_data(rs: list[Elem]) -> list[Elem]:
    """The rows as stored on a sheet."""
    return [dict(r) for r in rs]
