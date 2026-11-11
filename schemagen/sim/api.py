"""Simulation results on the project: operating point per scenario, expectations, and the fault sweep."""
from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..core import tables
from ..core.context import Ctx
from ..core.model import Model
from .build import Assumption, SimModel, build, nominal_v, setting, upstream
from .engine import REF, Linear, Result, SimError, trip_time


@dataclass
class OpPoint:
    scenario: str
    converged: bool
    message: str
    iterations: int
    residual: float
    seconds: float
    nodes: dict[str, float]
    conductors: list[dict[str, Any]]
    protective: list[dict[str, Any]]
    loads: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    buses: list[dict[str, Any]]
    relays: dict[str, bool]
    assumptions: list[Assumption]
    expectations: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # what the circuit lacks to be simulated at all
    unpowered: list[str] = field(default_factory=list)  # buses with loads that no source reaches

    @property
    def ok(self) -> bool:
        """Never a pass while a bus with loads is unpowered, whatever the expectations say."""
        return self.converged and not self.missing and not self.unpowered and all(e["ok"] for e in self.expectations)


def _summarise(sm: SimModel, r: Result, name: str, dt: float) -> OpPoint:
    m, c = sm.ctx.m, sm.circuit
    cond = []
    rmap = {x.name: x.r for x in c.res}
    for i, el in sm.conductor.items():
        cd = m.conductors[i]
        cur = abs(r.i.get(el, 0.0))
        lim = tables.max_rating(cd.awg, "breaker") if cd.awg else None
        cond.append(dict(id=cd.id, label=cd.label, current_A=cur, length_m=sm.length[i][0], length_provenance=sm.length[i][1],
                         drop_V=cur * rmap[el],
                         loading=cur / lim if lim else None))
    prot = []
    for pid, el in sm.protective.items():
        cur = abs(r.i.get(el, 0.0)); rating = sm.rating.get(pid)
        curve, prov = sm.curves[pid]
        t = trip_time(cur / rating, curve) if rating else math.inf
        prot.append(dict(id=pid, current_A=cur, rating_A=rating, loading=cur / rating if rating else None, trip_s=None if math.isinf(t) else t,
                         trips=not math.isinf(t), curve=prov))
    loads = []
    adj: dict[str, list[str]] = {}
    for x in c.res:
        if x.name in c.off or x.kind in ("fault", "coil"): continue
        adj.setdefault(x.a, []).append(x.b); adj.setdefault(x.b, []).append(x.a)
    island = _islands(c, adj)
    fed = {island(s.p) for s in c.src if s.name not in c.off}
    targets = {sm.name((b.raw,)) for b in m.buses if b.function_class != "GND"} | {s.p for s in c.src if s.name not in c.off}
    for ld in sm.loads:
        off = ld.element in c.off
        v = r.v.get(ld.plus, 0.0) - r.v.get(ld.minus, 0.0)
        drop = _drop(r, c._n(ld.plus), adj, targets) - v if not off else 0.0
        loads.append(dict(component=ld.comp, voltage_V=v, current_A=abs(r.i.get(ld.element, 0.0)), v_min=ld.v_min, off=off,
                          powered=(not off) and island(ld.plus) in fed and v >= max(ld.v_min, 0.5), drop_V=drop, provenance=ld.provenance))
    srcs = [dict(element=s.name, component=sm.sources.get(s.name, ""), current_A=r.i.get(s.name, 0.0), limited=s.name in r.limited,
                 off=s.name in c.off) for s in c.src]
    loaded = Counter(island(ld.plus) for ld in sm.loads if ld.element not in c.off)
    buses = []
    for b in m.buses:
        k, gnd = island(sm.name((b.raw,))), b.function_class == "GND"
        on = gnd or k in fed
        # an unfed bus floats: what it reads is the return drop seen through its loads (a few mV, often negative), so 0 V
        buses.append(dict(id=b.id, voltage_V=r.v.get(sm.name((b.raw,)), 0.0) if on else 0.0, nominal_V=None if gnd else nominal_v(b.function_class),
                          powered=on, loads=0 if gnd else loaded[k]))
    return OpPoint(name, r.converged, r.message, r.iterations, r.residual, dt, r.v, cond, prot, loads, srcs, buses, r.relay_states,
                   sm.assumptions, missing=list(sm.missing), unpowered=[b["id"] for b in buses if not b["powered"] and b["loads"]])


