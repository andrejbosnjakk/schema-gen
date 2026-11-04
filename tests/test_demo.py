import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from schemagen import palette, table
from schemagen.cards import Cards
from schemagen.cli import draw
from schemagen.config import load_config
from schemagen.drawing import build, build_set
from schemagen.net import Net
from schemagen.project import Project

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


@pytest.fixture(scope="module")
def pr():
    return Project(load_config(DEMO))


@pytest.fixture(scope="module")
def drawing(pr):
    cfg = pr.cfg
    return build(pr, Net(pr), Cards(cfg.cards, cfg.cardmap), "X-BH")


@pytest.fixture
def demo_copy(tmp_path):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("out"))
    return d


def by_label(pr, label):
    return next(w for w in pr.wires if w["label"] == label)


def rows(path):
    with open(path, encoding="utf-8") as fh: return list(csv.DictReader(fh))


def test_roles(pr):
    assert pr.role("SP-ECU-C ECU supply splice (cabin)") == "splice"
    assert pr.role("X-BH bulkhead D-SUB 9") == "harness"
    assert pr.role("GNDB ground bus") == "bus"
    assert pr.role("CB-ECU 5 A") == "breaker"
    assert pr.role("ECU engine control unit") == "device"


def test_colours_never_orange(pr):
    # orange is the usual HV colour; 24 V must be yellow
    assert all(w["color"] != "OG" for w in pr.wires)
    assert by_label(pr, "T01")["color"] == "YE"
    assert by_label(pr, "L05")["color"] == "RD"
    assert by_label(pr, "L11")["color"] == "BK"
    assert by_label(pr, "M01")["color"] == "VT"
    assert by_label(pr, "M04")["color"] == "BU"
    assert (by_label(pr, "N01")["color"], by_label(pr, "N03")["color"]) == ("GN", "GNWH")


def test_palette(pr):
    p = {k: (c, h, s) for k, c, h, s in palette.entries(pr.cfg)}
    assert p["24 V"] == ("YE", "#ffff00", "") and p["CAN_L"] == ("GNWH", "#00ff00", "#ffffff")


def test_net_crosses_splices_and_harness_but_not_breakers(pr):
    net = Net(pr)
    assert net.ends(by_label(pr, "L05")) == ["CB-ECU LOAD", "ECU J1 1"]
    assert {w["label"] for w, _ in net.next_hop(by_label(pr, "L04"), 1)} == {"L10"}  # other side of CB-ECU


def test_reach_walks_through_splices(pr):
    net = Net(pr)
    got = {(t[0].split()[0], t[2], path) for t, path in net.reach(by_label(pr, "L05"), 1)}  # L05 end 1 = cabin splice
    assert got == {("CB-ECU", "", ("L05", "L04")), ("X-BH", "2", ("L05", "L06"))}


def test_drawing_layout(drawing):
    doc = drawing.doc
    x = doc["connectors"]["X-BH"]
    assert x["pins"] == list(range(1, 10)) and x["pinlabels"][8] == "spare"
    assert doc["connectors"]["SP-ECU-C"]["style"] == "simple"
    pairs = [c for c in doc["cables"].values() if c.get("type") == "twisted pair"]
    assert len(pairs) == 2 and all(c["colors"] == ["GN", "GNWH"] and c["shield"] for c in pairs)


def test_bundles_per_far_item_with_gauge_in_label(drawing):
    cabs = drawing.doc["cables"]
    dsp = next(c for c in cabs.values() if "M01 · 22" in c["wirelabels"])
    assert dsp["wirelabels"] == ["M01 · 22", "M04 · 22"] and dsp["gauge"] == "22 AWG"


def test_short_notes_and_footnotes(drawing):
    note = drawing.doc["connectors"]["SP-ECU-C"]["notes"]
    assert note.startswith("L05 → L04 (CB-ECU LOAD), L06 (X-BH 2) [")
    assert "net ends" not in note
    fn = {l: t for n, l, t in drawing.footnotes}
    assert fn["L05"].endswith("net ends: CB-ECU LOAD, ECU J1 1")


def test_card_pin_names(drawing):
    # ECU from the card's ```yaml schemagen block, OTS from a markdown table via cardmap
    ecu, ots = drawing.doc["connectors"]["ECU"], drawing.doc["connectors"]["OTS"]
    # pin 1 (VBAT) reaches the harness through the engine-side splice, so it is not on the ECU box
    assert dict(zip(ecu["pins"], ecu["pinlabels"])) == {2: "GND", 3: "CAN_H", 4: "CAN_L"}
    assert dict(zip(ots["pins"], ots["pinlabels"])) == {1: "Supply 5 V", 2: "Temperature out"}


