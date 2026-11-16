"""Quality checks over hand-made tiny geometries (schemagen/drawing/checks.py)."""
import time
from typing import Any

from schemagen.drawing import checks as C


def sym(i: str, x: float, y: float, w: float = 20, h: float = 10, anchors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": i, "kind": "block", "model": f"component:{i}", "x": x, "y": y, "w": w, "h": h, "anchors": anchors or [], "prims": []}


def anc(i: str, x: float, y: float) -> dict[str, Any]:
    return {"id": i, "model": i, "x": x, "y": y, "side": "R"}


def wire(i: str, pts: list[list[float]], a: str = "", b: str = "") -> dict[str, Any]:
    return {"id": i, "model": f"conductor:{i}", "label": i, "gauge": "20", "colour": "WH", "hex": "#fff", "weight": "light",
            "points": pts, "a": a, "b": b, "pair": "", "shield": "", "fault": None}


def txt(s: str, x: float, y: float, w: float = 10, h: float = 3, size: float = 2.5, model: str = "") -> dict[str, Any]:
    return {"s": s, "x": x, "y": y, "w": w, "h": h, "size_mm": size, "align": "left", "model": model, "role": ""}


def geo(**kw: Any) -> Any:
    sh = {"n": 1, "of": 1, "size": "A4", "w_mm": 297.0, "h_mm": 210.0, "grid_mm": 5.0, "symbols": [], "wires": [], "texts": [],
          "flags": [], "notes": [], "legend": [], "title_block": {}, **kw}
    return {"version": 1, "drawing": {}, "sheets": [sh]}


def clean() -> Any:
    return geo(symbols=[sym("A", 10, 10, anchors=[anc("pin:A/1", 30, 15)]), sym("B", 60, 10, anchors=[anc("pin:B/1", 60, 15)])],
               wires=[wire("W1", [[30, 15], [60, 15]], "pin:A/1", "pin:B/1")],
               texts=[txt("A", 11, 11, model="component:A"), txt("W1", 40, 11, model="conductor:W1")])


def test_clean_passes_everything() -> None:
    r = C.report(clean())
    assert r["ok"] and r["findings"] == [] and r["crossings"]["total"] == 0


def test_text_overlaps() -> None:
    f = C.text_overlaps(geo(texts=[txt("a", 10, 10), txt("b", 15, 11)]))
    assert len(f) == 1 and f[0]["check"] == "text_overlaps"
    assert C.text_overlaps(geo(texts=[txt("a", 10, 10), txt("b", 20, 10), txt("c", 10, 13)])) == []   # touching edges


def test_text_symbol_overlaps() -> None:
    g = geo(symbols=[sym("A", 10, 10)], texts=[txt("own", 11, 11, model="component:A"), txt("alien", 15, 15, model="component:Z")],
            flags=[{"id": "f1", "model": "conductor:W9", "x": 100, "y": 100, "w": 10, "h": 5, "text": "", "target": "", "sheet": None, "kind": "off_sheet"}])
    g["sheets"][0]["texts"].append(txt("onflag", 102, 101))
    assert sorted(x["ids"][0] for x in C.text_symbol_overlaps(g)) == ["alien", "onflag"]


def test_wire_through_symbol() -> None:
    g = geo(symbols=[sym("A", 10, 10, anchors=[anc("pin:A/1", 30, 15)]), sym("B", 40, 10)],
            wires=[wire("W1", [[30, 15], [70, 15]], "pin:A/1", "x")])
    f = C.wire_through_symbol(g)
    assert [x["ids"] for x in f] == [["W1", "B"]]                      # own anchor edge is fine, B is crossed
    assert C.wire_through_symbol(geo(symbols=[sym("A", 10, 10)], wires=[wire("W", [[0, 10], [50, 10]])])) == []  # along the edge


def test_wire_text_overlaps() -> None:
    g = geo(wires=[wire("W1", [[0, 15], [50, 15]])], texts=[txt("own", 10, 14, model="conductor:W1"), txt("other", 30, 14)])
    assert [x["ids"][1] for x in C.wire_text_overlaps(g)] == ["other"]


def test_off_grid_and_diagonal() -> None:
    f = C.off_grid(geo(wires=[wire("W1", [[0, 0], [12, 0]]), wire("W2", [[0, 5], [10, 10]])]))
    assert sorted(x["ids"][0] for x in f) == ["W1", "W2"]


def test_wire_overlaps() -> None:
    g = geo(wires=[wire("W1", [[0, 10], [50, 10]]), wire("W2", [[30, 10], [80, 10]]), wire("W3", [[50, 10], [60, 10]])])
    assert sorted(x["ids"] for x in C.wire_overlaps(g)) == [["W1", "W2"], ["W2", "W3"]]   # W1/W3 only touch at x=50


def test_crossings_grid_3x2() -> None:
    hs = [wire(f"H{y}", [[0, y], [50, y]]) for y in (10, 20, 30)]
    vs = [wire(f"V{x}", [[x, 5], [x, 40]]) for x in (15, 35)]
    g = geo(wires=hs + vs)
    assert C.crossings(g) == 6 and C.crossings_by_sheet(g) == {1: 6}
    # touching ends and a T junction are not crossings; a wire never crosses itself
    assert C.crossings(geo(wires=[wire("A", [[0, 10], [20, 10]]), wire("B", [[20, 0], [20, 10]]), wire("C", [[10, 10], [10, 30]])])) == 0


def test_out_of_sheet_and_min_text() -> None:
    g = geo(wires=[wire("W", [[0, 0], [300, 0]])], symbols=[sym("A", -5, 10)], texts=[txt("small", 10, 10, size=2.0)])
    assert len(C.out_of_sheet(g)) == 2
    assert [x["ids"] for x in C.min_text(g)] == [["small"]]


def test_speed_500_segments_1500_texts() -> None:
    texts = [txt(f"t{i}", 7 * (i % 60), 11 * (i // 60) + 2, w=6, h=3) for i in range(1500)]
    wires = []
    for i in range(250):
        x, y = 5 * (i % 80), 10 * (i // 80)
        wires.append(wire(f"W{i}", [[x, y], [x, y + 5], [x + 15, y + 5]]))
    g = geo(wires=wires, texts=texts, w_mm=420.0, h_mm=297.0)
    t0 = time.perf_counter()
    r = C.report(g)
    dt = time.perf_counter() - t0
    print(f"report on 500 segments, 1500 texts: {dt:.3f} s")
    assert dt < 1.0 and "counts" in r
