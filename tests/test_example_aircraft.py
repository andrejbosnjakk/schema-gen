"""1.0 example project (examples/aircraft): a fictional electric aircraft whose readable sheet has exactly three
deliberate mistakes (examples/aircraft/README.md), all three shown by `check` (the app's Issues) as well as by Simulate."""
import shutil
from collections import Counter
from pathlib import Path

import pytest
import yaml
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
        ("no-power-source", ["component:BB-CABIN-BUS"]),                       # 3: no feed into the cabin bus
    ]
    titles = {i.rule: i.title for i in issues if i.rule == "no-power-source"}
    assert titles == {"no-power-source": "Cabin bus has no power source"}
    msg = next(i.message for i in issues if i.rule == "no-power-source")
    assert all(x in msg for x in ("Cabin fan", "Cabin light", "USB charger"))
    thin = next(i for i in issues if i.objects[0] == "conductor:W045")
    big = next(i for i in issues if i.objects[0] == "conductor:W058")
    assert thin.title == "W045 is too thin for the 10 A LANDING LT breaker" and "FAA AC 43.13-1B" in thin.message
    assert big.title == "The 15 A XPDR breaker is too big for wire W058 (20 AWG, max 7.5 A)" and "FAA AC 43.13-1B" in big.message


def test_unpowered_cabin_bus():
    """Mistake 3: no source or feed reaches the cabin bus, so its three loads see no voltage (`check` reports it too:
    the no-power-source rule)."""
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


@pytest.mark.parametrize("name", ["aircraft", "demo"])
def test_wireviz_connections_use_listed_pins(tmp_path, name):
    """Every [designator, pin] a drawing connects exists in that connector's pin list and has no stray whitespace (WireViz: "X:pin not found")."""
    d = tmp_path / name
    shutil.copytree(AIRCRAFT.parent / name, d, ignore=shutil.ignore_patterns("out"))
    assert main(["draw", str(d), "--all", "--no-render"]) == 0
    for f in (d / "out").glob("*.yml"):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "connectors" not in doc: continue
        for row in doc.get("connections", []):
            for part in row:
                for des, pins in (part.items() if isinstance(part, dict) else []):
                    if des not in doc["connectors"]: continue  # a cable
                    have = doc["connectors"][des].get("pins")
                    for p in pins:
                        assert (have is None or p in have) and str(p) == str(p).strip(), f"{f.name}: {des}:{p!r} not a clean listed pin of {have}"


def test_sheet_is_reproducible(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_sheet", AIRCRAFT / "make_sheet.py")
    ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)
    ms.write(tmp_path / "w.xlsx")
    import zipfile
    parts = lambda f: {i.filename: z.read(i) for z in [zipfile.ZipFile(f)] for i in z.infolist()}  # noqa: E731
    # the unpacked parts, not the file bytes: the compressed stream depends on the zlib build (zlib or zlib-ng)
    assert parts(tmp_path / "w.xlsx") == parts(AIRCRAFT / "wires.xlsx")
