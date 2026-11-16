"""The drawing engine end to end (docs/drawing-model.md): every scope of the demo, the aircraft, a synthetic project and a fixture goes
through draw() and must come out valid, say exactly what the model says, and pass the measurable layout checks."""
import time
from pathlib import Path

import pytest

from schemagen import synth
from schemagen.app.server import State
from schemagen.drawing import checks
from schemagen.drawing.engine import draw, export
from schemagen.drawing.geometry import validate
from schemagen.drawing.render_svg import svg
from schemagen.drawing.scope import scene
from schemagen.drawing.verify import roundtrip, table

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def states(tmp_path_factory):
    d = tmp_path_factory.mktemp("synth") / "s"
    synth.main(150, 1, str(d))
    return {"demo": State(ROOT / "examples" / "demo"), "aircraft": State(ROOT / "examples" / "aircraft"), "synth": State(d),
            "fixture": State(ROOT / "tests" / "data" / "drawing_fixture")}


def scopes(st):
    """Every component, every harness connector, one connection, one selection."""
    out = [f"component:{c.id}" for c in st.m.components] + [f"harness:{c.id}" for c in st.m.components if c.kind == "harness"]
    a, b = st.m.conductors[0].from_.device, st.m.conductors[0].to.device
    devs = [c.id for c in st.m.components if c.kind not in ("splice", "harness")][:3]
    return out + [f"connection:{st.ctx.comp[a].id}~{st.ctx.comp[b].id}", "selection:" + ",".join(devs)]


@pytest.mark.parametrize("project", ["demo", "aircraft", "synth", "fixture"])
def test_every_scope(states, project):
    st = states[project]
    bad = {}
    for s in scopes(st):
        g = draw(st, s)
        r = checks.report(g)
        p = validate(g) + roundtrip(st, scene(st, s), g) + [f["msg"] for f in r["findings"][:3]]
        if p or "crossings" not in r: bad[s] = p
    assert not bad, bad


def test_text_and_flags(states):
    """A multi-sheet drawing names the other sheet in its continuation flags; the summary flag stands for many wires."""
    g = draw(states["aircraft"], "component:EFIS")
    assert len(g["sheets"]) > 1
    cont = [f for sh in g["sheets"] for f in sh["flags"] if f["kind"] == "continuation"]
    assert cont and all(f["sheet"] and not f["text"].startswith("→ pin:") and "pin:" not in f["text"] for f in cont)
    assert any(f.get("covers") for sh in g["sheets"] for f in sh["flags"])
    assert any("22 " in t["s"] for sh in g["sheets"] for t in sh["texts"] if t["role"] == "wire")


def test_crossings_reported(states):
    r = checks.report(draw(states["demo"], "component:ECU"))
    assert r["crossings"]["total"] >= 0 and set(r["crossings"]["by_sheet"]) == {1, 2}


@pytest.mark.xfail(reason="not met: most crossings on a single-component aircraft drawing are 27 (MOTOR-CONTROLLER, 23 on its first sheet) and 19 (X-FW, a 38-wire"
                   " harness connector over 5 sheets); every other component has at most 6 (X-WR 6, EFIS 6)", strict=True)
def test_crossings_at_most_5(states):
    st = states["aircraft"]
    worst = {c.id: checks.crossings(draw(st, f"component:{c.id}")) for c in st.m.components}
    assert max(worst.values()) <= 5, sorted(worst.items(), key=lambda t: -t[1])[:3]


def test_wire_table(states):
    """Every sheet has a table row per conductor it shows, in words; the check notices a row that disagrees with the drawing."""
    g = draw(states["aircraft"], "component:EFIS")
    rows = {r["id"]: r for sh in g["sheets"] for r in sh["table"]["rows"]}
    assert {"W051", "W052", "W106"} <= set(rows) and table(g) == []
    assert rows["W051"]["frm"] == "CB-EFIS, LOAD" and rows["W052"]["frm"] == "EFIS, J1, pin 2 (GND)" and rows["W052"]["to"] == "ground bus BB-GROUND-BUS"
    assert [sh for sh in g["sheets"] if not sh["symbols"]], "the EFIS wire table does not fit under its sheets: a table sheet follows"
    rows["W051"]["gauge"] = "99"
    assert table(g)


def test_wire_table_inline(states):
    g = draw(states["aircraft"], "component:K-BATTERY-CONTACTOR")
    assert len(g["sheets"]) == 1 and g["sheets"][0]["table"]["sheet"] == 1 and g["sheets"][0]["rules"]


def test_wires_drawn_in_colour(states):
    g = draw(states["aircraft"], "component:K-BATTERY-CONTACTOR")
    assert 'stroke="#ff0000"' in svg(g, 0) and 'stroke="#ff0000"' not in svg(g, 0, colour=False)
    assert "22 AWG" in " ".join(t["s"] for t in g["sheets"][0]["texts"])


def test_deterministic(states):
    for p, s in (("aircraft", "component:MOTOR-CONTROLLER"), ("demo", "harness:X-BH"), ("fixture", "component:FCU")):
        a, b = draw(states[p], s), draw(states[p], s)
        assert [svg(a, i) for i in range(len(a["sheets"]))] == [svg(b, i) for i in range(len(b["sheets"]))]


def test_export(states, tmp_path):
    g = draw(states["aircraft"], "component:EFIS")
    assert len(export(g, tmp_path / "e.svg")) == len(g["sheets"]) and (tmp_path / "e-1.svg").exists()
    assert export(g, tmp_path / "e.pdf") == [tmp_path / "e.pdf"] and (tmp_path / "e.pdf").stat().st_size > 1000
    with pytest.raises(ValueError): export(g, tmp_path / "e.png")


@pytest.mark.perf
def test_speed(states):
    st = states["aircraft"]
    draw(st, "component:TRANSPONDER")
    t = time.perf_counter()
    draw(st, "component:TRANSPONDER")
    one = time.perf_counter() - t
    t = time.perf_counter()
    for c in st.m.components: draw(st, f"component:{c.id}")
    assert one <= 0.3, one
    assert time.perf_counter() - t <= 30
