"""The overview scope (drawing/overview.py): the whole fixture project on one sheet, every conductor drawn once, deterministic."""
from pathlib import Path

import pytest

from schemagen.app.server import State
from schemagen.drawing import checks
from schemagen.drawing.engine import export
from schemagen.drawing.geometry import to_json, validate
from schemagen.drawing.overview import draw

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = {"fixture": ROOT / "tests" / "data" / "drawing_fixture", "demo": ROOT / "examples" / "demo"}


@pytest.mark.parametrize("name", PROJECTS)
def test_overview_draws_every_conductor_once(name, tmp_path):
    st = State(PROJECTS[name])
    g = draw(st)
    assert len(g["sheets"]) == 1
    sh = g["sheets"][0]
    ids = [w["id"] for w in sh["wires"]]
    assert sorted(ids) == sorted(c.id for c in st.m.conductors) and len(set(ids)) == len(ids)   # every conductor exactly once
    assert validate(g) == []                                                                       # the custom sheet size is a valid size
    assert to_json(draw(st)) == to_json(g)                                                         # deterministic
    assert export(g, tmp_path / "overview.pdf")[0].stat().st_size > 1000


def test_overview_has_no_wire_through_a_symbol_on_the_fixture():
    g = draw(State(PROJECTS["fixture"]))
    assert [f for f in checks.report(g)["findings"] if f["check"] == "wire_through_symbol"] == []
