"""0.7 item 2: the readable sheet (plain names, connector / pin text, subsystem bars and component headers)."""
import json

import pytest
from openpyxl import Workbook, load_workbook

from schemagen import synth_readable
from schemagen.cli import main
from schemagen.cli.commands import names_changeset
from schemagen.core import changes as ch
from schemagen.core.context import Ctx
from schemagen.core.load import load
from schemagen.core.rules import run_rules
from schemagen.exporters import pinout
from schemagen.importers import readable as rd


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    d = tmp_path_factory.mktemp("readable")
    synth_readable.main(500, 1, str(d / "clean"), clean=True)
    synth_readable.main(500, 1, str(d / "seeded"))
    return d


def cells(path):
    return [list(r) for r in load_workbook(path).worksheets[0].iter_rows(values_only=True)]


@pytest.mark.parametrize("text,want", [
    ("pin 3", ("", "3")), ("X1.A", ("X1", "A")), ("J2, pin C3", ("J2", "C3")), ("terminal 87 (NO)", ("", "87")),
    ("positive terminal (M6)", ("+", "")), ("cockpit side, pin 19", ("cockpit side", "19")), ("splice", ("Splice", "")),
    ("stud", ("Stud", "")), ("load side", ("LOAD", "")), ("line side", ("LINE", "")), ("lead 1", ("lead", "1")),
    ("coil - (black lead)", ("coil", "-")), ("", ("", "")), ("  pin   12 ", ("", "12")),
    ("red lead", ("lead", "red")), ("brown lead (control)", ("lead", "brown")), ("line stud", ("line stud", "")),
    ("A1 (+) M8 stud (battery side)", ("", "A1")), ("A2 (-) M8 stud", ("", "A2")), ("out", ("out", "")), ("3, in", ("3", "in")),
    ("2, drop", ("2", "drop")), ("fuse holder lead", ("fuse holder lead", "")), ("lead", ("lead", "")),
    ("LV1 output (SurLok plug)", ("LV1 output", "")), ("Connector, V_in 5 V", ("Connector", "V_in 5 V")), ("TNC", ("TNC", "")),
    ("tip + ring", ("tip + ring", "")), ("safety loop in", ("safety loop in", "")),
    ("see drawing", None), ("pin ?", None), ("TBD", None), ("J?", None), ("pin 3 or 4", None)])
def test_grammar(text, want):
    assert rd.parse_cp(text) == want
    if want: assert rd.parse_cp(rd.format_cp(*want)) == want  # the canonical form reads back the same


REAL_FORMS = ["red lead", "black lead", "brown lead (control)", "yellow lead (sensor)", "line stud", "load stud", "feed stud",
              "A1 (+) M8 stud (battery side)", "A2 (-) M8 stud", "in", "out", "output", "3, in", "3, out", "2, drop", "fuse output",
              "fuse holder lead", "lead to ground bus", "lead", "LV1 output (SurLok plug)", "Connector, GND", "Connector, V_in 5 V",
              "Connector, Signal", "TNC", "BNC", "QMA", "tip", "tip + ring", "sleeve", "loop in", "loop out", "safety loop in",
              "coil - (black lead)", "coil − (black lead)", "Coil connector, − / case", "pin 2, black lead",
              "pin 1, red lead (kit fuse)", "DC barrel 5.5×2.1, centre", "DC barrel 5.5×2.1, sleeve"]


def test_real_forms_in_fixture_and_parse_rate(fixtures):
    """Every written form is in the fixture, and at least 98 % of its cells parse (the rest are the seeded ones)."""
    cs = [r[c] for r in cells(fixtures / "seeded" / "wires.xlsx")[1:] if r[2] is not None for c in (3, 5)]
    assert set(REAL_FORMS) <= set(cs)
    assert sum(rd.parse_cp(x) is not None for x in cs) / len(cs) >= 0.98


def test_round_trip_is_cell_identical(fixtures, tmp_path):
    assert main(["export", str(fixtures / "clean"), "--readable", "-o", str(tmp_path / "out.xlsx")]) == 0
    a, b = cells(fixtures / "clean" / "wires.xlsx"), cells(tmp_path / "out.xlsx")
    assert sum(r[0] is not None and r[2] is not None for r in a[1:]) >= 500
    assert a == b
    wb = load_workbook(tmp_path / "out.xlsx")
    assert len(wb.active.merged_cells.ranges) == len(load_workbook(fixtures / "clean" / "wires.xlsx").active.merged_cells.ranges)


