"""The app's Simulate overlay (docs/api.md, Overlay): one DC operating point with sources and loads inferred where part
data is missing (plus the sources added in the app), then a status and a one-line reason per object.

Wire and breaker sizes are judged against the protection table (FAA AC 43.13-1B Table 11-3, core/data/protection.yml):
the largest protector rating for a gauge is also taken as the most current that gauge may carry.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from ..core import tables
from ..core.context import Ctx
from ..core.model import Model
from .api import operating_point

RANKS = {"ok": 0, "warn": 1, "error": 2}


def _table(kind: str, cfg: Any) -> list[tuple[int, float]]:
    """(gauge, max A) from the lightest gauge to the heaviest."""
    t = tables.table("protection", cfg).get("fuse" if kind == "fuse" else "breaker", {})
    return sorted(((int(k), float(v)) for k, v in t.items()), key=lambda x: -x[0])


def overlay(m: Model, cfg: Any, sources: list[dict[str, Any]] | None = None, measured: dict[str, float] | None = None,
            ctx: Ctx | None = None) -> dict[str, Any]:
    ctx = ctx or Ctx(m, cfg)
    scfg = dataclasses.replace(cfg, sim={**(cfg.sim or {}), "infer": True}) if cfg is not None else None
    d = tables.table("sim", scfg)
    op = operating_point(m, scfg, {"scenario": "app", "sources": sources or []}, measured, ctx)
    items: dict[str, dict[str, str]] = {}

    def put(key: str, status: str, reason: str) -> None:
        if key not in items or RANKS[status] > RANKS[items[key]["status"]]: items[key] = dict(status=status, reason=reason)
    conds = m.conductors
    pds = {p.id: p for p in m.protective_devices}
    cur = {c["id"]: c["current_A"] for c in op.conductors}
    feeder: dict[int, Any] = {}
    for pid, idx in ctx.protected_by.items():
        pd = pds.get(pid)
        rating = pd.rating_a if pd else None
        for i in idx:
            feeder[i] = pd
            awg, c = conds[i].awg, conds[i]
            lim = tables.max_rating(awg, pd.kind if pd else "breaker", cfg) if awg is not None else None
            if rating and lim and rating > lim:
                put(f"conductor:{c.id}", "error", f"{awg} AWG is too small for {rating:g} A {pd.kind if pd else 'breaker'} {pid} (max {lim:g} A)")
                put(f"component:{pid}", "error", f"{rating:g} A is too big for {awg} AWG wire {c.label} (max {lim:g} A)")
    gauges = _table("breaker", cfg)
    steps = int(d.get("oversize_steps", 3))
    for i, c in enumerate(conds):
        a, awg = cur.get(c.id, 0.0), c.awg
        if awg is None: continue
        lim = tables.max_rating(awg, "breaker", cfg)
        if lim and a > lim: put(f"conductor:{c.id}", "error", f"{a:.1f} A is more than {awg} AWG may carry ({lim:g} A)"); continue
        pd = feeder.get(i)
        need = max(a, pd.rating_a or 0.0) if pd else a
        if a < 0.05 or awg not in [g for g, _ in gauges]: continue
        k = next((j for j, (_, mx) in enumerate(gauges) if mx >= need), None)
        have = [g for g, _ in gauges].index(awg)
        if k is not None and have - k >= steps:
            put(f"conductor:{c.id}", "warn", f"{awg} AWG carries {a:.2f} A{f' behind {pd.rating_a:g} A {pd.id}' if pd and pd.rating_a else ''}; "
                                             f"{gauges[k][0]} AWG would do")
    warn = float(d.get("breaker_warn_loading", 0.8))
    for p in op.protective:
        key, ld, r = f"component:{p['id']}", p["loading"], p["rating_A"]
        if p["trips"]: put(key, "error", f"trips: {p['current_A']:.1f} A through its {r:g} A rating" + (f" (in {p['trip_s']:.2g} s)" if p["trip_s"] else ""))
        elif ld is not None and ld > 1: put(key, "error", f"undersized: {p['current_A']:.1f} A is above its {r:g} A rating")
        elif ld is not None and ld >= warn: put(key, "warn", f"{p['current_A']:.1f} A is {100 * ld:.0f} % of its {r:g} A rating")
    unfed = set(op.unpowered)
    for ld in op.loads:
        if ld["off"] or ld["powered"]: continue
        v, vmin = ld["voltage_V"], ld["v_min"]
        put(f"component:{ld['component']}", "error", "no supply: no source reaches it" if v < 0.5 else f"{v:.2f} V is below its minimum {vmin:g} V")
    for b in op.buses:
        if b["id"] in unfed: put(f"component:{b['id']}", "error", f"no source reaches this bus ({b['loads']} load{'s' * (b['loads'] != 1)} on it)")
    errors = sum(x["status"] == "error" for x in items.values())
    trips = sum(p["trips"] for p in op.protective)
    problems = sum(x["status"] != "ok" for x in items.values())
    text = f"{problems} problem{'s' * (problems != 1)}, {trips} trip{'s' * (trips != 1)}" + (f", {len(unfed)} unpowered bus{'es' * (len(unfed) != 1)}" if unfed else "")
    if op.missing: text = "Cannot simulate: " + "; ".join(op.missing)
    elif not op.converged: text = f"The simulation did not converge: {op.message}"
    return dict(ok=op.converged and not op.missing and not unfed and not errors,
                summary=dict(problems=problems, trips=trips, unpowered=len(unfed), text=text),
                buses=[dict(id=b["id"], voltage_V=round(b["voltage_V"], 4), nominal_V=b["nominal_V"], powered=b["powered"]) for b in op.buses],
                breakers=[dict(id=p["id"], current_A=round(p["current_A"], 4), rating_A=p["rating_A"], loading=p["loading"], trips=p["trips"])
                          for p in op.protective],
                items=items, assumptions=[f"{a.what}: {a.note} ({a.provenance})" for a in op.assumptions])
