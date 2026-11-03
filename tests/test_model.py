"""M1: typed, lossless core model."""
import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from schemagen import synth
from schemagen.core.load import load
from schemagen.core.model import json_schemas
from schemagen.core.net import Net
from schemagen.exporters import json_model
from schemagen.exporters import table as table_out
from schemagen.importers.records import ModelError

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
GOLDEN = ROOT / "tests" / "golden" / "demo"


def copy_project(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("out"), dirs_exist_ok=True)
    return dst


def with_source(proj, path):
    cfg = yaml.safe_load((proj / "schemagen.yml").read_text())
    cfg["source"] = {"path": str(path)}
    (proj / "schemagen.yml").write_text(yaml.safe_dump(cfg, allow_unicode=True))


def roundtrip(proj, fmt, tmp):
    """import -> export (fmt) -> import; returns the two model dumps."""
    a = load(proj).model
    p = copy_project(proj, tmp / f"rt_{fmt}")
    out = p / {"xlsx": "model.xlsx", "csvdir": "tables", "json": "model.json"}[fmt]
    json_model.export(a, out) if fmt == "json" else table_out.export(a, out)
    with_source(p, out.name)
    return a.model_dump(), load(p).model.model_dump()


@pytest.fixture(scope="module")
def synth_dirs(tmp_path_factory):
    d = tmp_path_factory.mktemp("synth")
    for n in (1000, 5000): synth.main(n, 1, str(d / f"s{n}"))
    return d


@pytest.mark.parametrize("fmt", ["xlsx", "csvdir", "json"])
def test_roundtrip_demo(fmt, tmp_path):
    a, b = roundtrip(DEMO, fmt, tmp_path)
    assert a == b


@pytest.mark.parametrize("n,fmt", [(1000, "xlsx"), (1000, "csvdir"), (1000, "json"), (5000, "csvdir"), (5000, "json")])
def test_roundtrip_synthetic(synth_dirs, n, fmt, tmp_path):
    a, b = roundtrip(synth_dirs / f"s{n}", fmt, tmp_path)
    assert a == b and len(a["conductors"]) == n


def test_synthetic_is_deterministic(tmp_path):
    synth.main(300, 7, str(tmp_path / "a")); synth.main(300, 7, str(tmp_path / "b"))
    for f in (tmp_path / "a").rglob("*"):
        if f.is_file(): assert f.read_bytes() == (tmp_path / "b" / f.relative_to(tmp_path / "a")).read_bytes()


# ---------------------------------------------------------------- property test: random row modules
DEVICES = ["ECU engine control unit", "SP-A splice", "SP-B splice", "X-BH bulkhead D-SUB 9", "CB-1 5 A", "BB1 bus", "GNDB ground",
           "DSP display", "lamp without code", "K-1 relay"]
txt = st.text(alphabet=st.characters(codec="utf-8", categories=["L", "N"], include_characters=" -_./()"), max_size=12).map(str.strip)
word = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=8)
extra_val = st.one_of(txt, st.integers(-5, 10**6), st.floats(allow_nan=False, allow_infinity=False, width=32), st.booleans(),
                      st.lists(word, max_size=3), st.dictionaries(word, word, max_size=2))
src = st.lists(st.tuples(word, st.one_of(st.just(""), word)), max_size=2).map(lambda xs: "; ".join(f"{d} p. {p}" if p else d for d, p in xs))
num = st.one_of(st.none(), st.floats(0, 500, allow_nan=False).map(lambda x: round(x, 4)), st.just("~3"))


