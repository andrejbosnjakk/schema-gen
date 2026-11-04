"""`schemagen sim`: run scenario files and the fault sweep, write an HTML + JSON report, exit 1 when an
expectation fails or a scenario does not converge.

Scenario file (one per scenario, default <project>/scenarios/*.yml):

    scenario: master on, ECU on
    set: {SW-MSTR: closed, CB-GEN: open, "LD-L10-*": off, K-3: energized}   # ids or glob patterns
    faults: [{short: L05}, {open: L07}, {fail: DCDC1}]                     # short to ground, open a wire, fail a source
    expect:
      powered: [ECU, DSP]
      max_drop_V: {ECU: 0.5}
      min_voltage: {BB1: 12.0}
      no_trip: true
"""
from __future__ import annotations

import dataclasses
import html
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from ..core.context import Ctx
from ..core.load import load, measured_lengths
from . import api


def _jsonable(x: Any) -> Any:
    if dataclasses.is_dataclass(x) and not isinstance(x, type): return {k: _jsonable(v) for k, v in dataclasses.asdict(x).items()}
    if isinstance(x, dict): return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [_jsonable(v) for v in x]
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))): return None
    return x


def run(project: str | Path, scenario_files: list[str] | None = None, faults: bool = False, out: Path | None = None) -> dict[str, Any]:
    L = load(project)
    cfg, m = L.cfg, L.model
    meas = measured_lengths(cfg)
    files = [Path(f) for f in scenario_files] if scenario_files else sorted((cfg.root / "scenarios").glob("*.yml"))
    ctx = Ctx(m, cfg)
    ops = []
    for f in files:
        sc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        sc.setdefault("scenario", f.stem)
        ops.append((f.name, api.operating_point(m, cfg, sc, meas, ctx)))
    if not files: ops.append(("(default)", api.operating_point(m, cfg, None, meas, ctx)))
    sweep = api.fault_sweep(m, cfg, None, meas, ctx) if faults else None
    rep = dict(project=str(cfg.root), scenarios=[dict(file=f, **_jsonable(op), ok=op.ok) for f, op in ops],
               fault_sweep=_jsonable(sweep) if sweep else None)
    out = out or cfg.out / "sim"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "report.html").write_text(to_html(rep), encoding="utf-8")
    rep["_paths"] = [str(out / "report.json"), str(out / "report.html")]
    return rep


