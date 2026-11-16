"""Fixes from the product review of the 1.0 app (decisions D96-D104): a user's own sheet, import, export, cards, session."""
import json
import os
import shutil
import sys
from pathlib import Path

from openpyxl import load_workbook

from schemagen.app import userdata
from schemagen.renderers import wireviz
from test_api import AIRCRAFT, ac, empty, err, home  # noqa: F401  (fixtures)


def test_tests_use_a_temporary_user_folder(home):  # noqa: F811
    assert userdata.home() == Path(os.environ["SCHEMAGEN_HOME"])


def test_conftest_points_the_user_folder_at_a_temp_dir():
    assert "schemagen-home" in os.environ["SCHEMAGEN_HOME"] and userdata.home() == Path(os.environ["SCHEMAGEN_HOME"])


def test_imported_sheet_simulates_like_the_example(empty):  # noqa: F811
    """No cards, no schemagen.yml extras: switches, relays and contactors without part data count as closed."""
    w = empty.post("/api/import", files={"file": ("wires.xlsx", (AIRCRAFT / "wires.xlsx").read_bytes())}).json()
    kinds = {n["id"]: n["kind"] for n in w["components"]}
    assert kinds["MAIN-BATTERY"] == "battery" and kinds["BACKUP-BATTERY"] == "battery" and kinds["DC-DC-CONVERTER"] == "dcdc"
    assert kinds["BATTERY-MANAGEMENT-SYSTEM"] == "device" and kinds["CB-DCDC"] == "breaker"
    assert {n["id"]: n["rank"] for n in w["components"]}["MAIN-BATTERY"] == 0
    assert any(i["rule"] == "no-power-source" and i["title"] == "Cabin bus has no power source" and i["objects"] == ["component:BB-CABIN-BUS"]
               for i in w["issues"])
    o = empty.post("/api/simulate", json={}).json()
    v = {b["id"]: b for b in o["buses"]}
    assert v["BB-MAIN-BUS"]["powered"] and v["BB-ESSENTIAL-BUS"]["powered"] and v["BB-MAIN-BUS"]["voltage_V"] > 13
    assert not v["BB-CABIN-BUS"]["powered"] and o["ok"] is False
    assert (o["summary"]["problems"], o["summary"]["trips"], o["summary"]["unpowered"]) == (3, 0, 1)
    assert any("Battery contactor" in a and "taken as closed" in a for a in o["assumptions"])
    assert any("Switch 'MASTER'" in a and "taken as closed" in a for a in o["assumptions"])


def test_import_not_a_wire_sheet(empty, home):  # noqa: F811
    r = empty.post("/api/import", files={"file": ("notes.csv", b"Name,Price,Colour\nbolt,3,red\nnut,1,blue\n")})
    err(r, "import-failed", 422)
    e = r.json()["error"]
    assert e["retry"] is False
    assert e["message"] == "notes.csv has no wires schemagen can read. A wire sheet needs at least the columns Label, From and To."
    assert not (home / "projects" / "notes").exists()
    s = empty.get("/api/session").json()
    assert s["recent"] == [] and s["project"] is None
    e = empty.post("/api/import", files={"file": ("x.xlsx", b"not a workbook")}).json()["error"]
    assert e["message"] == "x.xlsx could not be read. Save it as .xlsx or .csv and try again." and ".." not in e["message"]


def test_health_reports_drawing_tools(empty, monkeypatch):  # noqa: F811
    h = empty.get("/api/health").json()
    assert h["drawings"].keys() == {"available", "message"} and h["graphviz"].keys() >= {"found", "version", "message"}
    monkeypatch.setattr(wireviz, "wireviz_cmd", lambda: None)
    h = empty.get("/api/health").json()
    assert h["drawings"] == {"available": False, "message": wireviz.DRAWINGS_MISSING}
    assert "pip" not in h["drawings"]["message"] and h["drawings"]["message"].startswith("Harness drawings need Graphviz and WireViz")
    monkeypatch.setattr(wireviz, "wireviz_cmd", lambda: ["x"])
    monkeypatch.setattr(wireviz, "find_dot", lambda: "dot")
    assert empty.get("/api/health").json()["drawings"] == {"available": True, "message": ""}


def test_export_drawings_without_wireviz_writes_nothing(ac, monkeypatch):  # noqa: F811
    c, d = ac
    monkeypatch.setattr(wireviz, "find_dot", lambda: "dot")
    monkeypatch.setattr(wireviz, "wireviz_cmd", lambda: None)
    r = c.post("/api/export", json={"kind": "drawings"})
    err(r, "graphviz-missing")
    assert r.json()["error"]["message"] == wireviz.DRAWINGS_MISSING and r.json()["error"]["retry"] is False
    assert not (d / "out").exists() or not list((d / "out").iterdir())


