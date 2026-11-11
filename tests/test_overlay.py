"""The simulate overlay counts root causes, not symptoms (docs/api.md, decisions D75)."""
from test_api import ac, home  # noqa: F401  (fixtures)


def test_overlay_counts_root_causes_not_symptoms(ac):  # noqa: F811
    c, _ = ac
    o = c.post("/api/simulate", json={}).json()
    s = o["summary"]
    assert (s["problems"], s["trips"], s["unpowered"]) == (3, 0, 1) and s["text"] == "3 problems, 0 trips, 1 unpowered bus"
    g = {frozenset(x["objects"]) for x in s["groups"]}
    assert g == {frozenset({"conductor:W045", "component:CB-LANDING-LT"}), frozenset({"conductor:W058", "component:CB-XPDR"}),
                 frozenset({"component:BB-CABIN-BUS", "component:CABIN-FAN", "component:CABIN-LIGHT", "component:USB-CHARGER"})}
    assert all(x["status"] == "error" and x["title"] for x in s["groups"])
    assert o["items"]["component:CABIN-FAN"] == {"status": "error", "reason": "no supply: Cabin bus has no source"}


def test_overlay_does_not_flag_wires_sized_for_their_breaker(ac):  # noqa: F811
    c, _ = ac
    it = c.post("/api/simulate", json={}).json()["items"]
    assert not [k for k in it if k.startswith("conductor:W0") and int(k[11:]) <= 22]
    assert not [k for k, v in it.items() if v["status"] == "warn"]


def test_overlay_group_goes_with_its_source(ac):  # noqa: F811
    c, _ = ac
    c.post("/api/sources", json={"attach": "BB-CABIN-BUS", "type": "battery", "nominal_V": 14})
    s = c.post("/api/simulate", json={}).json()["summary"]
    assert s["problems"] == 2 and not any("component:BB-CABIN-BUS" in x["objects"] for x in s["groups"]) and s["text"] == "2 problems, 0 trips"
