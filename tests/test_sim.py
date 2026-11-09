"""M3: DC simulation. Known answers are hand calculations written out below each circuit."""
import math
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import yaml

from schemagen import synth
from schemagen.cli import main
from schemagen.core import tables
from schemagen.core.load import load, measured_lengths
from schemagen.sim import api
from schemagen.sim.engine import Circuit, spice, spice_nodes, trip_time

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"


def close(got, want, rel=1e-3, abs_=1e-3):
    """|error| <= 0.1 % or <= 1 mV / 1 mA, as the metric says."""
    return abs(got - want) <= max(rel * abs(want), abs_)


def kcl_ok(c, r):
    return r.converged and r.residual <= 1e-9


# ---------------------------------------------------------------- 1-2 dividers and sources
def test_kat_divider():
    # 12 V across 1 kΩ + 2 kΩ: V_mid = 12 * 2000 / 3000 = 8 V, I = 4 mA
    c = Circuit(); c.vsrc("V", "a", "0", 12.0); c.r("R1", "a", "b", 1000); c.r("R2", "b", "0", 2000)
    r = c.solve()
    assert close(r.v["b"], 8.0) and close(r.i["R1"], 0.004, abs_=1e-6) and kcl_ok(c, r)


def test_kat_battery_internal_resistance_resistive_load():
    # 12.6 V, R_int 0.05 Ω, load 2 Ω: I = 12.6 / 2.05 = 6.146341 A, V = 12.29268 V
    c = Circuit(); c.vsrc("B", "p", "0", 12.6, rs=0.05); c.load("L", "p", "0", "resistive", 2.0)
    r = c.solve()
    assert close(r.i["B"], 12.6 / 2.05) and close(r.v["p"], 12.6 * 2 / 2.05) and kcl_ok(c, r)


def test_kat_parallel_wires():
    # 12 V, two 0.1 Ω wires in parallel (0.05 Ω), then 1 Ω: I = 12 / 1.05 = 11.428571 A, each wire half
    c = Circuit(); c.vsrc("V", "a", "0", 12.0); c.r("W1", "a", "b", 0.1); c.r("W2", "a", "b", 0.1); c.load("L", "b", "0", "resistive", 1.0)
    r = c.solve()
    assert close(r.i["W1"], 12 / 1.05 / 2) and close(r.i["W2"], 12 / 1.05 / 2) and close(r.v["b"], 12 / 1.05) and kcl_ok(c, r)


def test_kat_wire_resistance_table():
    # AWG 20: d = 0.127 * 92^(16/39) = 0.8118 mm, A = 0.5176 mm², R = 1.7241e-8 / 0.5176e-6 = 33.31 mΩ/m
    assert close(tables.ohm_per_m(20), 0.03331, rel=1e-3, abs_=1e-6)
    # at 60 °C: x (1 + 0.00393 * 40) = 1.1572
    assert close(tables.ohm_per_m(20, 60.0), 0.03331 * 1.1572, rel=1e-3, abs_=1e-6)
    # AWG 10: 3.277 mΩ/m
    assert close(tables.ohm_per_m(10), 0.003277, rel=1e-3, abs_=1e-7)


# ---------------------------------------------------------------- 3-5 nonlinear loads (Newton)
def test_kat_constant_power_newton():
    # 12.6 V, 0.05 Ω, 60 W: V^2 - 12.6 V + 0.05*60 = 0 -> V = (12.6 + sqrt(12.6^2 - 12)) / 2 = 12.357227 V
    c = Circuit(); c.vsrc("B", "p", "0", 12.6, rs=0.05); c.load("L", "p", "0", "constant_power", 60.0, v_min=9)
    r = c.solve()
    v = (12.6 + math.sqrt(12.6 ** 2 - 4 * 0.05 * 60)) / 2
    assert close(r.v["p"], v) and close(r.i["L"], 60 / v) and r.iterations <= 50 and kcl_ok(c, r)


