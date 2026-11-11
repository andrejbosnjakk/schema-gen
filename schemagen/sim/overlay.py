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
    groups: dict[str, dict[str, Any]] = {}  # one per root cause: the summary counts these

    def put(key: str, status: str, reason: str, group: str | None = None, title: str = "") -> None:
        if key not in items or RANKS[status] > RANKS[items[key]["status"]]: items[key] = dict(status=status, reason=reason)
        g = groups.setdefault(group or key, dict(title=title or reason, objects=[], status=status))
        if key not in g["objects"]: g["objects"].append(key)
        if RANKS[status] > RANKS[g["status"]]: g["status"] = status
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
                kind = pd.kind if pd else "breaker"
                put(f"conductor:{c.id}", "error", f"{awg} AWG is too small for {rating:g} A {kind} {pid} (max {lim:g} A)", f"component:{pid}",
                    f"{c.label} is too small for {pid}")
                put(f"component:{pid}", "error", f"{rating:g} A is too big for {awg} AWG wire {c.label} (max {lim:g} A)", f"component:{pid}",
                    f"{c.label} is too small for {pid}")
    margin = float(d.get("heavy_margin", 2.0))
    for i, c in enumerate(conds):
        a, awg = cur.get(c.id, 0.0), c.awg
        if awg is None: continue
        lim = tables.max_rating(awg, "breaker", cfg)
        pd = feeder.get(i)
        if lim and a > lim:
            put(f"conductor:{c.id}", "error", f"{a:.1f} A is more than {awg} AWG may carry ({lim:g} A)", f"component:{pd.id}" if pd else None, f"{c.label} is too small for {pd.id}" if pd else "")
            continue
        prot = bool(pd and pd.rating_a)
        gauges = _table(pd.kind if prot else "breaker", cfg)
        order = [g for g, _ in gauges]
        if (a < 0.05 and not prot) or awg not in order: continue
        have = order.index(awg)
        # a wire is sized for its protector (two gauges thinner still allowed for it), else for its current with a margin
        need = pd.rating_a if prot else a * margin
        if have >= 2 and gauges[have - 2][1] >= need:
            k = next(j for j, (_, mx) in enumerate(gauges) if mx >= need)
            put(f"conductor:{c.id}", "warn", f"{awg} AWG carries {a:.2f} A{f' behind {pd.rating_a:g} A {pd.id}' if prot else ''}; {gauges[k][0]} AWG would do")
    warn = float(d.get("breaker_warn_loading", 0.8))
    for p in op.protective:
        key, ld, r = f"component:{p['id']}", p["loading"], p["rating_A"]
        if p["trips"]:
            put(key, "error", f"trips: {p['current_A']:.1f} A through its {r:g} A rating" + (f" (in {p['trip_s']:.2g} s)" if p["trip_s"] else ""),
                f"trip:{p['id']}", f"{p['id']} trips")
        elif ld is not None and ld > 1: put(key, "error", f"undersized: {p['current_A']:.1f} A is above its {r:g} A rating", key, f"{p['id']} is undersized")
        elif ld is not None and ld >= warn: put(key, "warn", f"{p['current_A']:.1f} A is {100 * ld:.0f} % of its {r:g} A rating", key, f"{p['id']} is nearly full")
    unfed = set(op.unpowered)
    bus_of = {b.id: b for b in m.buses}
    def bname(bid: str) -> str: return bus_of[bid].raw[len(bid):].strip() or bid  # "Cabin bus" from "BB-CABIN-BUS Cabin bus"
    on_bus: dict[str, str] = {}  # load component id -> id of the unfed bus it hangs on (through splices and breakers)
    net = ctx.net
    for bid in unfed:
        todo, seen = [(i, 3 - e) for i, e in net.at[(bus_of[bid].raw,)]], set()
        while todo:
            i, far = todo.pop()
            if (i, far) in seen: continue
            seen.add((i, far))
            t = conds[i].end(far)
            if net.role(t.device) == "device" and t.device in ctx.comp: on_bus.setdefault(ctx.comp[t.device].id, bid)
            elif net.role(t.device) != "bus": todo += net.next_hop(i, far)
    for ld in op.loads:
        if ld["off"] or ld["powered"]: continue
        v, vmin = ld["voltage_V"], ld["v_min"]
        key, bid = f"component:{ld['component']}", on_bus.get(ld["component"])
        if bid and v < 0.5: put(key, "error", f"no supply: {bname(bid)} has no source", f"component:{bid}", f"{bname(bid)} has no source")
        else: put(key, "error", "no supply: no source reaches it" if v < 0.5 else f"{v:.2f} V is below its minimum {vmin:g} V")
    for b in op.buses:
        if b["id"] in unfed:
            put(f"component:{b['id']}", "error", f"no source reaches this bus ({b['loads']} load{'s' * (b['loads'] != 1)} on it)", f"component:{b['id']}",
                f"{bname(b['id'])} has no source")
    errors = sum(x["status"] == "error" for x in items.values())
    trips = sum(p["trips"] for p in op.protective)
    problems = len(groups)
    text = f"{problems} problem{'s' * (problems != 1)}, {trips} trip{'s' * (trips != 1)}" + (f", {len(unfed)} unpowered bus{'es' * (len(unfed) != 1)}" if unfed else "")
    if op.missing: text = "Cannot simulate: " + "; ".join(op.missing)
    elif not op.converged: text = f"The simulation did not converge: {op.message}"
    return dict(ok=op.converged and not op.missing and not unfed and not errors,
                summary=dict(problems=problems, trips=trips, unpowered=len(unfed), text=text, groups=list(groups.values())),
                buses=[dict(id=b["id"], voltage_V=round(b["voltage_V"], 4), nominal_V=b["nominal_V"], powered=b["powered"]) for b in op.buses],
                breakers=[dict(id=p["id"], current_A=round(p["current_A"], 4), rating_A=p["rating_A"], loading=p["loading"], trips=p["trips"])
                          for p in op.protective],
                items=items, assumptions=[f"{a.what}: {a.note} ({a.provenance})" for a in op.assumptions])