def test_edited_cells_export_in_canonical_form(fixtures, tmp_path):
    L = load(fixtures / "clean")
    m = L.model.model_copy(deep=True)
    m.conductors[0].from_.connector, m.conductors[0].from_.pin = "J9", "4"
    rd.export(m, tmp_path / "e.xlsx")
    row = next(r for r in cells(tmp_path / "e.xlsx") if r[0] == m.conductors[0].label)
    assert row[3] == "J9, pin 4"


def test_clean_fixture_checks_and_pinout(fixtures, tmp_path):
    L = load(fixtures / "clean")
    found = run_rules(L.model, L.cfg)
    assert not [i for i in found if i.severity in ("error", "warning")], [(i.rule, i.message) for i in found][:5]
    kinds = {c.kind for c in L.model.components}
    assert {"harness", "breaker", "splice", "bus", "switch", "relay", "device"} <= kinds
    assert next(c for c in L.model.components if c.name == "Ground bus").kind == "bus"
    pinout.write_xlsx(L.model, tmp_path / "p.xlsx", Ctx(L.model, L.cfg))  # the per-component checklist straight from the sheet
    assert main(["check", str(fixtures / "clean")]) == 0
    assert not [w for w in L.warnings if "look like one device" in w]  # 0 false merges on the clean fixture
    assert names_changeset(L)[1] == []


def test_seeded_cells_flagged_and_parse_rate(fixtures):
    L = load(fixtures / "seeded")
    seeds = json.loads((fixtures / "seeded" / "seeds.json").read_text(encoding="utf-8"))
    flagged = [i for i in run_rules(L.model, L.cfg) if i.rule == "readable-cell"]
    want = {(r, c) for r, c, _ in seeds["unparseable"]}
    got = {(int(i.message.split("row ")[1].split(",")[0]), i.message.split("column '")[1].split("'")[0]) for i in flagged}
    assert got == want  # 100 % of the cells that do not parse are flagged, at their sheet row and column
    total = 2 * len(L.model.conductors)
    assert 1 - len(flagged) / total >= 0.98


def test_seeded_near_duplicates_found_and_merged(fixtures, tmp_path):
    d = tmp_path / "s"
    import shutil
    shutil.copytree(fixtures / "seeded", d)
    L = load(d)
    seeds = json.loads((d / "seeds.json").read_text(encoding="utf-8"))
    cs, pairs = names_changeset(L)
    assert dict(pairs) == seeds["typos"]  # every seeded variant, merged into the name it came from
    ch.save(d, cs)
    L2 = load(d)
    assert names_changeset(L2)[1] == [] and not {c.name for c in L2.model.components} & set(seeds["typos"])
    assert main(["fix", "names", str(d)]) == 0  # nothing left


def test_near_duplicate_guards():
    pairs = rd.near_duplicates(["Nav light left", "Nav light right", "Pump 1", "Pump 2", "Light A", "Light B", "Beacon upper",
                                "Beacon lower", "Fuel pump", "fuel  pump", "Firewall connector", "Firwall connector"])
    assert sorted(pairs) == sorted([("fuel  pump", "Fuel pump"), ("Firwall connector", "Firewall connector")])


def test_components_tab_overrides(tmp_path):
    wb = Workbook(); ws = wb.active; ws.title = "Wires"
    ws.append(rd.HEAD)
    ws.append(["Lighting"])
    ws.append(["L1", "lamp feed", "Sling panel", "pin 1", "Tail lamp", "pin 1", "14 V", 1.0, 22, 2.0, 6.0])
    ws.append(["L2", "lamp return", "Tail lamp", "pin 2", "Ground stud", "stud", "GND", 1.0, 22, 2.0, 6.0])
    cp = wb.create_sheet("Components"); cp.append(["Name", "Kind", "Code", "Location", "Part"])
    cp.append(["Sling panel", "", "PNL-1", "cockpit", "PN-77"]); cp.append(["Ground stud", "bus", "", "", ""])
    wb.save(tmp_path / "w.xlsx")
    (tmp_path / "schemagen.yml").write_text("source: {path: w.xlsx}\n", encoding="utf-8")  # format detected from the header
    m = load(tmp_path).model
    c = {x.name: x for x in m.components}
    assert (c["Sling panel"].id, c["Sling panel"].zone, c["Sling panel"].part) == ("PNL-1", "cockpit", "PN-77")
    assert c["Ground stud"].kind == "bus" and c["Tail lamp"].kind == "device"
    assert m.conductors[0].subsystem == "Lighting"