def test_kat_constant_power_through_wire():
    # 14 V ideal, 0.2 Ω wire, 50 W: (14 - V) / 0.2 = 50 / V -> V^2 - 14 V + 10 = 0 -> V = 7 + sqrt(39) = 13.244998 V
    c = Circuit(); c.vsrc("V", "a", "0", 14.0); c.r("W", "a", "b", 0.2); c.load("L", "b", "0", "constant_power", 50.0, v_min=9)
    r = c.solve()
    assert close(r.v["b"], 7 + math.sqrt(39)) and kcl_ok(c, r)


def test_kat_constant_current_load():
    # 12 V, 0.5 Ω wire, 2 A constant current: V = 12 - 1 = 11 V
    c = Circuit(); c.vsrc("V", "a", "0", 12.0); c.r("W", "a", "b", 0.5); c.load("L", "b", "0", "constant_current", 2.0, v_min=9)
    r = c.solve()
    assert close(r.v["b"], 11.0) and close(r.i["W"], 2.0) and kcl_ok(c, r)


# ---------------------------------------------------------------- 6-7 current-limited source
def test_kat_current_limited_source_in_limit():
    # 24 V, 0.01 Ω, limit 10 A into 1 Ω: unlimited would be 23.76 A, so 10 A and V = 10 V
    c = Circuit(); c.vsrc("S", "o", "0", 24.0, rs=0.01, i_limit=10.0); c.load("L", "o", "0", "resistive", 1.0)
    r = c.solve()
    assert close(r.i["S"], 10.0) and close(r.v["o"], 10.0) and r.limited == ["S"] and kcl_ok(c, r)


def test_kat_current_limited_source_below_limit():
    # same source into 10 Ω: I = 24 / 10.01 = 2.397602 A, not limited
    c = Circuit(); c.vsrc("S", "o", "0", 24.0, rs=0.01, i_limit=10.0); c.load("L", "o", "0", "resistive", 10.0)
    r = c.solve()
    assert close(r.i["S"], 24 / 10.01) and r.limited == [] and kcl_ok(c, r)


def test_kat_dcdc_input_power():
    # 24 V DC/DC (0.01 Ω) into 24 Ω: I_out = 24 / 24.01, P_out = 24 * 24/24.01 * (24 - 0.01*I) ...; input power = P_out / 0.9
    c = Circuit(); c.vsrc("D", "o", "0", 24.0, rs=0.01, i_limit=15.0); c.load("L", "o", "0", "resistive", 24.0)
    c.vsrc("B", "b", "0", 13.2, rs=0.0)
    ld = c.load("in", "b", "0", "constant_power", 0.0, 0.0, 1.0); ld.dcdc_of, ld.efficiency = "D", 0.9
    r = c.solve()
    i_out = 24 / 24.01; p_out = i_out ** 2 * 24.0
    assert close(r.i["in"], p_out / 0.9 / 13.2) and kcl_ok(c, r)


# ---------------------------------------------------------------- 8-10 relay logic
def relay_circuit(switch_closed, coil_series=0.0):
    c = Circuit()
    c.vsrc("B", "p", "0", 14.0)
    if switch_closed: c.r("SW", "p", "a1", 0.005 + coil_series, "switch")
    c.r("coil", "a1", "0", 85.0, "coil")
    c.r("com-no", "p", "lamp", 0.005, "switch")
    c.load("lamp", "lamp", "0", "resistive", 10.0)
    from schemagen.sim.engine import Relay
    c.relays.append(Relay("K1", "coil", v_pickup=8.4, v_dropout=3.0, no=["com-no"]))
    return c


def test_kat_relay_picks_up():
    # coil 85 Ω at 14 V (minus 5 mΩ): 13.9992 V > 8.4 V pick-up: contact closes, lamp 10 Ω: I = 14 / 10.005 = 1.39930 A
    c = relay_circuit(True)
    r = c.solve()
    assert r.relay_states == {"K1": True} and close(r.i["lamp"], 14 / 10.005) and kcl_ok(c, r)


