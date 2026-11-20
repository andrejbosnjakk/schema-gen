"""The verifier's overview mode (schemagen/verify/overview.py) against the engine's overview PDF: no differences on the real output, and every seeded fault
(a wire end moved, two labels swapped, a dot dropped or added at a crossing, a gauge or colour changed, a label dropped, a wire on the wrong page) is found."""
import copy
import random
import re
from pathlib import Path

import pytest

from schemagen.app.server import State
from schemagen.drawing.engine import export, meta
from schemagen.drawing.overview import draw
from schemagen.verify import expect as X
from schemagen.verify.overview import check_overview

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = {"demo": ROOT / "examples" / "demo"}      # the fictional demo has every class: voltages, ground, CAN, signal
HARD = ("missing", "extra", "ends", "gauge", "colour", "label", "net", "junction", "title", "unread")
KINDS = ("end", "swap", "dot", "cross_dot", "gauge", "colour", "label_drop", "page_extra", "page_missing")
PER_KIND = {"demo": 13}          # 9 kinds x 13 = 117 seeded faults


@pytest.fixture(scope="module", params=sorted(PROJECTS))
def world(request, tmp_path_factory):
    d = PROJECTS[request.param]
    st = State(d)
    g = draw(st, meta(st.cfg))
    ex = X.read(d)
    cls = {c.id: (c.can or c.kind) for c in st.m.conductors}
    return request.param, g, ex, cls, tmp_path_factory.mktemp("ov")


def hard(ex, g, tmp, name):
    p = tmp / f"{name}.pdf"
    export(g, p)
    return [f for f in check_overview(ex, p, ex.source)[1] if f["kind"] in HARD]


def label_texts(sh, w):
    return [t for t in sh["texts"] if t.get("role") == "wire" and t["model"] == w["model"]]


def pages_with_wires(g):
    return [sh for sh in g["sheets"] if sh["wires"]]


def mutate(g, kind, rng, cls):
    """Applies one seeded fault to the geometry g (in place); False when this geometry has no place for it."""
    sh = rng.choice(pages_with_wires(g))
    ws = sh["wires"]
    if kind == "end":
        w = rng.choice(ws)
        v = rng.choice([x for x in ws if x is not w])
        P = v["points"][rng.choice((0, -1))]
        pts = w["points"]
        if P == pts[-1] or P == pts[0]: return False
        q = pts[-2]
        w["points"] = pts[:-1] + ([[q[0], P[1]]] if q[0] != P[0] and q[1] != P[1] else []) + [list(P)]
    elif kind == "swap":
        one = [w for w in ws if len(label_texts(sh, w)) == 1]
        if len(one) < 2: return False
        a, b = rng.sample(one, 2)
        ta, tb = label_texts(sh, a)[0], label_texts(sh, b)[0]
        if ta["s"] == tb["s"]: return False
        ta["s"], tb["s"] = tb["s"], ta["s"]
    elif kind in ("dot", "cross_dot"):
        circles = [(s, p) for s in sh["symbols"] for p in s["prims"] if p["kind"] == "circle" and p.get("fill") == "black"]
        if kind == "dot":
            if not circles: return False
            s, p = rng.choice(circles)
            if sum(q["kind"] == "circle" and (q["cx"], q["cy"]) == (p["cx"], p["cy"]) for q in s["prims"]) > 1: return False     # two dots on one spot: no visible change
            s["prims"].remove(p)
        else:
            hs = [(w, a, b) for w in ws for a, b in zip(w["points"], w["points"][1:]) if a[1] == b[1]]
            vs = [(w, a, b) for w in ws for a, b in zip(w["points"], w["points"][1:]) if a[0] == b[0]]
            xs = [(h[0]["id"], v[1][0], h[1][1]) for h in hs for v in vs if v[0] is not h[0] and min(h[1][0], h[2][0]) < v[1][0] < max(h[1][0], h[2][0])
                  and min(v[1][1], v[2][1]) < h[1][1] < max(v[1][1], v[2][1])]
            if not xs: return False
            _, x, y = rng.choice(xs)
            rng.choice(sh["symbols"])["prims"].append(dict(kind="circle", stroke="normal", fill="black", cx=x, cy=y, r=0.9))
    elif kind == "gauge":
        w = rng.choice([w for w in ws if len(label_texts(sh, w)) == 1] or [None])
        if w is None: return False
        t = label_texts(sh, w)[0]
        t["s"] = re.sub(r" (\d+) ", lambda m: f" {int(m.group(1)) + 2} ", t["s"], count=1)
    elif kind == "colour":
        w = rng.choice(ws)
        w["hex"] = "#0000ff" if w["hex"].lower() not in ("#0000ff", "#00f") else "#ff0000"
    elif kind == "label_drop":
        w = rng.choice(ws)
        sh["texts"] = [t for t in sh["texts"] if t not in label_texts(sh, w)]
    elif kind == "page_extra":
        far = [(s, w) for s in g["sheets"] for w in s["wires"] if s is g["sheets"][-1] and cls[w["id"]] == "signal"]
        if not far: return False
        _, w = rng.choice(far)
        target = g["sheets"][0]
        target["wires"].append(copy.deepcopy(w))
        target["texts"] += copy.deepcopy(label_texts(g["sheets"][-1], w))
    elif kind == "page_missing":
        w = rng.choice([w for w in g["sheets"][0]["wires"] if cls[w["id"]] != "signal"] or [None])
        if w is None: return False
        g["sheets"][0]["wires"].remove(w)
        g["sheets"][0]["texts"] = [t for t in g["sheets"][0]["texts"] if t not in label_texts(g["sheets"][0], w)]
    return True


def test_the_real_output_has_no_differences(world):
    name, g, ex, cls, tmp = world
    assert hard(ex, g, tmp, "plain") == []


def test_every_seeded_fault_is_found(world):
    name, g, ex, cls, tmp = world
    rng = random.Random(20261120)
    tried = caught = 0
    missed = []
    for kind in KINDS:
        done = 0
        for attempt in range(40):
            m = copy.deepcopy(g)
            if not mutate(m, kind, rng, cls): continue
            tried += 1; done += 1
            if hard(ex, m, tmp, f"{kind}{attempt}"): caught += 1
            else: missed.append((kind, attempt))
            if done == PER_KIND[name]: break
        assert done >= 1, f"no place for a {kind} fault in {name}"
    assert tried >= 50 and missed == [], (tried, caught, missed)
