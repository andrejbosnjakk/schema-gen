"""The overview scope (drawing/overview.py): the whole fixture project on one sheet, every conductor drawn once, deterministic."""
from pathlib import Path

from schemagen.app.server import State
from schemagen.drawing.engine import export
from schemagen.drawing.geometry import to_json
from schemagen.drawing.overview import draw

ROOT = Path(__file__).resolve().parent


def test_overview_of_the_fixture(tmp_path):
    st = State(ROOT / "data" / "drawing_fixture")
    g = draw(st)
    assert len(g["sheets"]) == 1
    sh = g["sheets"][0]
    ids = [w["id"] for w in sh["wires"]]
    assert sorted(ids) == sorted(c.id for c in st.m.conductors) and len(set(ids)) == len(ids)   # every conductor exactly once
    assert all(len(w["points"]) >= 2 for w in sh["wires"])
    assert to_json(draw(st)) == to_json(g)                                                         # deterministic
    out = export(g, tmp_path / "overview.pdf")[0]
    assert out.stat().st_size > 1000