def test_kat_relay_stays_open_without_coil():
    c = relay_circuit(False)
    r = c.solve()
    assert r.relay_states == {"K1": False} and close(r.i["lamp"], 0.0) and kcl_ok(c, r)


def test_kat_relay_below_pickup():
    # 100 Ω in series with the 85 Ω coil: V_coil = 14 * 85 / 185.005 = 6.432 V < 8.4 V: contact stays open
    c = relay_circuit(True, coil_series=100.0)
    r = c.solve()
    assert r.relay_states == {"K1": False} and close(r.v["a1"], 14 * 85 / 185.005)


def test_relay_oscillation_is_reported():
    # coil fed through its own NC contact: energised opens the feed, de-energised closes it -> no stable state
    from schemagen.sim.engine import Relay
    c = Circuit(); c.vsrc("B", "p", "0", 14.0)
    c.r("nc", "p", "a1", 0.005, "switch"); c.r("coil", "a1", "0", 85.0, "coil")
    c.relays.append(Relay("K1", "coil", 8.4, 3.0, nc=["nc"]))
    r = c.solve()
    assert not r.converged and r.oscillating == ["K1"] and "oscillate" in r.message


# ---------------------------------------------------------------- 11-12 breaker trip curve
def test_kat_trip_time_interpolation():
    curve = [(1.15, 3600), (1.5, 60), (2, 12), (5, 1.5), (10, 0.02)]
    # log-log between (2, 12) and (5, 1.5) at 3x: t = exp(ln 12 + ln(3/2)/ln(5/2) * (ln 1.5 - ln 12))
    want = math.exp(math.log(12) + math.log(1.5) / math.log(2.5) * (math.log(1.5) - math.log(12)))
    assert close(trip_time(3.0, curve), want, rel=1e-9)
    assert trip_time(1.0, curve) == math.inf and trip_time(20, curve) == 0.02 and trip_time(2.0, curve) == 12


# ---------------------------------------------------------------- 13-15 projects: fault current, trip, selectivity
CARDS = {
    "BAT": dict(device="^BAT$", kind="battery", source=dict(v_oc=12.0, r_int=0.01),
                connectors=[dict(id="+", match=r"^\+$", type="power_out"), dict(id="-", match="^-$", type="ground")]),
    "CBM": dict(device="^CB-M$", kind="breaker", trip_curve=[[1.15, 3600], [2, 30], [10, 1.0]], r_closed=0.002,
                connectors=[dict(id="LINE", match="^LINE$", type="power_in"), dict(id="LOAD", match="^LOAD$", type="power_out")]),
    "CBL": dict(device="^CB-L$", kind="breaker", trip_curve=[[1.15, 3600], [2, 10], [10, 0.01]], r_closed=0.002,
                connectors=[dict(id="LINE", match="^LINE$", type="power_in"), dict(id="LOAD", match="^LOAD$", type="power_out")]),
    "LD": dict(device="^LD$", kind="load", load=dict(model="resistive", r_ohm=4.0),
               connectors=[dict(id="P", match="^P$", pins=[dict(n="1", type="power_in"), dict(n="2", type="ground")])]),
}