def test_default_sides_and_override(fixtures, tmp_path):
    """cockpit / fuselage / cabin side are near and nose / tank / wing / back cabin / side-wall sensor side far by default."""
    L = load(fixtures / "clean")
    got = {h: s for halves in L.cfg.sides.values() for h, s in halves.items()}
    assert {h: got[h] for h in ("cockpit side", "fuselage side", "cabin side")} == dict.fromkeys(("cockpit side", "fuselage side", "cabin side"), "near")
    assert all(got[h] == "far" for h in ("nose side", "tank side", "wing side", "back cabin side", "side-wall sensor side"))
    import shutil
    shutil.copytree(fixtures / "clean", tmp_path / "o")
    y = tmp_path / "o" / "schemagen.yml"
    y.write_text(y.read_text(encoding="utf-8").replace("engine side: far", "engine side: far\n    nose side: near"), encoding="utf-8")
    assert {h: s for halves in load(tmp_path / "o").cfg.sides.values() for h, s in halves.items()}["nose side"] == "near"


def test_can_trunk_and_stubs_have_no_direction(fixtures):
    """CAN1 / GCAN / CAN_H / CAN_L names and wires between CAN splices are CAN, never judged as one-way signals."""
    from schemagen.core import direction
    L = load(fixtures / "clean")
    ctx = Ctx(L.model, L.cfg)
    can = [i for i, c in enumerate(L.model.conductors) if c.extra.get("readable", {}).get("header") == "CAN bus"]
    assert len(can) == 12 and all(L.model.conductors[i].kind == "CAN" for i in can)
    assert {L.model.conductors[i].can for i in can if "L" in L.model.conductors[i].name.split()[1]} == {"CAN_L"}
    assert next(c for c in L.model.conductors if c.name == "Bus link").kind == "CAN"  # between CAN splices, no CAN in its name
    assert not set(can) & ({f.index for f in direction.analyse(ctx)} | set(direction.unknown(ctx)))


def test_text_in_number_columns_round_trips(fixtures):
    """TBD / TBC in Current (A), Length (m) and Weight (g) are written back as read."""
    rows = [r for r in cells(fixtures / "clean" / "wires.xlsx") if r[1] and str(r[1]).startswith("Spare outlet")]
    assert {"TBD", "TBC", "n/a"} <= {v for r in rows for v in r[7:11]}
    L = load(fixtures / "clean")
    assert sum(isinstance(c.extra.get("amps"), str) for c in L.model.conductors) == 2


@pytest.mark.parametrize("name,code", [("Firewall connector PSW", "PSW"), ("Connector X-FW2", "X-FW2"), ("HPW connector", "HPW"),
                                       ("Tank connector BC1 (D-SUB 25)", "BC1"), ("Wing connector X-WL", "X-WL"), ("Firewall connector", "")])
def test_harness_code_from_name(name, code):
    assert rd.name_code(name) == code


def test_fixture_harness_codes_are_the_names_codes(fixtures):
    L = load(fixtures / "clean")
    hs = [c for c in L.model.components if c.kind == "harness"]
    assert hs and all(c.id == rd.name_code(c.name) and c.id in c.name.split() for c in hs)


@pytest.mark.parametrize("text,n", [("D-sub 25", 25), ("Panel connector X-IP (D-SUB 25)", 25), ("DB25", 25), ("DE-9", 9),
                                    ("Deutsch DT 12-pin", 12), ("4 way", 4), ("J1", None), ("Connector X-FW2", None)])
def test_connector_size(text, n):
    from schemagen.core.classes import connector_size
    assert connector_size(text) == n


