"""The wire table of a drawing (docs/drawing-model.md): one row per conductor a sheet shows, so a person can work through the sheet wire by wire.
A sheet's `table` is its rows as data (`sheet["table"] = {"sheet": n where it is drawn, "rows": [...]}`); the table itself is drawn as texts and `rules`
(prims) below the drawing when it fits there, else on table sheets after the last drawing sheet. Text for the wire's two ends comes from the page's
own items (the same words as the flags), colours from exporters/palette.py."""
from __future__ import annotations

from typing import Any

from ..app.workspace import _natural
from ..exporters.palette import words as colour_words
from . import symbols as S
from .style import SIZE, areas, fit

Elem = dict[str, Any]
ROW = 4.5                      # row pitch (mm); a text box is 4.2 mm high
COLS = (0.0, 8.0, 30.0, 88.0, 239.0)   # tick box, label, wire, from, to (offsets from the area's left edge)
WIDTH = 150.0                  # width of the from and to columns
HEAD = ("", "LABEL", "WIRE", "FROM", "TO")
GAP = 5.0                      # between a drawing and the table under it


def _end(it: Elem, b: Elem, p: Elem) -> str:
    """A terminal in words: `EFIS, J1, pin 2 (GND)`; a splice, bus or ground by what it is."""
    code = it["code"]
    if it["symbol"] == "splice": return f"splice {code}"
    if it["symbol"] == "bus": return f"bus {code}"
    if it["symbol"] == "ground": return f"ground bus {code}"
    pin = f"pin {p['n']}" if p["n"] else ""
    where = b["id"] if b["id"] and (len(it["blocks"]) > 1 or p["n"] or not p["name"]) else ""
    nm = f"({p['name']})" if p["name"] and p["n"] else ""
    return ", ".join(x for x in (code, where, " ".join(x for x in (pin, nm) if x)) if x)


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
            add(c["id"] if c else _cid(f), e, a, b, at.get(a, a), (text or b.removeprefix("pin:")) + sheet)
    return sorted(out.values(), key=lambda r: (_natural(r["label"]), _natural(r["id"])))


def height(n: int) -> float:
    """Height a table of n rows with its caption row takes at the foot of a sheet, with a gap above it."""
    return ROW * (n + 1) + GAP


def _rule(ax: float, y: float) -> Elem:
    return dict(kind="line", stroke="thin", x1=ax, y1=y, x2=ax + COLS[4] + WIDTH, y2=y)


def draw(lines: list[tuple[str, Any]], size: str, y: float) -> tuple[list[Elem], list[Elem]]:
    """Rules and texts of a table whose caption row is at y: lines are ("head", text) or ("row", row)."""
    ax = areas(size)["area"][0]
    rules: list[Elem] = []
    texts: list[Any] = []

    def t(s: str, i: int, cy: float, role: str = "pin", w: float = 1e9) -> None:
        if s: texts.append(S.text(fit(s, SIZE, w, role == "head"), ax + COLS[i], cy, "left", role, SIZE))
    for i, h in enumerate(HEAD): t(h, i, y + ROW / 2, "caption")
    rules.append(_rule(ax, y + ROW))
    for k, (kind, v) in enumerate(lines):
        y0 = y + ROW * (k + 1)
        cy = y0 + ROW / 2
        rules.append(_rule(ax, y0 + ROW))
        if kind == "head": t(v, 1, cy, "head"); continue
        rules.append(dict(kind="rect", stroke="thin", fill="none", x=ax + 1, y=cy - 1.25, w=2.5, h=2.5))
        t(v["label"], 1, cy, w=COLS[2] - COLS[1] - 1)
        t(" ".join(x for x in (f"{v['gauge']} AWG" if v["gauge"] else "", colour_words(v["colour"])) if x), 2, cy, w=COLS[3] - COLS[2] - 1)
        t(v["frm"], 3, cy, w=WIDTH - 2)
        t(v["to"], 4, cy, w=WIDTH)
    return rules, texts


def pages(groups: list[tuple[int, list[Elem]]], size: str) -> list[tuple[list[Elem], list[Elem], list[int]]]:
    """Table sheets for the rows of the sheets in `groups` ((sheet number, rows)): (rules, texts, sheets shown) per table sheet."""
    ay, ah = areas(size)["area"][1:4:2]
    cap = int(ah / ROW) - 1
    pgs: list[list[tuple[str, Any]]] = [[]]
    shown: list[list[int]] = [[]]
    for n, rs in groups:
        for i, r in enumerate(rs):
            fresh = n not in shown[-1]
            if pgs[-1] and len(pgs[-1]) + 1 + fresh > cap: pgs.append([]); shown.append([]); fresh = True
            if fresh: pgs[-1].append(("head", f"Sheet {n}" + (" (continued)" if i else ""))); shown[-1].append(n)
            pgs[-1].append(("row", r))
    return [(*draw(lines, size, ay), sh) for lines, sh in zip(pgs, shown) if lines]


def inline(rs: list[Elem], size: str) -> tuple[list[Elem], list[Elem]]:
    """The table of one sheet at the foot of the drawing area."""
    ay, ah = areas(size)["area"][1:4:2]
    return draw([("row", r) for r in rs], size, ay + ah - ROW * (len(rs) + 1))


def row_data(rs: list[Elem]) -> list[Elem]:
    """The rows as stored on a sheet."""
    return [dict(r) for r in rs]
