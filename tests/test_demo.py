import csv
import shutil
from pathlib import Path

import pytest

from schemagen.cards import Cards
from schemagen.cli import draw
from schemagen.config import load_config
from schemagen.drawing import build
from schemagen.net import Net
from schemagen.project import Project

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


@pytest.fixture(scope="module")
def pr():
    return Project(load_config(DEMO))


@pytest.fixture(scope="module")
def drawing(pr):
    cfg = pr.cfg
    return build(pr, Net(pr), Cards(cfg.cards, cfg.cardmap), "X-FW")


def by_label(pr, label):
    return next(w for w in pr.wires if w["label"] == label)


def test_roles(pr):
    assert pr.role("SP-ECU-C ECU supply splice (cabin)") == "splice"
    assert pr.role("X-FW firewall D-SUB 9") == "harness"
    assert pr.role("GNDB ground bus") == "bus"
    assert pr.role("CB-ECU 5 A") == "breaker"
    assert pr.role("ECU engine control unit") == "device"


def test_colours_never_orange(pr):
    # orange is the HV colour in the aircraft; 24 V must be yellow
    assert all(w["color"] != "OG" for w in pr.wires)
    assert by_label(pr, "T01")["color"] == "YE"
    assert by_label(pr, "L05")["color"] == "RD"
    assert by_label(pr, "L11")["color"] == "BK"
    assert by_label(pr, "M01")["color"] == "VT"
    assert by_label(pr, "M04")["color"] == "BU"
    assert (by_label(pr, "N01")["color"], by_label(pr, "N03")["color"]) == ("GN", "GNWH")


def test_net_crosses_splices_and_harness_but_not_breakers(pr):
    net = Net(pr)
    ends = net.ends(by_label(pr, "L05"))
    assert ends == ["CB-ECU LOAD", "ECU J1 1"]  # stops at the breaker, reaches the ECU through both splices
    nxt = {w["label"] for w, _ in net.next_hop(by_label(pr, "L04"), 1)}
    assert nxt == {"L10"}  # other side of CB-ECU


def test_drawing_layout(drawing):
    doc = drawing.doc
    x = doc["connectors"]["X-FW"]
    assert x["pins"] == list(range(1, 10)) and x["pinlabels"][8] == "spare"
    assert doc["connectors"]["SP-ECU-C"]["style"] == "simple"
    assert "continues" in doc["connectors"]["SP-ECU-C"]["notes"]
    pairs = [c for c in doc["cables"].values() if c.get("type") == "twisted pair"]
    assert len(pairs) == 2 and all(c["colors"] == ["GN", "GNWH"] and c["shield"] for c in pairs)


def test_card_pin_names(drawing):
    ecu = drawing.doc["connectors"]["ECU"]
    # pin 1 (VBAT) reaches the harness through the engine-side splice, so it is not on the ECU box
    assert dict(zip(ecu["pins"], ecu["pinlabels"])) == {2: "GND", 3: "CAN_H", 4: "CAN_L"}


def test_checks(drawing):
    assert drawing.checks == ["PIN TBD T02 at GEN (Field TBD)"]


def test_continuity_sheet_excludes_spliced_pins(tmp_path):
    cfg_dir = tmp_path / "demo"
    shutil.copytree(DEMO, cfg_dir, ignore=shutil.ignore_patterns("out"))
    draw(cfg_dir, no_render=True)
    rows = list(csv.DictReader(open(cfg_dir / "out" / "X-FW_continuity.csv", encoding="utf-8")))
    iso = {r["from pin"]: r["to pin"] for r in rows if r["test"].startswith("isolation")}
    assert "except pin 2" in iso["pin 1"] and "except" not in iso["pin 3"]
    e2e = [r for r in rows if r["test"].startswith("end to end")]
    assert len(e2e) == 8


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz not installed")
def test_render(tmp_path):
    cfg_dir = tmp_path / "demo"
    shutil.copytree(DEMO, cfg_dir, ignore=shutil.ignore_patterns("out"))
    draw(cfg_dir)
    out = cfg_dir / "out"
    for f in ("X-FW.svg", "X-FW.png", "X-FW.html", "X-FW.bom.tsv", "index.html"):
        assert (out / f).stat().st_size > 0
    assert "T02" in (out / "index.html").read_text(encoding="utf-8")