def tiny_project(d, cards=CARDS):
    """BAT + -> CB-M (30 A) -> BB1 -> CB-L (5 A) -> LD (4 Ω) -> GNDB -> BAT -. Every wire 1 m 10 AWG (3.277 mΩ),
    no contacts (studs), breakers 2 mΩ."""
    (d / "wirelist").mkdir(parents=True); (d / "cards").mkdir()
    rows = [("W1", "BAT", "+", "", "CB-M 30 A", "LINE", "", "14 V"), ("W2", "CB-M 30 A", "LOAD", "", "BB1 bus", "Stud", "", "14 V"),
            ("W3", "BB1 bus", "Stud", "", "CB-L 5 A", "LINE", "", "14 V"), ("W4", "CB-L 5 A", "LOAD", "", "SP-1 splice", "", "", "14 V"),
            ("W5", "SP-1 splice", "", "", "LD", "P", "1", "14 V"), ("W6", "LD", "P", "2", "GNDB", "Stud", "", "GND"),
            ("W7", "GNDB", "Stud", "", "BAT", "-", "", "GND")]
    R = [dict(id=i, p1=a, p1c=ac, p1p=ap, p2=b, p2c=bc, p2p=bp, func="x", bus=bus, awg="10", length=1.0) for i, a, ac, ap, b, bc, bp, bus in rows]
    (d / "wirelist" / "ss01_t.py").write_text(f"R = {R!r}\nP = {[dict(id='CB-M', rating=30), dict(id='CB-L', rating=5)]!r}\n", encoding="utf-8")
    for k, v in cards.items(): (d / "cards" / f"{k}.md").write_text(f"```yaml schemagen\n{yaml.safe_dump(v)}```\n", encoding="utf-8")
    (d / "schemagen.yml").write_text(yaml.safe_dump(dict(buses=["GNDB", "BB1"], breaker_prefixes=["CB-"], sim=dict(contact_resistance_by_awg={}))), encoding="utf-8")
    return d


RW = 0.003277  # 1 m of 10 AWG at 20 °C (≈ ASTM/IEC value, ohm)


def test_kat_project_operating_point(tmp_path):
    # series: R_int 0.01 + 5 wires * RW + 2 breakers * 0.002 + load 4 Ω + returns 2 * RW
    L = load(tiny_project(tmp_path / "p"))
    op = api.operating_point(L.model, L.cfg)
    rw = tables.ohm_per_m(10)
    i = 12.0 / (0.01 + 7 * rw + 0.004 + 4.0)
    ld = next(x for x in op.loads if x["component"] == "LD")
    assert close(ld["current_A"], i) and close(ld["voltage_V"], 4.0 * i) and op.residual <= 1e-9


def test_kat_fault_current_and_trip(tmp_path):
    # short at the splice SP-1: I = 12 / (0.01 + 4 RW + 0.004 + 0.001 fault + 2 RW return) (load in parallel with the
    # 1 mΩ short is negligible: < 0.1 %); CB-L sees it all: multiple = I / 5 > 10 -> 0.01 s; CB-M at I / 30
    L = load(tiny_project(tmp_path / "p"))
    sw = api.fault_sweep(L.model, L.cfg)
    row = next(r for r in sw.rows if r["node"].startswith("SP-1"))
    rw = tables.ohm_per_m(10)
    i = 12.0 / (0.01 + 3 * rw + 0.004 + 0.001 + 1 * rw)
    assert close(row["fault_current_A"], i, rel=2e-3)
    assert row["first_trip"] == "CB-L" and row["trip_s"] == 0.01 and row["selective"]
    assert row["within_interrupt"] and row["interrupt_provenance"] == "assumed"  # no interrupt rating in the data: 1000 A assumed


def test_kat_selectivity_violation(tmp_path):
    # give the upstream breaker the faster curve: a fault behind CB-L then trips CB-M first -> not selective
    cards = dict(CARDS); cards["CBM"] = dict(CARDS["CBM"], trip_curve=[[1.15, 3600], [2, 0.5], [10, 0.001]])
    L = load(tiny_project(tmp_path / "p", cards))
    row = next(r for r in api.fault_sweep(L.model, L.cfg).rows if r["node"].startswith("SP-1"))
    assert row["first_trip"] == "CB-M" and not row["selective"] and row["downstream_not_first"] == ["CB-L"]


def test_kat_wire_survival(tmp_path):
    # I²t limit for 10 AWG XLPE: (143 * 5.261 mm²)^2 = 5.66e5 A²s; fault ~ 600 A for 0.01 s = 3.6e3: survives
    L = load(tiny_project(tmp_path / "p"))
    row = next(r for r in api.fault_sweep(L.model, L.cfg).rows if r["node"].startswith("SP-1"))
    assert row["wire_survives"] and row["i2t_margin"] > 100
    assert close(tables.i2t_limit(10), (143 * tables.awg_area_mm2(10)) ** 2, rel=1e-12)


