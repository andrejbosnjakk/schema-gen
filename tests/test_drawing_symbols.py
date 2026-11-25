"""Symbols, style and the SVG and PDF renderers of the drawing engine (docs/drawing-model.md)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import pytest

from schemagen.drawing import style as st
from schemagen.drawing import symbols as S
from schemagen.drawing.geometry import validate
from schemagen.drawing.render_pdf import pdf
from schemagen.drawing.render_svg import svg
from schemagen.drawing.sheet import _blk, _item, _pin, symbol_sheet

KINDS = ["block", "far", "harness", "splice", "ground", "bus", "breaker", "fuse", "switch", "relay", "terminator", "battery", "dcdc"]


def make(kind: str, n: int) -> dict[str, Any]:
    """An item of `kind` with n pins (poles for a switch or relay)."""
    two = lambda c, a, b: [_blk(a, [_pin(c, a, "")]), _blk(b, [_pin(c, b, "")])]  # noqa: E731
    if kind in ("block", "far"):
        ps = [_pin("U", "J1", str(i), f"Signal {i}", spare=i % 5 == 0) for i in range(1, n + 1)]
        return _item("U", "block", [_blk("J1", ps, "PN-1", "P1"), _blk("J2", [_pin("U", "J2", "1", "x")])], name="Unit", part="PN-9", loc="Bay",
                     partial=kind == "far",
                     role="far_end" if kind == "far" else "in_scope")
    if kind == "harness":
        return _item("X", "harness", [_blk("Cabin half", [_pin("X", "Cabin half", str(i), spare=i == 2) for i in range(1, n + 1)], "H1", "H2", "near"),
                                      _blk("Wing half", [_pin("X", "Wing half", str(i)) for i in range(1, n + 1)], side="far")], role="harness")
    if kind in ("splice", "ground"):
        return _item("SP-LONG-NAME-1", kind, [_blk("S", [_pin("SP-LONG-NAME-1", "S", "")])], role="part", function_class="GND")
    if kind == "bus": return _item("BB", "bus", [_blk("Stud", [_pin("BB", "Stud", str(i)) for i in range(1, n + 1)])], role="part", function_class="14 V")
    if kind in ("breaker", "fuse"): return _item("CB", kind, two("CB", "LINE", "LOAD"), role="part", rating_a=7.5, panel="P")
    if kind == "terminator": return _item("R", "terminator", two("R", "1", "2"), role="part", value="120 Ω")
    if kind == "battery": return _item("B", "battery", [_blk("+", [_pin("B", "+", "")]), _blk("-", [_pin("B", "-", "")])], role="part", voltage=12.0)
    if kind == "dcdc": return _item("D", "dcdc", [_blk("PINS", [_pin("D", "PINS", str(i), "IN+" if i % 2 else "OUT+") for i in range(1, n + 1)])],
                                       role="part", voltage=5.0)
    if kind == "switch":
        t = [_blk(str(i), [_pin("S", str(i), "")]) for i in range(1, 2 * n + 1)]
        return _item("S", "switch", t, role="part", contacts=[dict(a=f"pin:S/{2 * i + 1}/", b=f"pin:S/{2 * i + 2}/") for i in range(n)], coil=None)
    t = [_blk(str(i), [_pin("K", str(i), "")]) for i in range(1, 3 * n + 3)]
    return _item("K", "relay", t, role="part", contacts=[dict(com=f"pin:K/{3 * i + 1}/", no=f"pin:K/{3 * i + 2}/", nc=f"pin:K/{3 * i + 3}/") for i in range(n)],
                 coil=dict(a1=f"pin:K/{3 * n + 1}/", a2=f"pin:K/{3 * n + 2}/"))


def on(v: float, g: float = 5.0) -> bool:
    return abs(v / g - round(v / g)) < 1e-6


def boxes_overlap(a: dict[str, Any], b: dict[str, Any], tol: float = 0.0) -> bool:
    return a["x"] + tol < b["x"] + b["w"] and b["x"] + tol < a["x"] + a["w"] and a["y"] + tol < b["y"] + b["h"] and b["y"] + tol < a["y"] + a["h"]


def segments(sym: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    out = []
    for p in sym["prims"]:
        if p["kind"] == "line": out.append((p["x1"], p["y1"], p["x2"], p["y2"]))
        elif p["kind"] == "rect":
            x, y, w, h = p["x"], p["y"], p["w"], p["h"]
            out += [(x, y, x + w, y), (x + w, y, x + w, y + h), (x + w, y + h, x, y + h), (x, y + h, x, y)]
        elif p["kind"] == "polyline":
            pts = p["points"] + ([p["points"][0]] if p.get("closed") else [])
            out += [(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])]
    return out


def hits(seg: tuple[float, float, float, float], t: dict[str, Any], tol: float = 0.1) -> bool:
    x1, y1, x2, y2 = seg
    n = max(2, int(max(abs(x2 - x1), abs(y2 - y1)) / 0.05))
    return any(t["x"] + tol < x1 + (x2 - x1) * i / n < t["x"] + t["w"] - tol and t["y"] + tol < y1 + (y2 - y1) * i / n < t["y"] + t["h"] - tol for i in range(n + 1))


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("n", [1, 2, 25, 60])
def test_symbol_rules(kind: str, n: int) -> None:
    item = make(kind, n)
    sym, texts = S.build(item, 20.0, 35.0)
    assert (sym["x"], sym["y"]) == (20.0, 35.0)
    assert on(sym["w"]) and on(sym["h"]) and sym["w"] > 0 and sym["h"] > 0
    assert S.size(item) == (sym["w"], sym["h"])
    ids = [a["id"] for a in sym["anchors"]]
    assert len(ids) == len(set(ids)) and ids
    for a in sym["anchors"]:
        assert on(a["x"]) and on(a["y"]), a
        edge = {"L": a["x"] == sym["x"], "R": a["x"] == sym["x"] + sym["w"], "T": a["y"] == sym["y"], "B": a["y"] == sym["y"] + sym["h"]}
        assert edge[a["side"]], (kind, a)
        assert sym["y"] <= a["y"] <= sym["y"] + sym["h"]
    for t in texts:
        assert t["size_mm"] >= st.MIN_TEXT
        assert t["x"] >= sym["x"] - 1e-6 and t["x"] + t["w"] <= sym["x"] + sym["w"] + 1e-6, (kind, t)
        assert t["y"] >= sym["y"] - 1e-6 and t["y"] + t["h"] <= sym["y"] + sym["h"] + 1e-6, (kind, t)
    for i, a in enumerate(texts):
        for b in texts[i + 1:]: assert not boxes_overlap(a, b), (kind, a["s"], b["s"])
    for seg in segments(sym):
        for t in texts: assert not hits(seg, t), (kind, t["s"], seg)


def test_unlisted_pins_and_empty_values_do_not_break() -> None:
    blank = _item("E", "block", [], role="far_end", partial=True)
    sym, texts = S.build(blank)
    assert sym["w"] >= 30 and not sym["anchors"]
    for kind in ("breaker", "fuse", "terminator", "battery", "switch", "relay", "dcdc", "bus", "splice", "ground", "harness"):
        it = make(kind, 1)
        it["blocks"], it["attrs"], it["part"], it["name"] = [], {}, "", it["code"]
        S.build(it)


def test_sides_choose_the_edge() -> None:
    it = make("block", 3)
    sym, _ = S.build(it, 0, 0, {p["anchor"]: "L" for p in it["blocks"][0]["pins"]})
    assert {a["side"] for a in sym["anchors"] if "J1" in a["id"]} == {"L"} and all(a["x"] == 0 for a in sym["anchors"] if "J1" in a["id"])
    part = make("far", 3); part["role"] = "in_scope"
    sym, _ = S.build(part)
    assert {a["side"] for a in sym["anchors"] if "J1" in a["id"]} == {"R"}   # in_scope partial default: R
    far = make("far", 3); far["role"] = "far_end"
    far["blocks"] = [b for b in far["blocks"] if b["id"] == "J1"]
    sym, _ = S.build(far)
    assert {a["side"] for a in sym["anchors"]} == {"L"}
    sym, _ = S.build(make("breaker", 1), 0, 0, {"pin:CB/LINE/": "R"})
    assert {a["id"]: a["side"] for a in sym["anchors"]} == {"pin:CB/LINE/": "R", "pin:CB/LOAD/": "L"}
    sym, _ = S.build(make("harness", 2), 0, 0, {"pin:X/Cabin half/1": "R", "pin:X/Wing half/1": "L"})
    assert next(a for a in sym["anchors"] if a["id"] == "pin:X/Cabin half/1")["side"] == "R"


def test_spare_pins_have_no_anchor() -> None:
    sym, _ = S.build(make("block", 10))
    assert "pin:U/J1/5" not in [a["id"] for a in sym["anchors"]] and "pin:U/J1/4" in [a["id"] for a in sym["anchors"]]


def test_text_width_is_conservative_and_monotonic() -> None:
    assert st.text_w("", 2.5) == 0 and st.text_w("iiii") < st.text_w("WWWW") and st.text_w("abc", 5) > st.text_w("abc", 2.5)
    assert st.text_w("Name", 2.5, True) > st.text_w("Name", 2.5)
    # Inter "Hello" is 2.9 em wide at 1000 units/em: 0.690+0.591+0.242+0.242+0.609 em = 2.374 em; cap 2.5 mm is em 3.436 mm
    assert st.text_w("Hello", 2.5) >= 0.1 * 0 + (690 + 571 + 242 + 242 + 612) / 1000 * st.em(2.5)
    assert st.glyphs("→ X") == "-> X"


def test_areas_are_on_the_grid() -> None:
    for size in ("A3", "A4"):
        for k, r in st.areas(size).items():
            assert all(on(v) for v in r), (size, k, r)


def test_flag_geometry() -> None:
    f = S.flag("flag:W1", "conductor:W1", "off_sheet", "→ CB-MAIN 30 A LOAD", "pin:CB/LOAD/", None, 10, 20)
    assert on(f["w"]) and on(f["h"]) and f["h"] == 10 and f["kind"] == "off_sheet"
    pr, tx = S.flag_shapes(f)
    assert pr and tx and all(f["x"] <= t["x"] and t["x"] + t["w"] <= f["x"] + f["w"] for t in tx)
    c = S.flag("flag:W2", "conductor:W2", "continuation", "pin:A/J1/1", "pin:A/J1/1", 3)
    assert {t["s"] for t in S.flag_shapes(c)[1]} >= {"3"}


def test_symbol_sheet_validates_and_renders() -> None:
    g = symbol_sheet()
    assert validate(g) == []
    assert len(g["sheets"]) == 3
    texts = [t for sh in g["sheets"] for t in sh["texts"]]
    assert all(t["size_mm"] >= 2.5 for t in texts)
    kinds = {s["kind"] for s in g["sheets"][0]["symbols"]}
    assert kinds >= {"block", "harness", "splice", "bus", "ground", "breaker", "fuse", "switch", "relay", "terminator", "battery", "dcdc"}
    assert {f["kind"] for sh in g["sheets"] for f in sh["flags"]} == {"off_sheet", "continuation"}


def test_svg_is_deterministic_and_well_formed() -> None:
    a, b = svg(symbol_sheet()), svg(symbol_sheet())
    assert a == b
    root = ET.fromstring(a)
    assert root.tag.endswith("svg") and root.get("viewBox") == "0 0 420 297"
    assert 'data-model="component:ECU"' in a and 'data-model="conductor:W001"' in a
    assert re.search(r"<polyline[^>]*stroke-width=\"1.1\"", a)   # the heavy wire
    assert "<text" in a and "Inter" in a
    assert svg(symbol_sheet(), 1) != a and svg(symbol_sheet(), 0, colour=False) != a
    assert "font-face" in svg(symbol_sheet(), 0, embed_font=True)


def test_pdf_has_one_page_per_sheet(tmp_path: Any) -> None:
    g = symbol_sheet()
    p = tmp_path / "a.pdf"
    assert pdf(g, p) == 3
    data = p.read_bytes()
    assert data.startswith(b"%PDF") and len(re.findall(rb"/Type\s*/Page\b", data)) == 3
    q = tmp_path / "b.pdf"
    pdf(g, q)
    assert q.read_bytes() == data   # deterministic


def test_narrow_flag_is_narrower_and_drawn_with_the_same_lines():
    """A narrow flag breaks its text into more, shorter lines; the renderer draws exactly those lines (no text lost)."""
    text = "+ 9 more wires on BB-BUS-STRIP-POWERTRAIN-PANEL (drawing BB-BUS-STRIP-POWERTRAIN-PANEL)"
    wide, narrow = S.flag("f", "m", "off_sheet", text, ""), S.flag("f", "m", "off_sheet", text, "", narrow=True)
    assert narrow["w"] < wide["w"] and narrow["h"] > wide["h"] and narrow.get("narrow") and "narrow" not in wide
    _, texts = S.flag_shapes(narrow)
    assert " ".join(t["s"] for t in texts).split() == text.split()
    assert max(st.text_w(t["s"], st.SIZE) for t in texts) <= narrow["w"]
