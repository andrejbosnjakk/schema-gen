"""M4: the app's API (the browser flows are in frontend/e2e)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import run_export
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
    assert {i["rule"] for i in ix["issues"]} == {"pin-tbd", "open-item", "open-status", "no-power-source"}
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


def test_diagram_route_draws_scopes(client):
    c, _ = client
    for scope in ("component:ECU", "connection:CB-ECU~ECU", "selection:ECU,CB-ECU"):
        r = c.get("/api/diagram", params=dict(scope=scope))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["scope"] == scope and d["title"] and d["sheets"] and all(s.startswith("<svg") and "</svg>" in s for s in d["sheets"])
    assert "ECU" in c.get("/api/diagram", params=dict(scope="component:ECU")).json()["sheets"][0]
    for bad in ("component:NOPE", "bogus:x", "component:"):
        r = c.get("/api/diagram", params=dict(scope=bad))
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad-request" and r.json()["error"]["message"].endswith(".")


def _pages(p):
    import re
    return len(re.findall(rb"/Type\s*/Page\b", p.read_bytes()))


def test_export_one_diagram(client):
    c, d = client
    r = run_export(c, kind="diagram", scope="connection:CB-ECU~ECU")
    assert r.status_code == 200, r.text
    assert r.json() == dict(folder=str(d / "out"), files=["drawings/connection-CB-ECU_ECU.pdf"])
    assert _pages(d / "out" / "drawings" / "connection-CB-ECU_ECU.pdf") >= 1
    assert run_export(c, kind="diagram").status_code == 400
    assert run_export(c, kind="diagram", scope="component:NOPE").status_code == 400


def test_export_all_drawings_makes_a_book(client):
    from schemagen.drawing.sheet import symbol_sheet
    c, d = client
    r = run_export(c, kind="drawings")
    assert r.status_code == 200, r.text
    files = r.json()["files"]
    out = d / "out"
    per = [f for f in files if f.startswith("drawings/")]
    assert "wiring-diagrams.pdf" in files and "drawings/component-ECU.pdf" in per and "drawings/component-X-BH.pdf" in per
    assert all((out / f).is_file() for f in files)
    assert _pages(out / "wiring-diagrams.pdf") == len(symbol_sheet()["sheets"]) + 1 + sum(_pages(out / f) for f in per)      # the symbol sheets, one contents page, the drawings


def test_export_all_survives_one_failed_drawing(client, monkeypatch):
    """One drawing that raises is logged and listed in `failed`; every other drawing and the book are still written."""
    from schemagen.app import diagrams
    c, d = client
    real = diagrams.draw

    def draw(st, scope, *a, **k):
        if scope == "component:ECU": raise KeyError("pin:ECU//3")
        return real(st, scope, *a, **k)
    monkeypatch.setattr(diagrams, "draw", draw)
    r = run_export(c, kind="drawings")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["failed"] == ["ECU"] and "wiring-diagrams.pdf" in j["files"] and "drawings/component-X-BH.pdf" in j["files"]
    assert "drawings/component-ECU.pdf" not in j["files"] and (d / "out" / "wiring-diagrams.pdf").is_file()
    monkeypatch.setattr(diagrams, "draw", lambda *a, **k: (_ for _ in ()).throw(KeyError("x")))
    assert run_export(c, kind="drawings").status_code == 400
