"""1.0 example project (examples/aircraft): a fictional electric aircraft whose readable sheet has exactly three
deliberate mistakes (examples/aircraft/README.md)."""
import shutil
from collections import Counter
from pathlib import Path

import pytest
from openpyxl import load_workbook

from schemagen.cli import main
from schemagen.core.load import load
from schemagen.core.rules import run_rules
from schemagen.importers import readable as rd
from schemagen.sim import api

AIRCRAFT = Path(__file__).resolve().parents[1] / "examples" / "aircraft"


@pytest.fixture(scope="module")
def loaded():
    return load(AIRCRAFT)


@pytest.fixture(scope="module")
def issues(loaded):
    return run_rules(loaded.model, loaded.cfg)


def test_size_and_kinds(loaded):
    m = loaded.model
    assert 110 <= len(m.conductors) <= 130
    kinds = Counter(c.kind for c in m.components)
    assert kinds["harness"] == 2 and kinds["bus"] == 4 and kinds["breaker"] >= 15
    assert {"switch", "relay", "fuse", "splice", "device"} <= set(kinds)
    assert not loaded.warnings


def test_cells_parse(loaded, issues):
    ws = load_workbook(AIRCRAFT / "wires.xlsx").worksheets[0]
    cells = [r[c] for r in ws.iter_rows(min_row=2, values_only=True) if r[2] is not None for c in (3, 5)]
    assert sum(rd.parse_cp(x) is not None for x in cells) / len(cells) >= 0.99
    assert not [i for i in issues if i.rule == "readable-cell"]


def test_lv_never_orange(loaded):
    pal = loaded.cfg.colours
    colour = {c.label: pal.get(c.can or c.kind, pal["signal"]) for c in loaded.model.conductors}
    assert {c.label for c in loaded.model.conductors if colour[c.label] == "OG"} == {"W001", "W002"}  # only the 400 V stub
    assert all(colour[c.label] == "RD" for c in loaded.model.conductors if c.kind == "14 V")


def test_exactly_the_deliberate_mistakes(issues):
    bad = [(i.rule, i.objects) for i in issues if i.severity in ("error", "warning")]
    assert sorted(bad) == [
        ("gauge-protection", ["conductor:W045", "protective:CB-LANDING-LT"]),  # 1: 22 AWG under a 10 A breaker (6 A landing light)
        ("gauge-protection", ["conductor:W058", "protective:CB-XPDR"]),        # 2: 15 A breaker on a 1.5 A transponder, 20 AWG
    ]


def test_unpowered_cabin_bus():
    """Mistake 3: no source or feed reaches the cabin bus, so its three loads see no voltage. No `check` rule finds
    this yet; the simulation shows it."""
    L = load(AIRCRAFT)
    op = api.operating_point(L.model, L.cfg)
    v = {b["id"]: b["voltage_V"] for b in op.buses}
    assert v["BB-CABIN-BUS"] < 1.0 and v["BB-MAIN-BUS"] > 13 and v["BB-ESSENTIAL-BUS"] > 13
    dark = {x["component"] for x in op.loads if not x["powered"]}
    assert dark == {"CABIN-LIGHT", "USB-CHARGER", "CABIN-FAN"}


def test_draw_without_render(tmp_path):
    d = tmp_path / "aircraft"
    shutil.copytree(AIRCRAFT, d, ignore=shutil.ignore_patterns("out"))
    assert main(["draw", str(d), "--no-render"]) == 0
    assert (d / "out").is_dir()


def test_sheet_is_reproducible(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_sheet", AIRCRAFT / "make_sheet.py")
    ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)
    ms.write(tmp_path / "w.xlsx")
    assert (tmp_path / "w.xlsx").read_bytes() == (AIRCRAFT / "wires.xlsx").read_bytes()