def _islands(c: Any, adj: dict[str, list[str]]) -> Any:
    """node -> island id: nodes joined by wires, closed breakers and contacts (not through loads or sources)."""
    seen: dict[str, int] = {}
    for start in adj:
        if start in seen: continue
        seen[start] = len(seen); todo = [start]
        while todo:
            n = todo.pop()
            for y in adj[n]:
                if y not in seen: seen[y] = seen[start]; todo.append(y)
    return lambda n: seen.get(c._n(n), seen.get(n, f"alone:{c._n(n)}"))


def _drop(r: Result, node: str, adj: dict[str, list[str]], targets: set[str]) -> float:
    """Voltage of the nearest bus or source terminal upstream of node (breadth-first over conductors, breakers,
    closed contacts), used to tell the wiring drop to a load."""
    seen, todo = {node}, [node]
    while todo:
        nxt = []
        for n in todo:
            if n in targets and n != node: return r.v.get(n, 0.0)
            for y in adj.get(n, []):
                if y not in seen and y != REF: seen.add(y); nxt.append(y)
        todo = nxt
    return r.v.get(node, 0.0)


def operating_point(m: Model, cfg: Any = None, scenario: dict[str, Any] | None = None, measured: dict[str, float] | None = None,
                    ctx: Ctx | None = None) -> OpPoint:
    t = time.perf_counter()
    sm = build(m, cfg, measured, scenario, ctx)
    try: r = sm.circuit.solve()
    except SimError as e:
        r = Result({}, {}, 0, math.inf, False, str(e))
    op = _summarise(sm, r, str((scenario or {}).get("scenario", "default")), time.perf_counter() - t)
    if scenario: op.expectations = expectations(op, sm, scenario.get("expect") or {})
    if not r.converged and not op.message: op.message = "did not converge"
    return op