def test_checks(drawing):
    assert drawing.checks == ["PIN TBD T02 at GEN (Field TBD)"]


def test_split(pr):
    cfg = pr.cfg
    net, cards = Net(pr), Cards(cfg.cards, cfg.cardmap)
    full, parts = build_set(pr, net, cards, "X-BH", mode="side")
    assert [d.harness for d in parts] == ["X-BH_near", "X-BH_far"]
    assert len(full.ends) == 16 and sorted(len(d.ends) for d in parts) == [8, 8]
    assert {t[0]["_cable"] for t in full.ends} == {c for d in parts for c in d.doc["cables"]}  # cut list names drawn bundles
    full, parts = build_set(pr, net, cards, "X-BH", mode="function")
    assert [d.harness for d in parts] == ["X-BH_power", "X-BH_can", "X-BH_signal"]
    assert build_set(pr, net, cards, "X-BH", mode="auto")[1][0].harness == "X-BH"  # 9 far items < threshold 20


def test_continuity_sheet(demo_copy):
    draw(demo_copy, no_render=True)
    r = rows(demo_copy / "out" / "X-BH_continuity.csv")
    pr = Project(load_config(demo_copy))
    assert not any(x["to"].startswith("SP-") or x["from"].startswith("SP-") for x in r)  # splices are not test points
    tied = [x for x in r if x["remarks"] == "tied pin (same splice)"]
    assert len(tied) == 2  # pin 1-2 on each half, listed once
    e2e = [x for x in r if x["test"].startswith("end to end")]
    assert len(e2e) == 8 and "parallel with pin 2" in e2e[0]["remarks"]
    iso = {x["from terminal"]: x["to terminal"] for x in r if x["test"].startswith("isolation")}
    assert "except pin 2" in iso["pin 1"] and "except" not in iso["pin 3"]
    assert pr.wires  # project still loads after draw


def test_table_roundtrip_csv_and_json(pr, demo_copy, tmp_path):
    for ext in ("csv", "json"):
        out = tmp_path / f"wires.{ext}"
        table.export(pr, out)
        cfg = yaml.safe_load((demo_copy / "schemagen.yml").read_text(encoding="utf-8"))
        cfg["source"] = {"path": str(out)}
        (demo_copy / "schemagen.yml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
        p2 = Project(load_config(demo_copy))
        assert [(w["label"], w["p1"], w["p2p"], w["color"]) for w in p2.wires] == [(w["label"], w["p1"], w["p2p"], w["color"]) for w in pr.wires]


def test_table_xlsx_with_column_mapping(pr, demo_copy, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Wires"
    ws.append(["My wire list"])  # title row above the header
    cols = {"id": "Wire ID", "p1": "From", "p1c": "From conn", "p1p": "From pin", "p2": "To", "p2c": "To conn", "p2p": "To pin"}
    ws.append([cols.get(f, f) for f in table.FIELDS])
    for w in pr.wires: ws.append([w.get(f, "") for f in table.FIELDS])
    ws.append(["", "", "", "Section header row"])  # skipped: no id
    wb.save(tmp_path / "wires.xlsx")
    cfg = yaml.safe_load((demo_copy / "schemagen.yml").read_text(encoding="utf-8"))
    cfg["source"] = {"path": str(tmp_path / "wires.xlsx"), "sheet": "Wires", "header_row": 2, "columns": cols}
    (demo_copy / "schemagen.yml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    assert len(Project(load_config(demo_copy)).wires) == len(pr.wires)


def test_wireviz_is_never_imported():
    # WireViz is GPL-3.0: schemagen runs it as a separate program and must not import it
    code = ("import sys, schemagen.cli, schemagen.cli.commands, schemagen.outputs, schemagen.drawing, schemagen.renderers.interface, "
            "schemagen.renderers.wireviz, schemagen.app.server, schemagen.sim.report; print('wireviz' in sys.modules)")
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip() == "False"


@pytest.mark.skipif(shutil.which("dot") is None or shutil.which("wireviz") is None, reason="Graphviz/WireViz not installed")
def test_render(demo_copy):
    draw(demo_copy)
    out = demo_copy / "out"
    for f in ("X-BH.svg", "X-BH.png", "X-BH.html", "X-BH.bom.tsv", "index.html"):
        assert (out / f).stat().st_size > 0
    assert "Continues at" in (out / "X-BH.html").read_text(encoding="utf-8")
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "T02" in page and json.dumps("X-BH") in page
