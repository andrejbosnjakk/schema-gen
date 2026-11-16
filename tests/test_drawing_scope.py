"""The drawing engine's scene and geometry contract (docs/drawing-model.md): every conductor on a drawn node is drawn once
or flagged, the scene says what the model says, and the geometry round trip catches what a layout drops."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from schemagen import synth
from schemagen.app.server import State
from schemagen.app.workspace import _natural
from schemagen.core.context import Ctx
from schemagen.drawing.geometry import from_json, to_json, validate
from schemagen.drawing.scope import parse, scene
from schemagen.drawing.verify import expected, netlist, roundtrip, scene_netlist

ROOT = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture(scope="module")
def states(tmp_path_factory):
    d = tmp_path_factory.mktemp("synth") / "s"
    synth.main(150, 1, str(d))
    return {"demo": State(ROOT / "demo"), "aircraft": State(ROOT / "aircraft"), "synth": State(d)}


def scopes(st):
    out = [f"component:{c.id}" for c in st.m.components]
    out += [f"harness:{c.id}" for c in st.m.components if c.kind == "harness"]
    a, b = st.m.conductors[0].from_.device, st.m.conductors[0].to.device
    devs = [c.id for c in st.m.components if c.kind not in ("splice", "harness")][:3]
    out += [f"connection:{st.ctx.comp[a].id}~{st.ctx.comp[b].id}", "selection:" + ",".join(devs), "system"]
    out += [f"subsystem:{s}" for s in sorted({c.subsystem for c in st.m.conductors if c.subsystem})[:2]]
    return out


def check(st, sc):
    """The scene invariants; returns the problems."""
    ctx, net, conds = st.ctx, st.ctx.net, st.m.conductors
    bad = []
    anchors = [p["anchor"] for it in sc["items"] for b in it["blocks"] for p in b["pins"]]
    ids = [it["id"] for it in sc["items"]]
    wires, flags = [w["id"] for w in sc["wires"]], [c["id"] for f in sc["flags"] for c in f.get("covers") or [dict(id=f["model"].removeprefix("conductor:"))]]
    for name, xs in (("items", ids), ("anchors", anchors), ("wires", wires), ("flags", flags)):
        if len(xs) != len(set(xs)): bad.append(f"duplicate {name}")
    if set(wires) & set(flags): bad.append(f"wire and flag: {sorted(set(wires) & set(flags))}")
    node_of = {ctx.ref(conds[i].end(e)): net.node(i, e) for i in range(len(conds)) for e in (1, 2)}
    drawn = {node_of[a] for a in anchors if a in node_of}
    touching = {c.id for i, c in enumerate(conds) if net.node(i, 1) in drawn or net.node(i, 2) in drawn}
    shown = set(wires) | set(flags)
    if touching != shown: bad.append(f"not drawn or flagged: {sorted(touching - shown)}, extra: {sorted(shown - touching)}")
    have = set(anchors)
    bad += [f"{w['id']} end not an anchor" for w in sc["wires"] if not {w["a"], w["b"]} <= have]
    bad += [f"{f['id']} not on an anchor" for f in sc["flags"] if f["at"] not in have]
    if scene_netlist(sc) != expected(st, sc): bad.append("scene netlist differs from the model")
    for it in sc["items"]:
        names = [b["id"] for b in it["blocks"]]
        if it["symbol"] != "harness" and names != sorted(names, key=_natural): bad.append(f"{it['id']} connectors out of order")
        for b in it["blocks"]:
            ns = [p["n"] for p in b["pins"]]
            if ns != sorted(ns, key=_natural): bad.append(f"{it['id']} {b['id']} pins out of order")
        if it["partial"]: continue
        got = {(b["id"], p["n"]) for b in it["blocks"] for p in b["pins"]}
        part = ctx.part_of(st.ctx.comp_by_id[it["code"]].raw)
        if it["symbol"] == "harness":
            con = next(x for x in st.m.connectors if x.id == it["code"])
            want = {str(k) for k in range(1, (con.pin_count or 0) + 1)}
            if any(not want <= {p["n"] for p in b["pins"]} for b in it["blocks"]): bad.append(f"{it['id']} misses spare pins")
        elif part:
            for cd in part.connectors:
                if not any({(n, p.n) for p in cd.pins} <= got for n in names): bad.append(f"{it['id']} misses pins of {cd.id}")
    return bad


@pytest.mark.parametrize("project", ["demo", "aircraft", "synth"])
def test_scope_sweep(states, project):
    st = states[project]
    problems = {s: p for s in scopes(st) if (p := check(st, scene(st, s)))}
    assert not problems, problems


def test_spares_and_halves(states):
    sc = scene(states["demo"], "harness:X-BH")
    (x,) = [it for it in sc["items"] if it["code"] == "X-BH"]
    assert [b["side"] for b in x["blocks"]] == ["near", "far"] and not x["partial"]
    assert all([p["n"] for p in b["pins"]] == [str(k) for k in range(1, 10)] for b in x["blocks"])
    assert any(p["spare"] for b in x["blocks"] for p in b["pins"])


def test_connection_and_flags(states):
    st = states["aircraft"]
    assert [w["label"] for w in scene(st, "connection:CB-XPDR~TRANSPONDER")["wires"]] == ["W058"]
    g = scene(st, "connection:BB-GROUND-BUS~X-WR")
    assert {"W033", "W043", "W049"} <= {w["label"] for w in g["wires"]}
    assert {it["code"] for it in g["items"] if it["role"] == "far_end"} >= {"LANDING-LIGHT", "NAV-LIGHT-LEFT"}
    t = scene(st, "component:TRANSPONDER")
    gnd = [f for f in t["flags"] if f["at"].startswith("pin:BB-GROUND-BUS/")]
    assert len(gnd) == 1 and gnd[0]["text"].startswith("+ ") and len(gnd[0]["covers"]) >= 4  # the ground bus's other wires: one summary flag (D111)
    assert all(c["target"] and c["at"].startswith("pin:BB-GROUND-BUS/") for c in gnd[0]["covers"])
    assert next(it for it in t["items"] if it["code"] == "TRANSPONDER")["role"] == "in_scope"
    k = next(it for it in scene(st, "component:K-BATTERY-CONTACTOR")["items"] if it["code"] == "K-BATTERY-CONTACTOR")
    assert k["symbol"] == "relay" and k["attrs"]["contacts"][0]["no"].endswith("/87") and k["attrs"]["coil"]


def test_parse():
    assert parse("connection:A ~ B") == {"kind": "connection", "ids": ["A", "B"], "text": "connection:A~B"}
    assert parse("selection:A,B,A")["ids"] == ["A", "B"] and parse("system")["ids"] == []
    for bad in ("nope:X", "component:", "connection:A", "selection:,"):
        with pytest.raises(ValueError): parse(bad)


def test_unknown_ids(states):
    st = states["demo"]
    for s in ("component:NOPE", "harness:ECU", "subsystem:NOPE"):
        with pytest.raises(ValueError): scene(st, s)


def test_deterministic(states):
    st = states["aircraft"]
    m = st.m.model_copy(update={"conductors": list(reversed(st.m.conductors)), "components": list(reversed(st.m.components))})
    other = SimpleNamespace(m=m, ctx=Ctx(m, st.cfg), cfg=st.cfg, issues=st.issues, overlay=None)
    for s in scopes(st):
        a = to_json(scene(st, s))
        assert a == to_json(scene(st, s)) == to_json(scene(other, s)), s


# ---------------------------------------------------------------- geometry
def naive(sc):
    """A deliberately plain layout: every anchor on its own grid point, L-shaped wires, flags along the bottom."""
    pos = {}
    for k, a in enumerate(p["anchor"] for it in sc["items"] for b in it["blocks"] for p in b["pins"]): pos[a] = [5.0 + 5 * (k % 80), 5.0 + 5 * (k // 80)]
    anchor = lambda a: dict(id=a, model=a, x=pos[a][0], y=pos[a][1], side="R")  # noqa: E731
    symbols = [dict(id=it["id"], kind=it["symbol"], model=it["model"], x=0, y=0, w=5, h=5, prims=[dict(kind="rect", stroke="normal", x=0, y=0, w=5, h=5)],
                    anchors=[anchor(p["anchor"]) for b in it["blocks"] for p in b["pins"]])
               for it in sc["items"]]
    wire = lambda w, a, b, pts: dict(id=w["id"], model=w["model"], label=w["label"], gauge=w["gauge"], colour=w["colour"], hex=w["hex"], weight=w["weight"],  # noqa: E731
                                     points=pts, a=a, b=b, pair="", shield="", fault=None)
    wires = [wire(w, w["a"], w["b"], [pos[w["a"]], [pos[w["b"]][0], pos[w["a"]][1]], pos[w["b"]]]) for w in sc["wires"]]
    flags = []
    for k, f in enumerate(sc["flags"]):
        x, y = 5.0 + 5 * (k % 80), 250.0 + 5 * (k // 80)
        flags.append(dict(id=f["id"], model=f["model"], x=x, y=y, w=5, h=5, text=f["text"], target=f["target"], sheet=None, kind="off_sheet", **({"covers": f["covers"]} if "covers" in f else {})))  # noqa: E501
        wires.append(wire(f, f["at"], f["id"], [pos[f["at"]], [x, pos[f["at"]][1]], [x, y]]) | {"id": "stub:" + f["id"]})
    sheet = dict(n=1, of=1, size="A3", w_mm=420.0, h_mm=297.0, grid_mm=5.0, symbols=symbols, wires=wires, texts=[], flags=flags, notes=[], legend=[], title_block={})
    info = dict(title=sc["title"], scope=sc["scope"]["text"], project=sc["project"], revision="", date="", drawn_by="", source="")
    return dict(version=1, drawing=info, sheets=[sheet])


@pytest.mark.parametrize("project", ["demo", "aircraft"])
def test_roundtrip_on_a_plain_layout(states, project):
    st = states[project]
    for s in scopes(st):
        sc = scene(st, s)
        g = naive(sc)
        assert validate(g) == [] and roundtrip(st, sc, g) == [] and netlist(g) == scene_netlist(sc), s
    sc = scene(st, "system")
    g = naive(sc)
    g["sheets"][0]["wires"].pop(0)
    g["sheets"][0]["wires"][0]["gauge"] = "99"
    assert len(roundtrip(st, sc, g)) == 3  # one wire missing, one with a wrong gauge (missing + extra)


def tiny():
    sym = lambda i, x, pin: dict(id=i, kind="block", model=f"component:{i}", x=x - 10, y=20, w=10, h=20,  # noqa: E731
                                 prims=[dict(kind="rect", stroke="normal", x=x - 10, y=20, w=10, h=20)],
                                 anchors=[dict(id=f"pin:{i}/J1/{pin}", model=f"pin:{i}/J1/{pin}", x=x, y=30, side="R")])
    w = lambda i, pts, a, b: dict(id=i, model="conductor:W1", label="W1", gauge="22", colour="WH", hex="#fff", weight="light", points=pts, a=a, b=b,  # noqa: E731
                                  pair="", shield="", fault=None)
    s1 = dict(n=1, of=2, size="A4", w_mm=297.0, h_mm=210.0, grid_mm=5.0, symbols=[sym("A", 50, "1")], notes=[], legend=[], title_block={"title": "t"},
              wires=[w("W1", [[50, 30], [100, 30], [100, 50]], "pin:A/J1/1", "c1")],
              flags=[dict(id="c1", model="conductor:W1", x=95, y=50, w=20, h=5, text="W1 to sheet 2", target="pin:B/J1/2", sheet=2, kind="continuation")],
              texts=[dict(s="A", x=40, y=15, w=5, h=3, size_mm=2.5, align="left", model="component:A", role="name")])
    s2 = dict(n=2, of=2, size="A4", w_mm=297.0, h_mm=210.0, grid_mm=5.0, symbols=[sym("B", 200, "2")], notes=[], legend=[], title_block={}, texts=[],
              wires=[w("W1", [[150, 30], [200, 30]], "c1", "pin:B/J1/2")],
              flags=[dict(id="c1", model="conductor:W1", x=140, y=25, w=10, h=10, text="W1 from sheet 1", target="pin:A/J1/1", sheet=1, kind="continuation")])
    return dict(version=1, drawing=dict(title="t", scope="connection:A~B", project="p", revision="A", date="2026-11-16", drawn_by="", source=""), sheets=[s1, s2])


def test_geometry_contract():
    g = tiny()
    assert validate(g) == [] and from_json(to_json(g)) == g
    assert netlist(g) == {("W1", "pin:A/J1/1", "pin:B/J1/2", "W1", "22", "WH")}  # continued over two sheets, one conductor
    b = copy.deepcopy(g)
    s = b["sheets"][0]
    s["wires"][0]["points"][1] = [101, 31]   # off the grid and diagonal
    s["texts"][0]["size_mm"] = 2.0
    s["wires"].append(dict(s["wires"][0], id="W2", points=[[0, 0], [5, 0]], a="nowhere"))
    s["size"] = "A2"
    msg = " | ".join(validate(b))
    for want in ("off the grid", "not orthogonal", "2.0 mm", "'nowhere'", "not A3 or A4", "end of 2 wires"):
        assert want in msg, (want, msg)
    with pytest.raises(ValueError): from_json(json.dumps({"version": 9, "sheets": []}))
