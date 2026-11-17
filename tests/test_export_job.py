"""The export is a background job (docs/api.md, Export): it answers at once, shows progress, can be cancelled, and survives a failed drawing. Run on
the generated fictional large project (tools/make_large_fixture.py; about 185 parts, 530 wires)."""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import run_export
from fastapi.testclient import TestClient

from schemagen.app.server import create_app

ROOT = Path(__file__).resolve().parents[1]
LARGE = ROOT / "tests" / "fixtures" / "large"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """The light variant of the large project: the same parts and wires, the ground bus on splices (the full bus takes the drawing engine minutes)."""
    d = tmp_path_factory.mktemp("large") / "p"
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_large_fixture.py"), str(d), "--light"], check=True)
    return TestClient(create_app(str(d))), d


def test_fixture_is_current(tmp_path):
    """The committed fixture is what the generator writes (it is deterministic), and has the size the tests and measurements rely on."""
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_large_fixture.py"), str(tmp_path)], check=True)
    for f in ("schemagen.yml", "cards/BATX_card.md", "wirelist/ss01_large.py"):
        assert (tmp_path / f).read_bytes() == (LARGE / f).read_bytes().replace(b"\r\n", b"\n"), f  # a Windows checkout may convert line ends
    from collections import Counter

    from schemagen.app.server import State
    st = State(LARGE)
    ends = Counter(e for x in st.m.conductors for e in (x.from_.device, x.to.device))
    assert len(st.m.conductors) >= 450 and len(st.m.components) >= 150 and ends["GNDB ground bus"] >= 150 and sum(v >= 30 for v in ends.values()) >= 6


@pytest.mark.slow  # about 100 s: 180 drawings, each written twice (its own PDF and the book); CI runs it
def test_large_export_completes_with_progress(client):
    c, d = client
    t = time.time()
    r = c.post("/api/export", json=dict(kind="drawings"))
    assert r.status_code == 202 and time.time() - t < 2  # started, not finished
    jid, seen = r.json()["job"], []
    while True:
        j = c.get(f"/api/export/{jid}").json()
        seen.append((j["n"], j["N"]))
        if j["state"] != "running": break
        time.sleep(0.05)
    assert j["state"] == "done" and j["failed"] == [], j
    assert j["N"] >= 150 and j["n"] == j["N"] and len({n for n, _ in seen}) > 3  # progress moved
    files = j["files"]
    out = d / "out"
    assert "wiring-diagrams.pdf" in files and len([f for f in files if f.startswith("drawings/")]) >= 100
    assert all((out / f).is_file() for f in files)
    assert c.post("/api/export", json=dict(kind="nonsense")).status_code == 400
    assert c.get("/api/export/nope").status_code == 404


def test_one_export_at_a_time_and_cancel_between_drawings(client):
    c, d = client
    shutil.rmtree(d / "out", ignore_errors=True)
    jid = c.post("/api/export", json=dict(kind="drawings")).json()["job"]
    assert c.post("/api/export", json=dict(kind="drawings")).json()["error"]["code"] == "busy"
    time.sleep(0.5)
    t = time.time()
    assert c.post(f"/api/export/{jid}/cancel").status_code == 200
    while c.get(f"/api/export/{jid}").json()["state"] == "running": time.sleep(0.02)
    assert time.time() - t < 2  # stopped within 2 s
    assert c.get(f"/api/export/{jid}").json()["state"] == "cancelled"
    assert not (d / "out").exists() or not list((d / "out").iterdir())  # nothing half written
    assert run_export(c, kind="pinout").status_code == 200  # and the next export can start


def test_cancel_inside_one_long_drawing(tmp_path):
    """The full project's ground bus (151 wires) takes the engine minutes to draw: a cancel still stops it within 2 s."""
    d = tmp_path / "p"
    shutil.copytree(LARGE, d)
    c = TestClient(create_app(str(d)))
    jid = c.post("/api/export", json=dict(kind="diagram", scope="component:GNDB")).json()["job"]
    time.sleep(1.5)  # well inside the layout
    assert c.get(f"/api/export/{jid}").json()["state"] == "running"
    t = time.time()
    c.post(f"/api/export/{jid}/cancel")
    while c.get(f"/api/export/{jid}").json()["state"] == "running": time.sleep(0.02)
    assert time.time() - t < 2 and c.get(f"/api/export/{jid}").json()["state"] == "cancelled"
    assert not (d / "out").exists() or not list((d / "out").rglob("*.pdf"))


def test_viewer_refuses_a_scope_too_big_to_show(client):
    c, d = client
    r = c.get("/api/diagram", params=dict(scope="system"))
    assert r.status_code == 400 and "Save it as PDF" in r.json()["error"]["message"]
    assert c.get("/api/diagram", params=dict(scope="component:EC1")).status_code == 200


def test_failed_drawings_are_listed_and_the_rest_is_written(client, monkeypatch):
    from schemagen.app import diagrams
    c, d = client
    real = diagrams.draw

    def draw(st, scope, *a, **k):  # only EC4 can be drawn: every other drawing fails (and fast)
        if scope != "component:EC4": raise KeyError("pin")
        return real(st, scope, *a, **k)
    monkeypatch.setattr(diagrams, "draw", draw)
    j = run_export(c, kind="drawings").json()
    assert "EC4" not in j["failed"] and "EC3" in j["failed"] and len(j["failed"]) >= 150
    assert "wiring-diagrams.pdf" in j["files"] and "drawings/component-EC4.pdf" in j["files"] and len(j["files"]) == 2