def test_failed_render_leaves_no_files(ac, monkeypatch, tmp_path):  # noqa: F811
    c, d = ac
    fake = tmp_path / "fake.py"
    fake.write_text("import sys\nsys.stderr.write('ValueError: boom\\n'); sys.exit(1)\n", encoding="utf-8")
    monkeypatch.setattr(wireviz, "find_dot", lambda: sys.executable)
    monkeypatch.setattr(wireviz, "wireviz_cmd", lambda: [sys.executable, str(fake)])
    r = c.post("/api/export", json={"kind": "drawings"})
    assert r.status_code >= 400 and r.json()["error"]["code"] == "render-failed"
    assert not (d / "out").exists() or not list((d / "out").iterdir())


def test_checklist_export(ac):  # noqa: F811
    c, d = ac
    r = c.post("/api/export", json={"kind": "pinout"}).json()
    assert sorted(r["files"]) == ["checklist.html", "checklist.xlsx"]
    h = (d / "out" / "checklist.html").read_text(encoding="utf-8")
    assert "<title>Wiring checklist</title>" in h and "<h1>Wiring checklist</h1>" in h and "aircraft" in h
    assert "@page{size:A4 portrait" in h and "table-header-group" in h and "break-after:avoid" in h
    assert h.count('<th class="tick">Connected</th>') == h.count("<table>") and h.count('<th class="tick">Continuity</th>') == h.count("<table>")
    assert "http://" not in h and "https://" not in h and "<link" not in h and "<script" not in h
    ws = load_workbook(d / "out" / "checklist.xlsx").worksheets[0]
    heads = [x for x in ws.iter_rows(values_only=True) if x[0] == "connector / half"]
    assert heads and all("Connected" in x and "Continuity" in x for x in heads)


def test_card_rows_have_display_text(ac):  # noqa: F811
    c, _ = ac
    k = c.get("/api/card/component/CB-DCDC").json()
    rows = [p for con in k["connectors"] for p in con["pins"]]
    assert rows and all({"pin", "pin_name", "wire", "wire_label", "wire_name", "other", "gauge"} <= p.keys() for p in rows)
    assert all("(" not in p["other"] for p in rows)
    line = next(p for p in rows if p["pin"] == "LINE")  # a text terminal: its text is the pin
    assert line["wire_name"] and line["pin_name"] == ""
    kb = [p for con in c.get("/api/card/component/K-BATTERY-CONTACTOR").json()["connectors"] for p in con["pins"]]
    assert any(p["other"] == "Breaker 'BATTERY' 30 A LINE" for p in kb)  # no code in brackets


def test_rating_edit_renames_in_the_same_change_set(ac):  # noqa: F811
    c, d = ac
    w = c.post("/api/component/CB-XPDR", json={"rating_A": 3}).json()
    assert next(n for n in w["components"] if n["id"] == "CB-XPDR")["name"] == "Breaker 'XPDR' 3 A"
    files = sorted((d / "changes").glob("*.json"))
    assert len(files) == 1
    ops = json.loads(files[0].read_text(encoding="utf-8"))["ops"]
    assert {(o["field"], o["old"], o["new"]) for o in ops} == {("rating_A", 15.0, 3.0), ("name", "Breaker 'XPDR' 15 A", "Breaker 'XPDR' 3 A")}
    assert c.get("/api/card/component/CB-XPDR").json()["rating_A"] == 3
    c.post("/api/component/CB-XPDR", json={"name": "Transponder breaker"})  # a name without the rating is left alone
    c.post("/api/component/CB-XPDR", json={"rating_A": 5})
    assert next(n for n in c.get("/api/workspace").json()["components"] if n["id"] == "CB-XPDR")["name"] == "Transponder breaker"


def test_close_session_and_recent(empty, home, tmp_path):  # noqa: F811
    empty.post("/api/import", files={"file": ("a.xlsx", (AIRCRAFT / "wires.xlsx").read_bytes())})
    assert empty.get("/api/session").json()["project"]["name"] == "a"
    assert empty.post("/api/close").json() == {"ok": True}
    s = empty.get("/api/session").json()
    assert s["project"] is None and [r["name"] for r in s["recent"]] == ["a"]
    err(empty.get("/api/workspace"), "no-project")
    folder = Path(s["recent"][0]["path"])
    shutil.copytree(folder, tmp_path / "gone")
    empty.post("/api/open", json={"path": str(tmp_path / "gone")})
    shutil.rmtree(tmp_path / "gone")
    assert [r["name"] for r in empty.get("/api/session").json()["recent"]] == ["a"]  # the vanished folder is not listed
    assert empty.post("/api/recent/remove", json={"path": str(folder)}).json() == {"ok": True}
    assert empty.get("/api/session").json()["recent"] == [] and folder.is_dir()
    err(empty.post("/api/recent/remove", json={}), "bad-request")