def test_scenario_expectations_and_cli_exit(tmp_path):
    d = tiny_project(tmp_path / "p")
    (d / "scenarios").mkdir()
    (d / "scenarios" / "ok.yml").write_text(yaml.safe_dump(dict(scenario="ok", expect=dict(powered=["LD"], no_trip=True, max_drop_V={"LD": 0.2}))), encoding="utf-8")
    assert main(["sim", str(d)]) == 0
    (d / "scenarios" / "bad.yml").write_text(yaml.safe_dump(dict(scenario="bad", set={"CB-L": "open"}, expect=dict(powered=["LD"]))), encoding="utf-8")
    assert main(["sim", str(d)]) == 1
    (d / "scenarios" / "bad.yml").write_text(yaml.safe_dump(dict(scenario="short", faults=[{"short": "W5"}], expect=dict(no_trip=True))), encoding="utf-8")
    assert main(["sim", str(d)]) == 1
    rep = (d / "out" / "sim" / "report.html").read_text(encoding="utf-8")
    assert "Assumptions" in rep and "short" in rep


def test_demo_scenarios_pass():
    assert main(["sim", str(DEMO), "-o", str(ROOT / "tests" / ".sim-out")]) == 0
    shutil.rmtree(ROOT / "tests" / ".sim-out", ignore_errors=True)


# ---------------------------------------------------------------- synthetic projects: Kirchhoff, Newton, speed
@pytest.fixture(scope="module")
def synth_projects(tmp_path_factory):
    d = tmp_path_factory.mktemp("sim")
    for n in (1000, 5000): synth.main(n, 1, str(d / f"s{n}"))
    return d


def test_synthetic_scenarios_kirchhoff_and_newton(synth_projects):
    for n in (1000, 5000):
        p = synth_projects / f"s{n}"
        L = load(p)
        for f in sorted((p / "scenarios").glob("*.yml")):
            op = api.operating_point(L.model, L.cfg, yaml.safe_load(f.read_text(encoding="utf-8")), measured_lengths(L.cfg))
            assert op.converged and op.iterations <= 50 and op.residual <= 1e-9, (n, f.name, op.message, op.residual)
            assert op.ok, [e for e in op.expectations if not e["ok"]]
            assert any(a.provenance == "measured" or "measured" in a.note for a in op.assumptions)


@pytest.mark.perf
def test_sim_speed(synth_projects):
    for n, lim in ((1000, 0.2), (5000, 2.0)):
        L = load(synth_projects / f"s{n}")
        sc = yaml.safe_load((synth_projects / f"s{n}" / "scenarios" / "normal.yml").read_text(encoding="utf-8"))
        api.operating_point(L.model, L.cfg, sc)  # warm caches (imports)
        t = time.perf_counter(); api.operating_point(L.model, L.cfg, sc, measured_lengths(L.cfg)); dt = time.perf_counter() - t
        assert dt <= lim, (n, dt)
    L = load(synth_projects / "s1000")
    t = time.perf_counter(); sw = api.fault_sweep(L.model, L.cfg, None, measured_lengths(L.cfg))
    assert time.perf_counter() - t <= 30 and len(sw.rows) > 500