def test_connector_size_shows_spares(fixtures, tmp_path):
    """A 25-way D-sub with one pin pair used is a 25-pin connector (24 spares), not a 3-pin one; the same for a device's J1."""
    import shutil

    import yaml

    from schemagen.cli.draw import draw
    L = load(fixtures / "clean")
    assert next(c for c in L.model.connectors if c.id == "X-IP").pin_count == 25
    d = tmp_path / "p"; shutil.copytree(fixtures / "clean", d)
    draw(d, harnesses=["X-IP"], no_render=True)
    x = yaml.safe_load((d / "out" / "X-IP.yml").read_text(encoding="utf-8"))["connectors"]["X-IP"]
    assert len(x["pins"]) == 25 and x["pinlabels"].count("spare") == 24
    j = yaml.safe_load(next((d / "out").glob("IF-*INTERCOM-BOX*.yml")).read_text(encoding="utf-8"))["connectors"]
    box = next(v for v in j.values() if "Intercom box" in str(v.get("type")))
    assert len(box["pins"]) == 15 and box["pinlabels"].count("spare") == 12


def test_sim_infer_finds_sources_by_name(fixtures, tmp_path):
    """--infer on a readable sheet: batteries and DC/DC converters by name (never the battery relay); a battery's voltage
    from its name when the wires give none."""
    from schemagen.sim import api
    L = load(fixtures / "clean")
    L.cfg.sim = {**L.cfg.sim, "infer": True}
    op = api.operating_point(L.model, L.cfg)
    names = {c.id: c.name for c in L.model.components}
    assert op.converged and not op.missing
    assert {names[s["component"]] for s in op.sources} == {"Battery", "Starter battery", "DC-DC converter"}
    wb = Workbook(); ws = wb.active; ws.title = "Wires"
    ws.append(rd.HEAD)
    ws.append(["L1", "lamp feed", "24 V battery", "positive terminal", "Work lamp", "pin 1", None, 1.0, 22, 2.0, 6.0])
    ws.append(["L2", "lamp return", "Work lamp", "pin 2", "24 V battery", "negative terminal", "GND", 1.0, 22, 2.0, 6.0])
    ws.append(["L3", "charger", "DC/DC converter", "output", "Work lamp", "pin 3", "14 V", 1.0, 22, 2.0, 6.0])
    wb.save(tmp_path / "w.xlsx")
    (tmp_path / "schemagen.yml").write_text("source: {path: w.xlsx}\nsim: {infer: true}\n", encoding="utf-8")
    L2 = load(tmp_path)
    op = api.operating_point(L2.model, L2.cfg)
    notes = {a.what: a.note for a in op.assumptions if "inferred" in a.note}
    assert any("battery" in k and "24 V" in v for k, v in notes.items()), notes
    assert any("dcdc" in k for k in notes), notes


def test_can_terminations_t_pieces_and_jumpers(fixtures):
    """An M12 terminator after three T-pieces counts for the bus the chain carries; a termination jumper between two
    pins of one device counts as the other termination."""
    L = load(fixtures / "clean")
    ctx = Ctx(L.model, L.cfg)
    can2 = [b for b in ctx.can_buses if any(lab_.startswith("CAN2") for lab_ in (L.model.conductors[i].name for i in b.conductors))]
    assert len(can2) == 2 and all(len(b.terminators) == 2 for b in can2)
    assert {c for b in can2 for c in b.inferred_terms} == {"MOTOR-CONTROLLER", "CAN2-TERMINATOR-M12"}
    assert not [i for i in run_rules(L.model, L.cfg) if i.rule.startswith("can-") and i.severity == "error"]


def test_direction_regressions_from_the_real_sheet(fixtures):
    """No direction finding on: terminator leads written from the resistor, the E-STOP enable chain, loop wires,
    a return through a harness connector to a point not named as a ground, a feed from a bus to an untyped relay."""
    from schemagen.core import direction
    L = load(fixtures / "clean")
    ctx = Ctx(L.model, L.cfg)
    names = ("CAN1 H end", "CAN1 L end", "CAN2 H terminator", "CAN2 L terminator", "Enable chain", "Safety loop", "Safety loop return",
             "Cabin heater return", "Fuel shutoff relay feed")
    idx = {i for i, c in enumerate(L.model.conductors) if c.name in names}
    assert len(idx) >= 12
    assert not idx & {f.index for f in direction.analyse(ctx)}