@st.composite
def projects(draw):
    n = draw(st.integers(1, 6))
    rows = []
    for i in range(n):
        r = dict(id=f"W{i}", p1=draw(st.sampled_from(DEVICES)), p1c=draw(st.sampled_from(["J1", "Cabin half", "Engine half", "Stud", ""])),
                 p1p=draw(st.one_of(st.integers(1, 9).map(str), st.just(""), st.integers(1, 9))), p2=draw(st.sampled_from(DEVICES)),
                 p2c=draw(st.sampled_from(["J1", "Cabin half", "Engine half", "LOAD", ""])), p2p=draw(st.sampled_from(["1", "2", "H", ""])),
                 func=draw(txt), bus=draw(st.sampled_from(["14 V", "24 V", "5 V", "GND", "—", "", "12 V"])),
                 awg=draw(st.sampled_from(["22", "20", "8", "TBD", "", "18 AWG"])), st=draw(st.sampled_from(["Proposed", "Open: pin", ""])))
        opt = (("label", txt), ("name", txt), ("notes", txt), ("zone", word), ("harn", word), ("prot", word), ("col", st.sampled_from(["", "WH", "GNWH"])))
        for k, s in opt:
            if draw(st.booleans()): r[k] = draw(s)
        if draw(st.booleans()): r["src"] = draw(src)
        if draw(st.booleans()): r["amps"] = draw(num)
        if draw(st.booleans()): r["length"] = draw(num)
        if draw(st.booleans()): r["p1side"] = draw(st.sampled_from(["near", "far", ""]))
        for k in draw(st.lists(word, max_size=3, unique=True)): r["x_" + k] = draw(extra_val)
        rows.append(r)
    P = [dict(id="CB-1", rating=draw(st.sampled_from([5, 7.5, "5 A?"])), panel=draw(txt), loads=draw(st.lists(word, max_size=2)),
              **{"x_" + k: draw(extra_val) for k in draw(st.lists(word, max_size=2, unique=True))})]
    D = [dict(id="D1", text=draw(txt), **{"x_" + k: draw(extra_val) for k in draw(st.lists(word, max_size=2, unique=True))})]
    O = [dict(id="O1", text=draw(txt), status=draw(st.sampled_from(["open", "closed"])), objects=draw(st.lists(word, max_size=2)))]
    return rows, P, D, O


def write_rows_project(d, rows, P, D, O):
    (d / "wirelist").mkdir(parents=True)
    (d / "wirelist" / "ss01_x.py").write_text(f"R = {rows!r}\nP = {P!r}\nD = {D!r}\nO = {O!r}\n", encoding="utf-8")
    (d / "schemagen.yml").write_text(yaml.safe_dump(dict(harnesses={"X-BH": ["Bulkhead", "X-BH", "engine"]}, breaker_prefixes=["CB-"],
                                                         relay_prefixes=["K-"], sides={"X-BH": {"Cabin half": "near"}})))


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(projects())
def test_roundtrip_property(p):
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "p"
        write_rows_project(d, *p)
        a = load(d).model
        for fmt, out in (("csvdir", "tables"), ("json", "model.json"), ("xlsx", "model.xlsx")):
            q = Path(t) / fmt
            copy_project(d, q)
            json_model.export(a, q / out) if fmt == "json" else table_out.export(a, q / out)
            with_source(q, out)
            assert load(q).model.model_dump() == a.model_dump(), fmt


# ---------------------------------------------------------------- lossless: unknown keys survive
def test_unknown_keys_survive_export(tmp_path):
    rows = [dict(id="W1", p1="ECU unit", p1c="J1", p1p="1", p2="CB-1 5 A", p2c="LOAD", p2p="", func="x", bus="14 V", awg="20",
                 src="EWD-1 p. 4", zone="Z1", harn="H1", prot="CB-1", col="WH", route=["Z1", "Z2"], legacy="OLD-1", under="loom", dom="SYS")]
    P = [dict(id="CB-1", rating=5, panel="ECU", loads=["ECU"], curve_ref="MS-1")]
    D = [dict(id="D1", text="t", by="me", ref="memo 3")]
    O = [dict(id="O1", text="t", status="open", owner="me", due="2026-12-01")]
    write_rows_project(tmp_path / "p", rows, P, D, O)
    m = load(tmp_path / "p").model
    c = m.conductors[0]
    assert (c.zone, c.harness, c.protection, c.colour, c.sources[0].doc, c.sources[0].page) == ("Z1", "H1", "CB-1", "WH", "EWD-1", "4")
    assert c.extra == {"route": ["Z1", "Z2"], "legacy": "OLD-1", "under": "loom", "dom": "SYS"}
    pd = next(p for p in m.protective_devices if p.id == "CB-1")
    assert (pd.rating_a, pd.panel, pd.loads, pd.extra) == (5.0, "ECU", ["ECU"], {"curve_ref": "MS-1"})
    assert m.decisions[0].extra == {"ref": "memo 3"} and m.open_items[0].extra == {"due": "2026-12-01"}
    table_out.export(m, tmp_path / "w.xlsx")
    from openpyxl import load_workbook
    wb = load_workbook(tmp_path / "w.xlsx")
    head = [c.value for c in wb["Wires"][1]]
    assert {"route:json", "legacy", "under", "dom", "zone", "harness", "protection", "sources", "colour"} <= set(head)
    assert "curve_ref" in [c.value for c in wb["Protection"][1]] and "due" in [c.value for c in wb["Open items"][1]]


