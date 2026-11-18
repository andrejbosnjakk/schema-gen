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
    """A multi-sheet drawing is a strip: every flag names the drawing it leads to (and the sheet, when that is this drawing); the summary flag stands for many wires."""
    g = draw(states["aircraft"], "component:EFIS")
    assert len(g["sheets"]) > 1
    flags = [f for sh in g["sheets"] for f in sh["flags"]]
    assert flags and all("(drawing " in f["text"] and "pin:" not in f["text"] for f in flags)
    assert any("(drawing EFIS, sheet " in f["text"] for f in flags)
    assert any(f.get("covers") for sh in g["sheets"] for f in sh["flags"])
    assert any("22 " in t["s"] for sh in g["sheets"] for t in sh["texts"] if t["role"] == "wire")


def test_crossings_reported(states):
    r = checks.report(draw(states["demo"], "component:ECU"))
    assert r["crossings"]["total"] >= 0 and set(r["crossings"]["by_sheet"]) == {1, 2}


def test_crossings_at_most_5(states):
    st = states["aircraft"]
    worst = {c.id: checks.crossings(draw(st, f"component:{c.id}")) for c in st.m.components}
    assert max(worst.values()) <= 5, sorted(worst.items(), key=lambda t: -t[1])[:3]


def test_jumpers_and_units_and_odd_terminals(states):
    """Fictional fixture parts that broke a real project: wires between two pins of one connector (drawn as two flags, never through the
    block), a gauge that already says AWG (printed once), and a 3-terminal battery written with pin numbers and no connector name."""
    st = states["fixture"]
    for s in ("component:JMP", "component:BATX"):
        g = draw(st, s)
        assert checks.report(g)["findings"] == [] and roundtrip(st, scene(st, s), g) == [], s
        texts = [t["s"] for sh in g["sheets"] for t in sh["texts"]]
        assert any("22 AWG" in t for t in texts) and not any("AWG AWG" in t for t in texts)
    g = draw(st, "component:JMP")
    assert not [f for f in checks.wire_through_symbol(g)] and sum(f["kind"] == "off_sheet" for sh in g["sheets"] for f in sh["flags"]) >= 4


def test_checks_catch_the_defects(states):
    """The rules behind the real-project defects: a wire through a block, two wires on one line, the unit twice."""
    g = draw(states["fixture"], "component:JMP")
    sh = g["sheets"][0]
    s = sh["symbols"][0]
    w = dict(sh["wires"][0], id="X1", points=[[s["x"] - 5, s["y"] + s["h"] / 2 // 5 * 5], [s["x"] + s["w"] + 5, s["y"] + s["h"] / 2 // 5 * 5]])
    assert checks.wire_through_symbol(dict(g, sheets=[dict(sh, wires=[w])]))
    a = dict(sh["wires"][0], id="A", model="conductor:A", points=[[0.0, 5.0], [50.0, 5.0]])
    b = dict(a, id="B", model="conductor:B", points=[[20.0, 5.0], [70.0, 5.0]])
    assert checks.wire_overlaps(dict(g, sheets=[dict(sh, wires=[a, b])]))
    assert checks.gauge_unit(dict(g, sheets=[dict(sh, wires=[dict(a, gauge="22 AWG")])]))
    assert checks.gauge_unit(dict(g, sheets=[dict(sh, texts=[dict(sh["texts"][0], s="W1 22 AWG AWG BK")])]))


def test_wire_table(states):
    """Every sheet has a table row per conductor it shows, in words; the check notices a row that disagrees with the drawing."""
    g = draw(states["aircraft"], "component:EFIS")
    rows = {r["id"]: r for sh in g["sheets"] for r in sh["table"]["rows"]}
    assert {"W051", "W052", "W106"} <= set(rows) and table(g) == []
    assert rows["W051"]["frm"] == "EFIS, J1, pin 1 (POWER)" and rows["W051"]["to"].startswith("Breaker 'EFIS' 5 A, LOAD")
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
