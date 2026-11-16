"""The wiring drawing (app/drawing.py): complete and correct on the example, since people will wire from it."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from schemagen.app.server import create_app

AIRCRAFT = Path(__file__).resolve().parents[1] / "examples" / "aircraft"


@pytest.fixture(scope="module")
def ws():
    c = TestClient(create_app(str(AIRCRAFT)))
    return c, c.get("/api/workspace").json()


def runs(d):
    return [r["left"] + r["right"] for g in d["groups"] for r in g["rows"]]


def test_every_wire_end_is_drawn_once_per_component(ws):
    c, w = ws
    seen: dict[str, int] = {}
    for n in w["components"]:
        if n["id"].startswith("SRC-"): continue
        d = c.get(f"/api/drawing/{n['id']}").json()
        assert not d["cut"]
        first = [s[0]["wire"] for r in (g["rows"] for g in d["groups"]) for row in r for s in ([row["left"]] if row["left"] else []) + ([row["right"]] if row["right"] else [])]
        for wid in set(first): seen[wid] = seen.get(wid, 0) + 1
        for run in runs(d):  # a run ends on a real terminal, never on a splice or a connector pin with a wire behind it
            assert run[-1]["role"] not in ("splice",), (n["id"], run[-1])
    by_id = {x["id"]: x for x in w["conductors"]}
    assert set(seen) == set(by_id)  # every wire leaves some drawn pin
    for wid, k in seen.items():  # once under each end that is a drawn component (splices have no drawing of their own)
        assert 1 <= k <= 2, (wid, k)


def test_run_goes_through_the_firewall_connector(ws):
    c, _ = ws
    d = c.get("/api/drawing/BATTERY-MANAGEMENT-SYSTEM").json()
    run = next(r["right"] for g in d["groups"] for r in g["rows"] if r["right"][0]["label"] == "W089")
    assert [s["role"] for s in run] == ["harness", "breaker"] and "motor side 9" in run[0]["at"] and "BMS" in run[1]["at"]
    x = c.get("/api/drawing/X-FW").json()
    row = next(r for r in x["groups"][0]["rows"] if r["pin"] == "9")
    assert len(x["sides"]) == 2 and {row["left"][-1]["comp"], row["right"][-1]["comp"]} == {"CB-BMS", "BATTERY-MANAGEMENT-SYSTEM"}


def test_connection_between_two_components(ws):
    c, _ = ws
    d = c.get("/api/drawing/CB-XPDR", params={"to": "TRANSPONDER"}).json()
    assert d["to"]["id"] == "TRANSPONDER" and [[s["label"] for s in r] for r in runs(d)] == [["W058"]]
    assert c.get("/api/drawing/NOPE").status_code == 404
    g = c.get("/api/drawing/BB-GROUND-BUS", params={"to": "X-WR"}).json()  # through a connector: the run goes on to the light behind it
    assert {r[0]["label"] for r in runs(g)} == {"W033", "W043", "W049"} and all(r[0]["comp"] == "X-WR" and r[-1]["role"] == "device" for r in runs(g))