# ---------------------------------------------------------------- ngspice cross-check
def ngspice(c):
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh: fh.write(spice(c))
    r = subprocess.run(["ngspice", "-b", fh.name], capture_output=True, text=True, timeout=60)
    Path(fh.name).unlink()
    vals = {m.group(1): float(m.group(2)) for m in re.finditer(r"^(n\d+) = (\S+)", r.stdout, re.M)}
    names = spice_nodes(c)
    return {k: vals[v] for k, v in names.items() if v in vals}


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_ngspice_cross_check():
    circuits = []
    c = Circuit(); c.vsrc("B", "p", "0", 12.6, rs=0.05); c.load("L", "p", "0", "constant_power", 60, v_min=9); c.r("R", "p", "q", 1.0); c.r("R2", "q", "0", 3)
    circuits.append(c)
    c = Circuit(); c.vsrc("V", "a", "0", 14.0); c.r("W1", "a", "b", 0.2); c.r("W2", "a", "b", 0.3)
    c.load("L1", "b", "0", "constant_power", 50, v_min=9); c.load("L2", "b", "0", "constant_current", 2.0, v_min=5); c.r("W3", "b", "c", 0.1)
    c.load("L3", "c", "0", "resistive", 6.0)
    circuits.append(c)
    c = Circuit(); c.vsrc("B", "p", "0", 13.2, rs=0.01)
    for k in range(5):
        c.r(f"f{k}", "p", f"n{k}", 0.05 * (k + 1)); c.load(f"l{k}", f"n{k}", "g", "constant_power", 10.0 * (k + 1), v_min=9)
    c.r("ret", "g", "0", 0.02)
    circuits.append(c)
    for c in circuits:
        mine = c.solve().v
        ref = ngspice(c)
        assert len(ref) >= 2
        for k, v in ref.items():
            if k in mine and abs(v) > 1e-6: assert abs(mine[k] - v) <= 0.005 * abs(v), (k, mine[k], v)


def test_no_part_data_is_not_a_pass_and_infer_assumes_it(synth_projects, tmp_path, capsys):
    d = tmp_path / "bare"
    shutil.copytree(synth_projects / "s1000", d, ignore=shutil.ignore_patterns("out", "cards"))
    assert main(["sim", str(d), "--faults", "all"]) == 2  # 0.5 printed "pass" with 0 nodes here
    assert "cannot simulate this project:" in capsys.readouterr().out
    L = load(d)
    L.cfg.sim = {**L.cfg.sim, "infer": True}
    op = api.operating_point(L.model, L.cfg)
    assert op.converged and not op.missing and {s["component"] for s in op.sources} >= {"BAT"}
    assert all(a.provenance == "assumed" for a in op.assumptions if "inferred" in a.note)
    assert any(ld["powered"] for ld in op.loads)
    assert len(api.fault_sweep(L.model, L.cfg).rows) > 0
    assert main(["sim", str(d), "--infer"]) in (0, 1)  # simulated: pass or fail on the scenario expectations


def unfed_bus_project(d):
    """tiny_project plus BB2 (14 V) with load LD2 on it and nothing feeding BB2."""
    tiny_project(d)
    R = [dict(id="W8", p1="BB2 bus", p1c="Stud", p2="LD2", p2c="P", p2p="1", func="x", bus="14 V", awg="20", length=1.0),
         dict(id="W9", p1="LD2", p1c="P", p1p="2", p2="GNDB", p2c="Stud", func="x", bus="GND", awg="20", length=1.0)]
    (d / "wirelist" / "ss02_unfed.py").write_text(f"R = {R!r}\n", encoding="utf-8")
    (d / "cards" / "LD2.md").write_text(f"```yaml schemagen\n{yaml.safe_dump(dict(CARDS['LD'], device='^LD2$'))}```\n", encoding="utf-8")
    cfg = yaml.safe_load((d / "schemagen.yml").read_text(encoding="utf-8")); cfg["buses"].append("BB2")
    (d / "schemagen.yml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return d


def test_unfed_bus_with_loads_is_never_a_pass(tmp_path, capsys):
    d = unfed_bus_project(tmp_path / "p")
    L = load(d)
    op = api.operating_point(L.model, L.cfg)
    bus = {b["id"]: b for b in op.buses}
    assert op.converged and op.unpowered == ["BB2"] and not op.ok
    assert bus["BB2"] == dict(id="BB2", voltage_V=0.0, nominal_V=14.0, powered=False, loads=1)  # floats near the return: shown as 0 V
    assert bus["BB1"]["powered"] and bus["BB1"]["voltage_V"] > 11
    assert not next(x for x in op.loads if x["component"] == "LD2")["powered"]
    assert main(["sim", str(d)]) == 1 and "bus BB2 has loads but no source reaches it" in capsys.readouterr().out
