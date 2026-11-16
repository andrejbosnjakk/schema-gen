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
    titles = {x["title"] for x in s["groups"]}  # W045 is listed at 6 A, more than 22 AWG may carry (wire too thin); W058 at 1.5 A (breaker too big)
    assert {"W045 is too thin for the 10 A LANDING LT breaker", "The 15 A XPDR breaker is too big for wire W058 (20 AWG, max 7.5 A)",
            "Cabin bus has no power source"} == titles
    assert o["items"]["component:CABIN-FAN"] == {"status": "error", "reason": "Cabin fan has no supply: Cabin bus has no source"}


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


def test_no_guessed_heavy_wire_threshold():
    from schemagen.core import tables
    assert "heavy_margin" not in tables.table("sim")  # no standard behind it: wires without a protector are never "far heavier"


def test_overlay_and_rule_say_the_same_thing(ac):  # noqa: F811
    c, _ = ac
    o = c.post("/api/simulate", json={}).json()
    w = c.get("/api/workspace").json()
    issue = next(i for i in w["issues"] if "conductor:W045" in i["objects"])
    group = next(g for g in o["summary"]["groups"] if "conductor:W045" in g["objects"])
    assert issue["title"] == group["title"] == "W045 is too thin for the 10 A LANDING LT breaker"
    # the framing follows the sheet's current, not the simulated one: a listed 10 A on the 20 AWG transponder wire makes it too thin
    w = c.post("/api/wire/W058", json={"current": 10}).json()
    assert next(i for i in w["issues"] if "conductor:W058" in i["objects"])["title"] == "W058 is too thin for the 15 A XPDR breaker"
    o = c.post("/api/simulate", json={}).json()
    assert next(g for g in o["summary"]["groups"] if "conductor:W058" in g["objects"])["title"] == "W058 is too thin for the 15 A XPDR breaker"