def to_html(rep: dict[str, Any]) -> str:
    e = html.escape
    parts = []
    for sc in rep["scenarios"]:
        st = "pass" if sc["ok"] else "FAIL"
        exp = "".join(f"<tr class=\"{'ok' if x['ok'] else 'bad'}\"><td>{e(x['kind'])}</td><td>{e(x['detail'])}</td></tr>" for x in sc["expectations"])
        bus = "".join(f"<tr><td>{e(b['id'])}</td><td>{b['voltage_V']:.3f}</td></tr>" for b in sc["buses"])
        prot = "".join(f"<tr class=\"{'bad' if p['trips'] else ''}\"><td>{e(p['id'])}</td><td>{p['current_A']:.3f}</td><td>{p['rating_A'] or ''}</td>"
                       f"<td>{_pct(p['loading'])}</td><td>{_sec(p['trip_s'])}</td></tr>"
                       for p in sorted(sc["protective"], key=lambda p: -(p["loading"] or 0))[:40])
        fail = [ld for ld in sc["loads"] if not ld["powered"] and not ld["off"]]
        fl = "".join(f"<li>{e(ld['component'])}: {ld['voltage_V']:.2f} V (min {ld['v_min']} V)</li>" for ld in fail) or "<li>none</li>"
        asm = "".join(f"<li><b>{e(a['what'])}</b> ({e(a['provenance'])}): {e(a['note'])}</li>" for a in sc["assumptions"])
        parts.append(f"<section><h2>{e(sc['scenario'])} <span class=\"{st.lower()}\">{st}</span></h2>"
                     f"<p>{'converged' if sc['converged'] else 'NOT converged: ' + e(sc['message'])} in {sc['iterations']} iterations, "
                     f"KCL residual {sc['residual']:.1e} A, {sc['seconds'] * 1000:.0f} ms</p>"
                     f"<h3>Expectations</h3><table>{exp or '<tr><td>none</td></tr>'}</table>"
                     f"<h3>Bus voltages</h3><table><tr><th>bus</th><th>V</th></tr>{bus}</table>"
                     f"<h3>Protective devices (most loaded first)</h3><table><tr><th>device</th><th>A</th><th>rating A</th><th>loading</th>"
                     f"<th>trip</th></tr>{prot}</table><h3>Loads below their minimum voltage</h3><ul>{fl}</ul>"
                     f"<h3>Assumptions</h3><ul>{asm}</ul></section>")
    sw = rep.get("fault_sweep")
    if sw:
        rows = "".join(f"<tr class=\"{'bad' if _bad(r) else ''}\">"
                       f"<td>{e(r['node'])}</td><td>{r['fault_current_A']:.0f}</td><td>{e(r.get('first_trip') or 'none')}</td>"
                       f"<td>{'' if r.get('trip_s') is None else format(r['trip_s'], '.3f')}</td><td>{'yes' if r.get('within_interrupt') else 'NO'}</td>"
                       f"<td>{'yes' if r.get('selective') else 'NO'}</td><td>{e(str(r.get('wire_survives')))} {e(r.get('worst_wire', ''))}</td></tr>"
                       for r in sw["rows"])
        parts.append(f"<section><h2>Fault sweep</h2><p>{len(sw['rows'])} nodes shorted to ground, {sw['seconds']:.1f} s</p>"
                     f"<table><tr><th>node</th><th>fault A</th><th>trips first</th><th>trip s</th><th>within interrupt</th><th>selective</th>"
                     f"<th>wire survives</th></tr>{rows}</table></section>")
    css = ("body{font:14px system-ui,sans-serif;margin:16px;color:#111;background:#fff}table{border-collapse:collapse;margin:4px 0 12px}"
           "td,th{border:1px solid #bbb;padding:2px 6px;text-align:left}.bad td{background:#ffe5e5}.ok td{background:#e8f8ea}"
           ".pass{color:#176f2c}.fail{color:#b00020}@media (prefers-color-scheme: dark){body{background:#111;color:#eee}"
           ".bad td{background:#4a1d22}.ok td{background:#173a20}td,th{border-color:#555}}")
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Simulation report</title><style>{css}</style></head>"
            f"<body><h1>Simulation report</h1><p>Design check, not certification evidence. Every result lists its assumptions.</p>"
            f"{''.join(parts)}</body></html>")


def _bad(r: dict[str, Any]) -> bool:
    return not r.get("first_trip") or not r.get("selective") or r.get("wire_survives") is False or not r.get("within_interrupt")


def _pct(x: float | None) -> str:
    return "" if x is None else f"{100 * x:.0f} %"


def _sec(x: float | None) -> str:
    return "" if x is None else f"{x:.2f} s"


def run_cli(a: Any) -> int:
    rep = run(a.config, a.scenarios or None, a.faults == "all", Path(a.output) if a.output else None)
    bad = 0
    for sc in rep["scenarios"]:
        flag = "pass" if sc["ok"] else "FAIL"
        print(f"{flag:4}  {sc['scenario']}: {sc['iterations']} iterations, residual {sc['residual']:.1e} A")
        for x in sc["expectations"]:
            if not x["ok"]: print(f"      expectation failed: {x['detail']}")
        if not sc["converged"]: print(f"      {sc['message']}")
        bad += not sc["ok"]
    sw = rep.get("fault_sweep")
    if sw:
        r = sw["rows"]
        print(f"fault sweep: {len(r)} nodes, {sum(1 for x in r if not x.get('first_trip'))} not cleared, "
              f"{sum(1 for x in r if not x.get('selective', True))} not selective, {sum(1 for x in r if x.get('wire_survives') is False)} wire damage, "
              f"{sum(1 for x in r if not x.get('within_interrupt', True))} over interrupt rating ({sw['seconds']:.1f} s)")
    print("report:", ", ".join(rep["_paths"]))
    sys.stdout.flush()
    return 1 if bad else 0
