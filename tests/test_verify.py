"""The drawing verifier (schemagen/verify): it reads only the PDFs and the model, and it catches seeded faults. Fictional data only
(tests/data/drawing_fixture, examples/demo). The mutants are made here, from the engine's geometry, and rendered to PDF; the verifier never sees the engine."""
import copy
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

from schemagen.app.server import State
from schemagen.drawing.engine import draw, meta, stem
from schemagen.drawing.render_pdf import pdf
from schemagen.verify import HARD, check_drawings, check_pdf, expect

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = {"fixture": ROOT / "tests" / "data" / "drawing_fixture", "demo": ROOT / "examples" / "demo"}
PER_KIND = int(os.environ.get("SCHEMAGEN_MUTANTS", "23"))     # 23 per kind x 10 kinds = 230 mutants; set lower for a quick run
KINDS = ["swap_pins", "move_end", "delete_wire", "duplicate_label", "remove_dot", "add_dot_at_crossing", "change_gauge", "change_colour", "wrong_sheet", "drop_table_row"]


# ---------------------------------------------------------------- independence
def test_verifier_imports_nothing_of_the_engine():
    """The verifier must not share code with what it checks: no schemagen.drawing, renderer or app module (a shared bug would pass both)."""
    out = subprocess.run([sys.executable, "-c", "import sys, schemagen.verify, schemagen.verify.check, schemagen.verify.parse, schemagen.verify.legible; "
                          "print([m for m in sys.modules if m.startswith(('schemagen.drawing', 'schemagen.renderers', 'schemagen.app', 'schemagen.exporters'))])"],
                         capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]", out.stdout
    for p in (ROOT / "schemagen" / "verify").glob("*.py"):
        src = p.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+(schemagen|\.\.)\.?(drawing|renderers|app|exporters)\b", src, re.M), p.name
        assert not re.search(r"from \.\.(drawing|renderers|app|exporters)", src), p.name


# ---------------------------------------------------------------- unmutated output
@pytest.fixture(scope="module")
def states():
    return {k: State(v) for k, v in PROJECTS.items()}


@pytest.fixture(scope="module")
def drawings(states, tmp_path_factory):
    """Every component's drawing of both projects: {(project, stem): geometry}, and the folders of their PDFs."""
    out, folders = {}, {}
    for k, st in states.items():
        d = tmp_path_factory.mktemp(k) / "drawings"
        d.mkdir()
        folders[k] = d.parent
        for c in sorted(st.m.components, key=lambda c: c.id):
            if c.kind == "splice": continue
            g = draw(st, f"component:{c.id}", "A3", meta(st.cfg))
            if not any(sh["wires"] or sh["flags"] for sh in g["sheets"]): continue
            out[(k, stem(g["drawing"]["scope"]))] = g
            pdf(g, d / f"{stem(g['drawing']['scope'])}.pdf")
    return out, folders


@pytest.mark.parametrize("name", ["fixture", "demo"])
def test_clean_output_has_no_differences(drawings, name):
    """Correct drawings: no difference to the wire list (connectivity, tables, completeness), the title block hash is the source's, and flags that lead
    nowhere are none. What the engine does not yet say (flags naming no drawing, a revision) is reported as findings of its own."""
    _, folders = drawings
    rep = check_drawings(PROJECTS[name], folders[name])
    assert [f for f in rep["findings"] if f["kind"] in HARD] == []
    assert rep["ok"] and rep["totals"]["drawings"] >= 8 and rep["totals"]["conductor_checks"] > 20
    kinds = set(rep["totals"]["by_kind"])
    assert not kinds - {"flag_no_target", "flag_no_drawing", "flag_no_sheet", "title_revision_missing"} - set(rep["totals"]["legibility"])
    assert rep["source"]["sha256"] and "title_hash_missing" not in kinds
    json.dumps(rep)   # the report is plain JSON


