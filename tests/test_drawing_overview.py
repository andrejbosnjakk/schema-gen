"""The overview scope (drawing/overview.py): the whole project on one sheet, every conductor drawn once, deterministic, and the cleanliness gates."""
import sys
from pathlib import Path

import pytest

from schemagen.app.server import State
from schemagen.drawing import checks
from schemagen.drawing.engine import export
from schemagen.drawing.geometry import to_json, validate
from schemagen.drawing.overview import draw

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = {"fixture": ROOT / "tests" / "data" / "drawing_fixture", "demo": ROOT / "examples" / "demo"}
GATES = ("wire_through_symbol", "text_overlaps", "wire_text_overlaps", "wire_overlaps")


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    """A small cut of the fictional large project (2 controllers with 5 sensors each, light grounds): the generator's shape, a few seconds to draw."""
    sys.path.insert(0, str(ROOT / "tools"))
    import make_large_fixture as M
    M.CONTROLLERS, M.SENSORS = 2, 5
    d = tmp_path_factory.mktemp("large") / "p"
    M.main(d, True)
    return d


def gates(g):
    """Findings of the hard gates: through-symbol, text on text or on a foreign wire, collinear wires, a crossing near a dot, end, bend or label, a dot touched."""
    found = [f for f in checks.report(g)["findings"] if f["check"] in GATES]
    return found + checks.crossing_clearance(g) + checks.dot_touch(g)


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


@pytest.mark.parametrize("name", PROJECTS)
def test_overview_hard_gates(name):
    assert gates(draw(State(PROJECTS[name]))) == []


def test_overview_hard_gates_on_the_large_fixture(large):
    st = State(large)
    g = draw(st)
    assert sorted(w["id"] for w in g["sheets"][0]["wires"]) == sorted(c.id for c in st.m.conductors)
    assert gates(g) == []
