"""M4: the app's API (the browser flows are in frontend/e2e)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from schemagen.app.server import create_app

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"


@pytest.fixture
def client(tmp_path):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("out"))
    git = lambda *a: subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)  # noqa: E731
    git("init", "-q"); git("add", "."); git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "demo")
    return TestClient(create_app(d)), d


def test_index_has_every_object_type(client):
    c, _ = client
    ix = c.get("/api/index").json()
    assert len(ix["conductors"]) == 23 and ix["nets"] and ix["components"] and ix["connectors"] and ix["lists"]["gauge"]
    assert {i["rule"] for i in ix["issues"]} == {"pin-tbd", "open-item", "open-status"}
    h = c.get("/api/health").json()
    assert h["ready"] is True and "graphviz" in h


@pytest.mark.parametrize("typ,oid,title", [("conductor", "PWR-ECU-A", "L04"), ("pin", "ECU/J1/1", "ECU engine control unit J1 1"), ("component", "CB-ECU", "CB-ECU"),
                                           ("connector", "X-BH", "X-BH"), ("part", "demo battery 12 Ah", "part")])
def test_object_pages(client, typ, oid, title):
    c, _ = client
    o = c.get("/api/object", params=dict(type=typ, id=oid)).json()
    assert title in o["title"] and "links" in o and "issues" in o and "history" in o


def test_object_history_from_git(client):
    c, _ = client
    assert c.get("/api/object", params=dict(type="conductor", id="PWR-ECU-A")).json()["history"][0]["subject"] == "demo"


def test_edit_undo_and_diff(client):
    c, d = client
    r = c.post("/api/edit", json=dict(edits=[dict(id="PWR-ECU-A", field="awg", value="18")]))
    assert r.status_code == 200 and len(list((d / "changes").glob("*.json"))) == 1
    assert next(x for x in r.json()["index"]["conductors"] if x["id"] == "PWR-ECU-A")["gauge"] == "18"
    cs = json.loads(next((d / "changes").glob("*.json")).read_text(encoding="utf-8"))
    assert cs["ops"] == [dict(op="set", id="PWR-ECU-A", field="awg", old="20", new="18", row={})]
    t = c.get("/api/diff", params=dict(rev="HEAD")).json()["text"]
    assert "~ conductor PWR-ECU-A gauge: '20' -> '18'" in t
    assert c.post("/api/undo").json()["removed"].endswith("app-edit.json")
    assert c.post("/api/edit", json=dict(edits=[dict(id="PWR-ECU-A", field="nope", value="1")])).status_code == 400
    assert c.post("/api/edit", json=dict(edits=[dict(id="PWR-ECU-A", field="awg", value="20")])).status_code == 400  # nothing changed


def test_fix_direction_preview_and_apply(client):
    c, d = client
    p = d / "wirelist" / "ss01_demo.py"
    p.write_text(p.read_text(encoding="utf-8").replace('row("GND-BAT-1", "BAT battery 14 V", "−", "", "GNDB ground bus", "Stud", ""',
                                       'row("GND-BAT-1", "GNDB ground bus", "Stud", "", "BAT battery 14 V", "−", ""'), encoding="utf-8")
    c2 = TestClient(create_app(d))
    assert [f["label"] for f in c2.get("/api/fix/direction").json()["flips"]] == ["L03"]
    assert c2.post("/api/fix/direction").json()["applied"] == 1
    assert not [i for i in c2.get("/api/index").json()["issues"] if i["rule"] == "direction"]


def test_sim_graph_and_drawings(client):
    c, _ = client
    r = c.post("/api/sim/run", json=dict(scenario="normal.yml")).json()
    assert r["ok"] and r["tree"][0]["id"] == "BB1" and r["tree"][0]["feeds"]
    assert c.post("/api/sim/faults", json={}).json()["rows"]
    g = c.get("/api/graph").json()
    assert {"BB1", "X-BH", "ECU"} <= {n["id"] for n in g["nodes"]} and g["edges"]
    assert c.get("/api/drawings").json() == []
    assert c.post("/api/drawings/render", json=dict(no_render=True)).json() == []  # YAML only: no SVGs
    assert c.get("/api/drawing/../../etc/passwd").status_code == 404


def test_frontend_is_bundled_without_cdn():
    static = ROOT / "schemagen" / "app" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    assert "/assets/" in html and "http://" not in html and "https://" not in html
    js = "".join(p.read_text(errors="ignore", encoding="utf-8") for p in (static / "assets").glob("*.js"))
    assert "googleapis" not in js and "unpkg.com" not in js and "jsdelivr" not in js