def test_cli_writes_report_and_exit_code(drawings, tmp_path):
    _, folders = drawings
    out = tmp_path / "r.json"
    r = subprocess.run([sys.executable, "-m", "schemagen", "check-drawings", str(PROJECTS["demo"]), str(folders["demo"]), "-o", str(out)],
                       capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["ok"] and "verdict: PDFs agree" in r.stdout


def test_missing_pdf_is_a_book_finding(drawings, tmp_path):
    import shutil
    _, folders = drawings
    d = tmp_path / "drawings"
    shutil.copytree(folders["demo"] / "drawings", d)
    (d / "component-ECU.pdf").unlink()
    rep = check_drawings(PROJECTS["demo"], tmp_path)
    assert not rep["ok"] and any(f["kind"] == "book" and "ECU" in f["msg"] for f in rep["findings"])


def test_a_changed_source_is_caught_by_the_hash(drawings, tmp_path):
    _, folders = drawings
    other = tmp_path / "other.xlsx"
    other.write_bytes(b"not the source")
    rep = check_drawings(PROJECTS["demo"], folders["demo"], source=other)
    assert not rep["ok"] and any(f["kind"] == "title" and "hash" in f["msg"] for f in rep["findings"])


# ---------------------------------------------------------------- seeded faults
def _wired(sh):
    return {x.split("#")[0] for w in sh["wires"] for x in (w["a"], w["b"])}


def _flag_wire(sh, w):
    ids = {f["id"] for f in sh["flags"]}
    return w["a"] in ids or w["b"] in ids


def _label_text(sh, w):
    return next((t for t in sh["texts"] if t["model"] == w["model"] and t["role"] == "wire"), None)


def _crossings(sh):
    out = []
    for i, w in enumerate(sh["wires"]):
        for v in sh["wires"][i + 1:]:
            for a, b in zip(w["points"], w["points"][1:]):
                for c, d in zip(v["points"], v["points"][1:]):
                    for (h1, h2), (v1, v2) in (((a, b), (c, d)), ((c, d), (a, b))):
                        if h1[1] == h2[1] and v1[0] == v2[0] and min(h1[0], h2[0]) < v1[0] < max(h1[0], h2[0]) and min(v1[1], v2[1]) < h1[1] < max(v1[1], v2[1]):
                            out.append((v1[0], h1[1]))
    return out


def targets(kind, g):
    """Every place in geometry g where a fault of this kind can be seeded: a list of (description, function that seeds it in a deep copy)."""
    out = []
    for si, sh in enumerate(g["sheets"]):
        if kind == "swap_pins":
            wired = _wired(sh)
            pins = [(i, t) for i, t in enumerate(sh["texts"]) if t["role"] == "pin" and t["model"] in wired and t["s"] == t["model"].rsplit("/", 1)[-1] and t["s"].isdigit()]
            for (i, a) in pins:
                for (j, b) in pins:
                    if i < j and a["x"] == b["x"] and a["model"].rsplit("/", 1)[0] == b["model"].rsplit("/", 1)[0] and a["s"] != b["s"] and abs(a["y"] - b["y"]) < 30:
                        out.append((f"sheet {si + 1}: pin texts {a['s']} and {b['s']} of {a['model']}", lambda h, si=si, i=i, j=j: _swap(h["sheets"][si]["texts"], i, j)))
        elif kind == "move_end":
            for wi, w in enumerate(sh["wires"]):
                p = w["points"]
                for end in (0, -1):
                    q = p[:3] if end == 0 else p[:-4:-1]
                    anchor = w["a"] if end == 0 else w["b"]
                    if len(p) >= 4 and anchor.startswith("pin:") and "#" not in anchor and q[0][1] == q[1][1] and q[1][0] == q[2][0]:
                        for dy in (5.0, -5.0):
                            out.append((f"sheet {si + 1}: wire {w['label']} end moved {dy} mm", lambda h, si=si, wi=wi, end=end, dy=dy: _move(h["sheets"][si]["wires"][wi], end, dy)))
        elif kind == "delete_wire":
            for wi, w in enumerate(sh["wires"]):
                out.append((f"sheet {si + 1}: wire {w['label']} deleted", lambda h, si=si, wi=wi: _delete(h["sheets"][si], wi)))
        elif kind == "duplicate_label":
            ws = [(wi, w) for wi, w in enumerate(sh["wires"]) if not _flag_wire(sh, w) and _label_text(sh, w)]
            for (i, a) in ws:
                for (j, b) in ws:
                    if i != j and a["label"] != b["label"]: out.append((f"sheet {si + 1}: {b['label']} labelled {a['label']}", lambda h, si=si, i=i, j=j: _dup(h["sheets"][si], i, j)))
        elif kind == "remove_dot":
            for yi, s in enumerate(sh["symbols"]):
                ids = {a["id"] for a in s["anchors"]}
                n = sum(1 for w in sh["wires"] if w["a"] in ids) + sum(1 for w in sh["wires"] if w["b"] in ids)
                if s["kind"] in ("bus", "ground", "splice") and n >= (3 if s["kind"] == "splice" else 2):
                    for pi, pr in enumerate(s["prims"]):
                        if pr["kind"] == "circle" and pr.get("fill") == "black":
                            out.append((f"sheet {si + 1}: dot of {s['id']} removed", lambda h, si=si, pr=pr: _undot(h["sheets"][si], pr["cx"], pr["cy"])))
        elif kind == "add_dot_at_crossing":
            for (x, y) in _crossings(sh):
                out.append((f"sheet {si + 1}: dot at the crossing {x},{y}", lambda h, si=si, x=x, y=y: h["sheets"][si].setdefault("rules", []).append(
                    dict(kind="circle", stroke="normal", fill="black", cx=x, cy=y, r=0.9))))
        elif kind == "change_gauge":
            for wi, w in enumerate(sh["wires"]):
                t = _label_text(sh, w)
                if t and re.search(r" \d+ AWG ", t["s"]): out.append((f"sheet {si + 1}: wire {w['label']} gauge changed", lambda h, si=si, wi=wi: _gauge(h["sheets"][si], wi)))
        elif kind == "change_colour":
            for wi, w in enumerate(sh["wires"]):
                t = _label_text(sh, w)
                if t and w["colour"] and not w.get("fault"):
                    for how in ("text", "drawn"):
                        out.append((f"sheet {si + 1}: wire {w['label']} colour changed ({how})", lambda h, si=si, wi=wi, how=how: _colour(h["sheets"][si], wi, how)))
        elif kind == "wrong_sheet":
            for fi, f in enumerate(sh["flags"]):
                if f["kind"] == "continuation": out.append((f"sheet {si + 1}: flag {f['id']} points at the wrong sheet", lambda h, si=si, fi=fi: _sheet(h, si, fi)))
        elif kind == "drop_table_row":
            drawn = {w["label"] for w in sh["wires"]}
            for t in sh["texts"]:
                if t["model"] == "" and t["role"] == "pin" and t["s"] in drawn and t["y"] > 150: out.append((f"sheet {si + 1}: table row {t['s']} dropped", lambda h, si=si, t=t: _drop(h["sheets"][si], t)))
    return out


def _undot(sh, cx, cy):
    """Takes every filled dot at that point away (the engine draws one per wire that meets there)."""
    for s in sh["symbols"]: s["prims"] = [p for p in s["prims"] if not (p["kind"] == "circle" and p.get("fill") == "black" and (p["cx"], p["cy"]) == (cx, cy))]


def _swap(texts, i, j):
    texts[i]["s"], texts[j]["s"] = texts[j]["s"], texts[i]["s"]


def _move(w, end, dy):
    pts = w["points"]
    ix = [0, 1] if end == 0 else [len(pts) - 1, len(pts) - 2]
    for k in ix: pts[k] = [pts[k][0], pts[k][1] + dy]


def _delete(sh, wi):
    w = sh["wires"].pop(wi)
    sh["texts"] = [t for t in sh["texts"] if not (t["model"] == w["model"] and t["role"] == "wire")]


def _dup(sh, i, j):
    a, b = sh["wires"][i], sh["wires"][j]
    _label_text(sh, b)["s"] = _label_text(sh, a)["s"]


def _gauge(sh, wi):
    t = _label_text(sh, sh["wires"][wi])
    t["s"] = re.sub(r" (\d+) AWG ", lambda m: f" {'22' if m.group(1) != '22' else '20'} AWG ", t["s"])


def _colour(sh, wi, how):
    w = sh["wires"][wi]
    if how == "drawn": w["hex"] = "#0066ff" if w["colour"][:2] != "BU" else "#ff0000"
    else:
        t = _label_text(sh, w)
        t["s"] = t["s"][:-len(w["colour"])] + ("RD" if w["colour"][:2] != "RD" else "BU")


def _sheet(g, si, fi):
    f = g["sheets"][si]["flags"][fi]
    n = len(g["sheets"])
    f["sheet"] = next((k for k in range(1, n + 1) if k not in (f["sheet"], si + 1)), n + 1)


def _drop(sh, t):
    sh["texts"] = [x for x in sh["texts"] if not (x["model"] == "" and abs(x["y"] - t["y"]) < 0.01 and x["y"] > 150)]


@pytest.fixture(scope="module")
def expected(states):
    return {k: expect.read(PROJECTS[k]) for k in PROJECTS}


def test_clean_drawings_are_clean_one_by_one(drawings, expected):
    """The baseline the mutants are compared with: not one hard finding on any unmutated drawing."""
    gs, folders = drawings
    for (proj, name), _ in sorted(gs.items()):
        d = check_pdf(folders[proj] / "drawings" / f"{name}.pdf", expected[proj])
        assert [f for f in d.findings if f["kind"] in HARD] == [], name


def test_seeded_faults_are_all_caught(drawings, expected, tmp_path):
    """>= 200 faults of ten kinds, each rendered to a PDF and read back: every one must produce a hard finding (the unmutated drawings produce none)."""
    gs, folders = drawings
    rng = random.Random(1712)
    keys = sorted(gs)
    total, missed, per = 0, [], {}
    for kind in KINDS:
        pool = [(k, desc, fn) for k in keys for desc, fn in targets(kind, gs[k])]
        assert pool, f"no place for {kind} in the fixtures"
        picks = []
        by_drawing: dict[tuple[str, str], list] = {}
        for k, desc, fn in pool: by_drawing.setdefault(k, []).append((k, desc, fn))
        for v in by_drawing.values(): rng.shuffle(v)
        order = sorted(by_drawing)
        rng.shuffle(order)
        i = 0
        while len(picks) < min(PER_KIND, len(pool)):   # round robin over the drawings, so one drawing does not supply them all
            k = order[i % len(order)]
            if by_drawing[k]: picks.append(by_drawing[k].pop())
            i += 1
        caught = 0
        for n, (k, desc, fn) in enumerate(picks):
            g = copy.deepcopy(gs[k])
            fn(g)
            p = tmp_path / f"{kind}-{n}.pdf"
            pdf(g, p)
            d = check_pdf(p, expected[k[0]])
            hard = [f for f in d.findings if f["kind"] in HARD]
            if hard: caught += 1
            else: missed.append(f"{kind} {k}: {desc}")
        per[kind] = (len(picks), caught)
        total += len(picks)
    print("mutants per kind (made, caught):", per)
    assert total >= min(200, PER_KIND * len(KINDS)) and not missed, "\n".join(missed)