def test_table_input_unknown_columns_kept(tmp_path):
    d = copy_project(DEMO, tmp_path / "d")
    (d / "w.csv").write_text("id,from,from pin,to,to pin,gauge,My column,src\nW1,ECU unit,1,BB1 bus,,20,hello,DOC p. 2\n", encoding="utf-8")
    with_source(d, "w.csv")
    c = load(d).model.conductors[0]
    assert c.extra == {"My column": "hello"} and c.sources[0].text() == "DOC p. 2" and c.gauge == "20"


# ---------------------------------------------------------------- validation messages
def test_validation_errors_name_file_row_column(tmp_path):
    d = copy_project(DEMO, tmp_path / "d")
    (d / "w.csv").write_text("Wire ID,from,to,to side\nW1,ECU unit,,\n,A,B,\nW3,A,X-BH bulkhead D-SUB 9,left\n", encoding="utf-8")
    cfg = yaml.safe_load((d / "schemagen.yml").read_text())
    cfg["source"] = {"path": "w.csv", "columns": {"id": "Wire ID"}}
    (d / "schemagen.yml").write_text(yaml.safe_dump(cfg))
    with pytest.raises(ModelError) as e:
        load(d)
    msg = str(e.value)
    assert "w.csv, row 2, column 'to': 'to' is empty" in msg
    assert "w.csv, row 3, column 'Wire ID': 'Wire ID' is empty" in msg
    assert "w.csv, row 4, column 'to side': side must be near or far" in msg


def test_non_numeric_current_warns_and_is_kept(tmp_path):
    write_rows_project(tmp_path / "p", [dict(id="W1", p1="A", p2="B", amps="~3")], [], [], [])
    L = load(tmp_path / "p")
    assert L.model.conductors[0].extra == {"amps": "~3"} and L.model.conductors[0].current_a is None
    assert any("ss01_x.py, row 1, column 'amps'" in w for w in L.warnings)


# ---------------------------------------------------------------- sides
def test_explicit_sides_and_guess_warning(tmp_path):
    L = load(DEMO)
    x = next(c for c in L.model.connectors if c.id == "X-BH")
    assert [(h.name, h.side, h.guessed) for h in x.halves] == [("Cabin half", "near", False), ("Engine half", "far", False)]
    assert not L.warnings
    d = copy_project(DEMO, tmp_path / "d")
    cfg = yaml.safe_load((d / "schemagen.yml").read_text()); cfg.pop("sides"); (d / "schemagen.yml").write_text(yaml.safe_dump(cfg))
    L = load(d)
    assert any("half 'Engine half' guessed as far" in w for w in L.warnings)


def test_pdo_tables_become_objects():
    L = load(next(iter([DEMO])))
    assert {p.id for p in L.model.protective_devices} >= {"CB-ECU", "CB-GEN", "CB-MAIN"}
    assert next(p for p in L.model.protective_devices if p.id == "CB-ECU").rating_a == 5.0


def test_net_semantics_on_typed_model():
    m = load(DEMO).model
    net = Net(m)
    i = next(k for k, c in enumerate(m.conductors) if c.label == "L05")
    assert sorted(m.conductors[j].end(e).device.split()[0] for j, e in net.ends(i)) == ["CB-ECU", "ECU"]
    lab = {m.conductors[j].label for j, _ in net.next_hop(next(k for k, c in enumerate(m.conductors) if c.label == "L04"), 1)}
    assert lab == {"L10"}  # the other side of CB-ECU: breakers are elements, not connections
    assert all(n.id.startswith("net:") for n in net.nets()) and len({n.id for n in net.nets()}) == len(net.nets())


# ---------------------------------------------------------------- golden files, schema, performance
def test_demo_outputs_match_golden(tmp_path):
    from schemagen.cli import draw
    d = copy_project(DEMO, tmp_path / "d")
    draw(d, no_render=True)
    for f in GOLDEN.iterdir():
        if f.name == "wires.csv": continue
        assert (d / "out" / f.name).read_text(encoding="utf-8") == f.read_text(encoding="utf-8"), f.name


def test_json_schema_matches_models():
    for name, schema in json_schemas().items():
        on_disk = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        assert on_disk == json.loads(json.dumps(schema)), f"schemas/{name} is stale: run `schemagen schema`"


@pytest.mark.perf
def test_load_and_net_5k_within_2s(synth_dirs):
    t = time.perf_counter()
    m = load(synth_dirs / "s5000").model
    Net(m).nets()
    assert time.perf_counter() - t <= 2.0
