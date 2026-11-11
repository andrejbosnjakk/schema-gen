"""The 1.0 app API (docs/api.md): start screen, session, workspace, cards, edits, simulate overlay, sources, export, errors."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from schemagen.app.server import create_app

ROOT = Path(__file__).resolve().parents[1]
AIRCRAFT = ROOT / "examples" / "aircraft"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHEMAGEN_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def empty(home):
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def ac(home, tmp_path):
    d = tmp_path / "aircraft"
    shutil.copytree(AIRCRAFT, d, ignore=shutil.ignore_patterns("out", "__pycache__"))
    return TestClient(create_app(d), raise_server_exceptions=False), d


def err(r, code, status=None):
    assert status is None or r.status_code == status, r.text
    assert r.status_code >= 400, r.text
    e = r.json()["error"]
    assert e["code"] == code and e["message"] and isinstance(e["retry"], bool) and "Traceback" not in r.text


# ---------------------------------------------------------------- session
def test_no_project_start(empty, home):
    assert empty.get("/api/health").json()["graphviz"].keys() >= {"found", "version", "message"}
    s = empty.get("/api/session").json()
    assert s["project"] is None and s["recent"] == [] and s["tour_done"] is False and s["theme"] == "light"
    err(empty.get("/api/workspace"), "no-project")
    assert empty.post("/api/settings", json={"tour_done": True, "theme": "dark"}).json() == {"ok": True}
    assert (home / "settings.json").is_file()
    s = empty.get("/api/session").json()
    assert s["tour_done"] is True and s["theme"] == "dark"


def test_open_example_copies_once(empty, home, monkeypatch):
    monkeypatch.setenv("SCHEMAGEN_EXAMPLE", str(AIRCRAFT))
    w = empty.post("/api/open", json={"example": True}).json()
    copy = home / "projects" / "Example aircraft"
    assert (copy / "schemagen.yml").is_file() and w["project"]["root"] == str(copy)
    (copy / "marker.txt").write_text("x", encoding="utf-8")
    empty.post("/api/open", json={"example": True})
    assert (copy / "marker.txt").is_file()  # not copied over again
    s = empty.get("/api/session").json()
    assert s["project"]["name"] == "Example aircraft" and s["recent"][0]["path"] == str(copy)


def test_import_sheet_and_bad_files(empty):
    r = empty.post("/api/import", files={"file": ("My sheet.xlsx", (AIRCRAFT / "wires.xlsx").read_bytes())})
    assert r.status_code == 200 and r.json()["project"]["name"] == "My sheet" and len(r.json()["conductors"]) == 121
    err(empty.post("/api/import", files={"file": ("x.txt", b"hi")}), "bad-request")
    err(empty.post("/api/import", files={"file": ("x.xlsx", b"not a workbook")}), "import-failed")
    err(empty.post("/api/import", files={"file": ("x.xlsx", b"")}), "import-failed")


# ---------------------------------------------------------------- bad requests never crash
@pytest.mark.parametrize("path,body", [
    ("/api/open", {"path": "C:/definitely/not/here"}), ("/api/open", {}), ("/api/open", {"x": 1}),
    ("/api/settings", {"theme": "pink"}), ("/api/settings", {"nope": 1}), ("/api/settings", {"tour_done": "yes"}),
])
def test_bad_session_requests(empty, path, body):
    r = empty.post(path, json=body)
    assert 400 <= r.status_code < 500 and r.json()["error"]["message"]


def test_bad_bodies_and_ids(ac):
    c, _ = ac
    err(c.get("/api/card/component/NOPE"), "not-found")
    err(c.get("/api/card/wire/NOPE"), "not-found")
    err(c.post("/api/component/NOPE", json={"name": "x"}), "not-found")
    err(c.post("/api/wire/NOPE", json={"label": "x"}), "not-found")
    err(c.post("/api/wire/W045", json={"bogus": 1}), "bad-request")
    err(c.post("/api/wire/W045", json={"current": "lots"}), "bad-request")
    err(c.post("/api/wire/W045", content=b"{not json", headers={"content-type": "application/json"}), "bad-request")
    err(c.post("/api/wire/W045", json=[1, 2]), "bad-request")
    err(c.post("/api/component/CB-XPDR", json={"rating_A": -3}), "bad-request")
    err(c.post("/api/positions", json={"positions": [1]}), "bad-request")
    err(c.post("/api/positions", json={"positions": {"CB-XPDR": ["a", 1]}}), "bad-request")
    err(c.post("/api/sources", json={"attach": "NOPE", "nominal_V": 14}), "not-found")
    err(c.post("/api/sources", json={"attach": "BB-CABIN-BUS", "type": "fusion", "nominal_V": 14}), "bad-request")
    err(c.post("/api/sources", json={"attach": "BB-CABIN-BUS"}), "bad-request")
    err(c.delete("/api/sources/SRC-9"), "not-found")
    err(c.post("/api/export", json={"kind": "pdf"}), "bad-request")
    err(c.post("/api/reveal", json={"path": "C:/Windows"}), "bad-request")
    assert c.get("/api/workspace").status_code == 200  # still alive


def test_unexpected_error_is_internal_and_logged(ac, home, monkeypatch):
    c, _ = ac
    from schemagen.app import workspace

    def boom(*a, **k): raise RuntimeError("secret cause")
    monkeypatch.setattr(workspace, "workspace", boom)
    r = c.get("/api/workspace")
    err(r, "internal", 500)
    assert "secret cause" not in r.text
    assert "secret cause" in (home / "logs" / "schemagen.log").read_text(encoding="utf-8")


# ---------------------------------------------------------------- workspace, cards, edits
def test_workspace_shape(ac):
    c, d = ac
    w = c.get("/api/workspace").json()
    assert {"project", "components", "edges", "conductors", "issues", "zones", "positions", "sources", "palette"} <= w.keys()
    assert len(w["conductors"]) == 121 and all(n["id"] and n["rank"] in range(5) for n in w["components"])
    wire = next(x for x in w["conductors"] if x["id"] == "W045")
    assert wire["gauge"].startswith("22") and wire["from"] and wire["to"] and wire["hex"].startswith("#")
    assert any("×" in e["label"] for e in w["edges"]) and all(e["wires"] for e in w["edges"])
    assert all(i["title"] for i in w["issues"])
    assert c.post("/api/positions", json={"positions": {"CB-XPDR": [10, 20.5]}}).json() == {"ok": True}
    assert (d / "layout.json").is_file() and c.get("/api/workspace").json()["positions"]["CB-XPDR"] == [10, 20.5]


def test_cards(ac):
    c, _ = ac
    k = c.get("/api/card/component/CB-XPDR").json()
    assert k["id"] == "CB-XPDR" and k["rating_A"] == 15 and k["connectors"]
    w = c.get("/api/card/wire/W045").json()
    assert w["id"] == "W045" and w["issues"] and w["from"] and w["to"]


def test_edits_are_change_sets(ac):
    c, d = ac
    before = (d / "wires.xlsx").read_bytes()
    w = c.post("/api/wire/W045", json={"gauge": "18", "notes": "fixed in the app"}).json()
    assert (d / "wires.xlsx").read_bytes() == before and (d / "changes").is_dir()
    assert next(x for x in w["conductors"] if x["id"] == "W045")["gauge"].startswith("18")
    assert not [i for i in w["issues"] if i["rule"] == "gauge-protection" and "conductor:W045" in i["objects"]]
    w = c.post("/api/component/CB-XPDR", json={"rating_A": 5}).json()
    assert not [i for i in w["issues"] if i["rule"] == "gauge-protection" and "protective:CB-XPDR" in i["objects"]]
    assert c.get("/api/card/component/CB-XPDR").json()["rating_A"] == 5


# ---------------------------------------------------------------- simulate and sources
def test_overlay_tells_the_three_mistakes_apart(ac):
    c, _ = ac
    o = c.post("/api/simulate", json={}).json()
    it = o["items"]
    assert it["conductor:W045"]["status"] == "error" and "too small" in it["conductor:W045"]["reason"]
    assert "10 A" in it["conductor:W045"]["reason"]
    assert it["component:CB-XPDR"]["status"] == "error" and "too big" in it["component:CB-XPDR"]["reason"]
    assert it["component:BB-CABIN-BUS"]["status"] == "error" and "no source" in it["component:BB-CABIN-BUS"]["reason"]
    assert o["ok"] is False and o["summary"]["unpowered"] >= 1 and o["summary"]["text"]
    cabin = next(b for b in o["buses"] if b["id"] == "BB-CABIN-BUS")
    assert cabin["powered"] is False and cabin["voltage_V"] < 0.5


def test_source_powers_the_cabin_bus(ac):
    c, d = ac
    w = c.post("/api/sources", json={"attach": "BB-CABIN-BUS", "type": "battery", "nominal_V": 14, "name": "Test battery"}).json()
    assert len(w["sources"]) == 1 and w["sources"][0]["attach"] == "BB-CABIN-BUS" and w["sources"][0]["nominal_V"] == 14
    sid = w["sources"][0]["id"]
    assert any(n["id"] == sid and n["rank"] == 0 for n in w["components"])
    o = c.post("/api/simulate", json={}).json()
    assert "component:BB-CABIN-BUS" not in o["items"] and o["summary"]["unpowered"] == 0
    assert next(b for b in o["buses"] if b["id"] == "BB-CABIN-BUS")["powered"] is True
    assert len(TestClient(create_app(d)).get("/api/workspace").json()["sources"]) == 1  # it lives in the project
    w = c.delete(f"/api/sources/{sid}").json()
    assert w["sources"] == [] and c.post("/api/simulate", json={}).json()["summary"]["unpowered"] >= 1


# ---------------------------------------------------------------- export
def test_export_files(ac):
    c, d = ac
    for kind, name in (("pinout", "pinout.xlsx"), ("wirelist", "wirelist.xlsx")):
        r = c.post("/api/export", json={"kind": kind}).json()
        assert name in r["files"] and (d / "out" / name).is_file() and r["folder"] == str(d / "out")
    r = c.post("/api/export", json={"kind": "faults"}).json()
    assert r["files"] and all((d / "out" / f).is_file() for f in r["files"])


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz not installed")
def test_export_drawings(ac):
    c, _ = ac
    r = c.post("/api/export", json={"kind": "drawings"})
    assert r.status_code == 200 and any(f.endswith((".svg", ".png")) for f in r.json()["files"])


def test_export_drawings_without_graphviz(ac, monkeypatch):
    c, _ = ac
    from schemagen.renderers import wireviz
    monkeypatch.setattr(wireviz, "find_dot", lambda: None)
    err(c.post("/api/export", json={"kind": "drawings"}), "graphviz-missing")


# ---------------------------------------------------------------- speed
def test_500_wire_readable_import_is_fast(empty, tmp_path):
    out = tmp_path / "syn"
    subprocess.run([sys.executable, "-m", "schemagen", "synth", "--readable", "--wires", "500", "--seed", "3", "-o", str(out)],
                   check=True, capture_output=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
    sheet = next(out.rglob("*.xlsx"))
    t = time.perf_counter()
    r = empty.post("/api/import", files={"file": ("big.xlsx", sheet.read_bytes())})
    dt = time.perf_counter() - t
    assert r.status_code == 200 and len(r.json()["conductors"]) >= 450 and dt < 3, (dt, r.text[:200])