def expectations(op: OpPoint, sm: SimModel, exp: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_comp: dict[str, list[dict[str, Any]]] = {}
    for ld in op.loads: by_comp.setdefault(ld["component"], []).append(ld)
    for comp in exp.get("powered", []) or []:
        lds = by_comp.get(str(comp), [])
        ok = bool(lds) and all(x["powered"] for x in lds)
        v = min((x["voltage_V"] for x in lds), default=0.0)
        out.append(dict(kind="powered", target=comp, ok=ok, value=v, detail=f"{comp}: {v:.3f} V" if lds else f"{comp}: no load in the model"))
    for comp, lim in (exp.get("max_drop_V") or {}).items():
        lds = by_comp.get(str(comp), [])
        d = max((x["drop_V"] for x in lds), default=math.inf)
        out.append(dict(kind="max_drop_V", target=comp, ok=d <= float(lim), value=d, detail=f"{comp}: drop {d:.3f} V (max {lim} V)"))
    vol = {b["id"]: b["voltage_V"] for b in op.buses}
    for k, lds in by_comp.items(): vol.setdefault(k, min(x["voltage_V"] for x in lds))
    for k, lim in (exp.get("min_voltage") or {}).items():
        v = vol.get(str(k), -math.inf)
        out.append(dict(kind="min_voltage", target=k, ok=v >= float(lim), value=v, detail=f"{k}: {v:.3f} V (min {lim} V)"))
    if exp.get("no_trip"):
        tr = [p["id"] for p in op.protective if p["trips"]]
        out.append(dict(kind="no_trip", target="*", ok=not tr, value=len(tr), detail="no protective device trips" if not tr else f"trips: {', '.join(tr)}"))
    return out


# ---------------------------------------------------------------- fault sweep
@dataclass
class Sweep:
    rows: list[dict[str, Any]]
    seconds: float
    assumptions: list[Assumption]


def fault_sweep(m: Model, cfg: Any = None, scenario: dict[str, Any] | None = None, measured: dict[str, float] | None = None,
                ctx: Ctx | None = None, limit: int | None = None) -> Sweep:
    """Short every powered node to ground, one at a time: prospective current, the device that trips first and when,
    wire survival (I^2 t against the insulation limit), interrupt rating and selectivity."""
    t0 = time.perf_counter()
    d = tables.table("sim", cfg)
    ctx = ctx or Ctx(m, cfg)
    sm = build(m, cfg, measured, scenario, ctx)
    c = sm.circuit
    base = c.solve()
    states = dict(base.relay_states)
    for rl in c.relays:  # hold the relays where they settled: a short is faster than a relay
        for n in rl.no: (c.off.discard if states.get(rl.name) else c.off.add)(n)
        for n in rl.nc: (c.off.add if states.get(rl.name) else c.off.discard)(n)
    c.relays = []
    ups = upstream(sm)
    rf = float(d["fault_resistance_ohm"])
    lin = Linear(c, base)
    gnd_nodes = ground_nodes(sm)
    nodes = [n for n in lin.names if base.v.get(n, 0.0) > 0.5 and n not in gnd_nodes]
    if limit: nodes = nodes[:limit]
    import numpy as np
    ix = lin.idx
    def vec(names: list[str]) -> Any:
        return np.array([ix.get(x, -1) for x in names])
    res = {x.name: x for x in c.res}
    pel = [(pid, res[el]) for pid, el in sm.protective.items() if el in res and el not in c.off]
    pa, pb = vec([x.a for _, x in pel]), vec([x.b for _, x in pel]); pr = np.array([x.r for _, x in pel])
    cel = [(i, res[el]) for i, el in sm.conductor.items() if el in res]
    ca, cb = vec([x.a for _, x in cel]), vec([x.b for _, x in cel]); cr = np.array([x.r for _, x in cel])
    climit = np.array([tables.i2t_limit(a, cfg) if (a := m.conductors[i].awg) is not None else np.inf for i, _ in cel])
    rows = []
    for n in nodes:
        xf, limited = lin.short(n, rf)
        v = np.append(xf, 0.0)  # index -1 -> the reference
        i_f = float(xf[ix[n]]) / rf
        ip = np.abs((v[pa] - v[pb]) / pr) if len(pel) else np.zeros(0)
        trips = []
        for (pid, _), cur in zip(pel, ip):
            rating = sm.rating.get(pid)
            if not rating or cur < 1e-6: continue
            tt = trip_time(float(cur) / rating, sm.curves[pid][0])
            if not math.isinf(tt): trips.append((tt, pid, float(cur)))
        trips.sort()
        row: dict[str, Any] = dict(node=n, voltage_before_V=base.v.get(n, 0.0), fault_current_A=i_f, limited_sources=sorted(limited))
        if trips:
            tt, pid, cur = trips[0]
            ii, iprov = sm.interrupt[pid]
            carrying = {p for (p, _), x in zip(pel, ip) if x > 0.1 * cur}  # devices the fault current flows through
            downstream = sorted(p for p in ups.get(pid, set()) if p in carrying)
            ties = [p for t2, p, _ in trips[1:] if abs(t2 - tt) < 1e-9]
            icw = np.abs((v[ca] - v[cb]) / cr)
            margin = climit / np.maximum(icw ** 2 * tt, 1e-30)
            k = int(np.argmin(np.where(icw > 1.0, margin, np.inf))) if len(icw) else 0
            worst = (float(margin[k]), m.conductors[cel[k][0]].label) if len(icw) and icw[k] > 1.0 else None
            row.update(first_trip=pid, trip_s=tt, trip_current_A=cur, curve=sm.curves[pid][1], interrupt_A=ii, interrupt_provenance=iprov,
                       within_interrupt=cur <= ii, selective=not downstream and not ties, downstream_not_first=downstream,
                       simultaneous=ties, worst_wire=worst[1] if worst else "", wire_survives=(worst[0] >= 1.0) if worst else True,
                       i2t_margin=worst[0] if worst else None)
        else:
            row.update(first_trip="", trip_s=None, within_interrupt=True, selective=True, wire_survives=None,
                       note="no protective device trips: the fault is not cleared (unprotected section or current-limited source)")
        rows.append(row)
    asm = sm.assumptions + [Assumption("fault", "assumed", f"bolted short {rf} ohm to the reference, relays held in their settled state, "
                                                         "loads as their operating-point resistance (IEC 60909 neglects load current)"),
                            Assumption("wire survival", "datasheet", f"adiabatic I²t <= (k A)², {tables.table('wire', cfg)['source_k']}, "
                                                                     f"k = {tables.table('wire', cfg)['k_insulation']}")]
    return Sweep(rows, time.perf_counter() - t0, asm)


def ground_nodes(sm: SimModel) -> set[str]:
    """Circuit nodes on ground / return nets (a short there is not a fault)."""
    ctx = sm.ctx
    out = {REF}
    for nt in ctx.net.nets():
        if ctx.net_kind(nt.conductors) == "GND": out |= {sm.circuit._n(sm.name(k)) for k in nt.nodes}
    return out


def _parents(ups: dict[str, set[str]], pid: str) -> list[str]:
    return [a for a, bs in ups.items() if pid in bs]


def scenario_name(sc: dict[str, Any]) -> str:
    return str(sc.get("scenario", "scenario"))


__all__ = ["operating_point", "fault_sweep", "OpPoint", "Sweep", "setting"]
