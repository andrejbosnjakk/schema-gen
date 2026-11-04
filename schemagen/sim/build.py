"""Model -> Circuit. Every parameter is marked measured / datasheet / design / estimated / assumed, and the circuit
keeps that record so every result can list the assumptions it rests on.

Nodes are the net nodes (splice, bus, harness pin, device terminal). Each conductor is a resistor: copper (ohm/m by
AWG x length x temperature factor) plus contact resistance at each pin. Breakers and fuses are small resistances,
switch and relay contacts are resistors present only when closed, relay coils are resistors that close their
contacts at pick-up. Batteries are a voltage behind their internal resistance, DC/DC converters and regulated
outputs are current-limited sources, loads come from part data (or, marked assumed, from a conductor's current).
"""
from __future__ import annotations

import fnmatch
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..core import tables
from ..core.context import Ctx
from ..core.model import Component, Model, Part, Terminal
from ..core.net import NodeKey
from .engine import REF, Circuit, Relay


@dataclass
class Assumption:
    what: str
    provenance: str     # measured, datasheet, design, estimated, assumed
    note: str = ""


@dataclass
class LoadInfo:
    comp: str
    element: str
    plus: str
    minus: str
    v_min: float
    model: str
    provenance: str


@dataclass
class SimModel:
    circuit: Circuit
    ctx: Ctx
    ref_node: NodeKey | None
    conductor: dict[int, str] = field(default_factory=dict)          # conductor index -> resistor name
    length: dict[int, tuple[float, str]] = field(default_factory=dict)
    protective: dict[str, str] = field(default_factory=dict)          # protective id -> resistor name
    loads: list[LoadInfo] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)             # source element -> component id
    assumptions: list[Assumption] = field(default_factory=list)
    curves: dict[str, tuple[list[tuple[float, float]], str]] = field(default_factory=dict)  # protective id -> (curve, provenance)
    rating: dict[str, float] = field(default_factory=dict)
    interrupt: dict[str, tuple[float, str]] = field(default_factory=dict)

    def name(self, key: NodeKey) -> str:
        return REF if key == self.ref_node else "|".join(key)


def _matches(comp: Component, key: str) -> bool:
    return comp.id == key or fnmatch.fnmatch(comp.id, key) or fnmatch.fnmatch(comp.raw, key)


def setting(comp: Component, sets: dict[str, Any]) -> str | None:
    for k, v in sets.items():
        if _matches(comp, str(k)): return str(v).lower()
    return None


def _term(spec: str, raw: str) -> Terminal:
    con, _, pin = spec.partition(".")
    return Terminal(device=raw, connector=con, pin=pin)


def build(m: Model, cfg: Any = None, measured: dict[str, float] | None = None, scenario: dict[str, Any] | None = None,
          ctx: Ctx | None = None) -> SimModel:
    sc = scenario or {}
    sets: dict[str, Any] = dict(sc.get("set") or {})
    faults: list[dict[str, Any]] = list(sc.get("faults") or [])
    d = tables.table("sim", cfg)
    ctx = ctx or Ctx(m, cfg)
    net, conds = ctx.net, m.conductors
    measured = measured or {}
    c = Circuit(gmin=float(d["gmin_S"]))
    used = ctx.by_terminal
    # reference node: a battery's negative terminal, else a ground bus, else the first ground pin
    ref: NodeKey | None = None
    for comp in m.components:
        p = ctx.part_of(comp.raw)
        if p and p.kind == "battery":
            for key in used:
                if key[0] == comp.raw and ctx.pin_type(Terminal(device=key[0], connector=key[1], pin=key[2])) == "ground":
                    ref = net.node_of(Terminal(device=key[0], connector=key[1], pin=key[2])); break
        if ref: break
    if ref is None:
        b = next((x for x in m.buses if x.function_class == "GND"), None)
        if b: ref = (b.raw,)
    sm = SimModel(c, ctx, ref)
    if ref is None: sm.assumptions.append(Assumption("reference node", "assumed", "no battery negative or ground bus: node voltages float"))
    N = sm.name
    T = float(d["temperature_C"])
    rc_def = float(d["contact_resistance_ohm"])
    rc_by = sorted((int(k), float(v)) for k, v in (d.get("contact_resistance_by_awg") or {}).items())

    def rc_for(awg: int) -> float:
        heavier = [v for g, v in rc_by if awg <= g]
        return heavier[0] if heavier else rc_def
    opened = {str(f.get("open")) for f in faults if f.get("open")}
    prov: Counter[str] = Counter()
    gauge_assumed = contact_assumed = 0
    zones = {z.id: z for z in m.zones}
    for i, cd in enumerate(conds):
        if cd.label in opened or cd.id in opened: continue
        if cd.label in measured: ln, pv = measured[cd.label], "measured"
        elif cd.length_m is not None: ln, pv = cd.length_m, "design"
        else:
            za, zb = (ctx.comp[t.device].zone if t.device in ctx.comp else "" for t in (cd.from_, cd.to))
            xa, xb = (zones[z].xy if z in zones else None for z in (za, zb))
            if xa and xb and za != zb:
                ln, pv = abs(xa[0] - xb[0]) + abs(xa[1] - xb[1]) + float(d["service_loop_m"]), "estimated"
            else: ln, pv = float(d["default_length_m"]), "assumed"
        prov[pv] += 1
        sm.length[i] = (ln, pv)
        awg = cd.awg
        if awg is None: awg, gauge_assumed = 22, gauge_assumed + 1
        r = tables.ohm_per_m(awg, T, cfg) * ln
        for t in (cd.from_, cd.to):
            tc = ctx.comp.get(t.device)
            if tc and (t.pin or tc.kind == "harness"):
                pdef = ctx.pin(t)
                if pdef and pdef.r_contact is not None: r += pdef.r_contact
                else: r += rc_for(awg); contact_assumed += 1
        name = f"c{i}"
        c.r(name, N(net.node(i, 1)), N(net.node(i, 2)), r, "wire", f"conductor:{cd.id}")
        sm.conductor[i] = name
    sm.assumptions.append(Assumption("conductor lengths", "mixed", ", ".join(f"{n} {k}" for k, n in sorted(prov.items()))
                                     + f" (default {d['default_length_m']} m, zone estimates + {d['service_loop_m']} m service loop)"))
    sm.assumptions.append(Assumption("wire resistance", "datasheet", f"copper ohm/m by AWG at {T:g} °C, {tables.table('wire', cfg)['source']}"))
    if gauge_assumed: sm.assumptions.append(Assumption("gauge", "assumed", f"{gauge_assumed} conductor(s) without a gauge taken as 22 AWG"))
    if contact_assumed: sm.assumptions.append(Assumption("contact resistance", "assumed",
                                                         f"{contact_assumed} contact(s) by gauge, {rc_by} ohm, else {rc_def} ohm"))

    by_dev: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for key in used: by_dev[key[0]].append(key)

    def terms(comp: Component, types: tuple[str, ...]) -> list[Terminal]:
        out = []
        for key in by_dev.get(comp.raw, []):
            t = Terminal(device=key[0], connector=key[1], pin=key[2])
            if ctx.pin_type(t) in types: out.append(t)
        return sorted(out, key=lambda t: t.key())

    pds = {p.id: p for p in m.protective_devices}
    counts: Counter[str] = Counter()
    for comp in m.components:
        p = ctx.part_of(comp.raw)
        st = setting(comp, sets)
        if comp.kind in ("breaker", "fuse"):
            ins, outs = terms(comp, ("power_in",)), terms(comp, ("power_out",))
            pd = pds.get(comp.id)
            curve = list(p.trip_curve) if p and p.trip_curve else [tuple(x) for x in d["generic_trip_curve"]]
            sm.curves[comp.id] = ([(float(a), float(b)) for a, b in curve], "datasheet" if p and p.trip_curve else "assumed")
            if pd and pd.rating_a: sm.rating[comp.id] = pd.rating_a
            ii = (pd.i_interrupt if pd and pd.i_interrupt else None) or (p.i_interrupt if p and p.i_interrupt else None)
            sm.interrupt[comp.id] = (float(ii), "design" if pd and pd.i_interrupt else "datasheet") if ii else (float(d["i_interrupt_A"]), "assumed")
            if not ins or not outs: continue
            if st in ("open", "off", "tripped"): continue
            rr = p.r_closed if p and p.r_closed is not None else float(d["breaker_resistance_ohm"])
            if not (p and p.r_closed is not None): counts["breaker resistance"] += 1
            nm = f"pd:{comp.id}"
            c.r(nm, N(net.node_of(ins[0])), N(net.node_of(outs[0])), rr, "breaker", f"protective:{comp.id}")
            for extra_t in ins[1:]: c.merge(N(net.node_of(extra_t)), N(net.node_of(ins[0])))
            for extra_t in outs[1:]: c.merge(N(net.node_of(extra_t)), N(net.node_of(outs[0])))
            sm.protective[comp.id] = nm
        elif p and p.kind == "switch":
            closed = st not in ("open", "off")
            if st is None: counts["switch state (closed)"] += 1
            for k, ct in enumerate(p.contacts):
                if ct.a and ct.b and closed:
                    c.r(f"sw:{comp.id}:{k}", N(net.node_of(_term(ct.a, comp.raw))), N(net.node_of(_term(ct.b, comp.raw))),
                        float(d["switch_resistance_ohm"]), "switch", f"component:{comp.id}")
        elif p and p.kind == "relay":
            no: list[str] = []
            nc: list[str] = []
            for k, ct in enumerate(p.contacts):
                for kind, other, lst in (("no", ct.no, no), ("nc", ct.nc, nc)):
                    if ct.com and other:
                        nm = f"rl:{comp.id}:{k}{kind}"
                        c.r(nm, N(net.node_of(_term(ct.com, comp.raw))), N(net.node_of(_term(other, comp.raw))),
                            float(d["switch_resistance_ohm"]), "switch", f"component:{comp.id}")
                        lst.append(nm)
            if p.coil:
                a2 = _term(p.coil.a2, comp.raw)
                cn = f"coil:{comp.id}"
                c.r(cn, N(net.node_of(_term(p.coil.a1, comp.raw))), N(net.node_of(a2)) if a2.key() in used else REF, p.coil.r, "coil",
                    f"component:{comp.id}")
                if st in ("energized", "energised", "on"): c.off.update(nc)
                elif st in ("de-energized", "de-energised", "off"): c.off.update(no)
                else: c.relays.append(Relay(comp.id, cn, p.coil.v_pickup, p.coil.v_dropout, no, nc))
        if p and st not in ("off", "failed", "fail") and comp.raw in by_dev:
            _sources_and_loads(sm, comp, p, terms, N, used)
        elif p is None and comp.kind in ("device", "load", "sensor", "controller") and st not in ("off",):
            _assumed_loads(sm, comp, N)
    for what, cnt in counts.items(): sm.assumptions.append(Assumption(what, "assumed", f"{cnt} element(s)"))
    for f in faults:  # shorts to ground
        if f.get("short") is None: continue
        fk = node_ref(sm, str(f["short"]))
        if fk is None: raise ValueError(f"fault: no node '{f['short']}'")
        c.r(f"fault:{f['short']}", N(fk), REF, float(f.get("r", d["fault_resistance_ohm"])), "fault")
    for f in faults:
        if f.get("fail"):
            for s, comp_id in sm.sources.items():
                if comp_id == f["fail"] or fnmatch.fnmatch(comp_id, str(f["fail"])): c.off.add(s)
    for ld in sm.loads:
        lc = ctx.comp_by_id.get(ld.comp)
        if lc and setting(lc, sets) == "off": c.off.add(ld.element)
    return sm


def _sources_and_loads(sm: SimModel, comp: Component, p: Part, terms: Any, N: Any, used: Any) -> None:
    c, net = sm.circuit, sm.ctx.net
    gnd = terms(comp, ("ground",))
    minus = N(net.node_of(gnd[0])) if gnd else REF
    for g in gnd[1:]: c.merge(N(net.node_of(g)), minus)
    minus = c._n(minus)
    if not gnd and (p.load or p.source or p.supply_out):
        sm.assumptions.append(Assumption(f"{comp.id} return", "assumed", "no ground pin wired: returns through the reference (chassis)"))
    if p.kind == "battery" and p.source and p.source.v_oc is not None:
        plus = terms(comp, ("power_out",))
        if plus:
            nm = f"src:{comp.id}"
            c.vsrc(nm, N(net.node_of(plus[0])), minus, p.source.v_oc, p.source.r_int or 0.0, ref=f"component:{comp.id}")
            sm.sources[nm] = comp.id
            sm.assumptions.append(Assumption(f"{comp.id} battery", p.source.provenance, f"{p.source.v_oc} V open circuit, {p.source.r_int} ohm"))
    if p.kind == "dcdc" and p.source and p.source.v_out is not None:
        outs, ins = terms(comp, ("power_out",)), terms(comp, ("power_in",))
        if outs:
            nm = f"src:{comp.id}"
            c.vsrc(nm, N(net.node_of(outs[0])), minus, p.source.v_out, p.source.r_out or 1e-3, p.source.i_limit, f"component:{comp.id}")
            sm.sources[nm] = comp.id
            if ins:
                ld = c.load(f"in:{comp.id}", N(net.node_of(ins[0])), minus, "constant_power", 0.0, 0.0, 1.0, f"component:{comp.id}")
                ld.dcdc_of, ld.efficiency = nm, p.source.efficiency or 1.0
            sm.assumptions.append(Assumption(f"{comp.id} DC/DC", p.source.provenance,
                                             f"{p.source.v_out} V, limit {p.source.i_limit} A, efficiency {p.source.efficiency}"))
    if p.supply_out and p.supply_out.v_out is not None:
        for k, t in enumerate(terms(comp, ("power_out",))):
            nm = f"reg:{comp.id}:{k}"
            c.vsrc(nm, N(net.node_of(t)), minus, p.supply_out.v_out, p.supply_out.r_out or 0.05, p.supply_out.i_limit, f"component:{comp.id}")
            sm.sources[nm] = comp.id
    if p.load:
        L = p.load
        plus = terms(comp, ("power_in",))
        if not plus: return
        pn = N(net.node_of(plus[0]))
        for t in plus[1:]: c.merge(N(net.node_of(t)), pn)
        pn = c._n(pn)
        if L.model == "constant_power": val = L.p_w or 0.0
        elif L.model == "constant_current": val = L.i_a or 0.0
        else: val = L.r_ohm or ((L.v_nom or 14.0) ** 2 / L.p_w if L.p_w else 1e6)
        nm = f"load:{comp.id}"
        c.load(nm, pn, minus, L.model, val, L.v_min, None, f"component:{comp.id}")
        sm.loads.append(LoadInfo(comp.id, nm, pn, minus, L.v_min, L.model, L.provenance))


def _assumed_loads(sm: SimModel, comp: Component, N: Any) -> None:
    """A device without part data: constant-current loads from its conductors' `current` field (marked assumed)."""
    ctx, c, net = sm.ctx, sm.circuit, sm.ctx.net
    gnd = [(i, e) for i, e in net.by_dev[comp.raw] if ctx.m.conductors[i].kind == "GND"]
    minus = N(net.node(*gnd[0])) if gnd else REF
    seen: set[str] = set()
    for i, e in net.by_dev[comp.raw]:
        cd = ctx.m.conductors[i]
        if cd.kind == "GND" or not cd.current_a: continue
        pn = N(net.node(i, e))
        if pn in seen: continue
        seen.add(pn)
        nm = f"load:{comp.id}:{len(seen)}"
        c.load(nm, pn, minus, "constant_current", cd.current_a, 0.0, 1.0, f"component:{comp.id}")
        sm.loads.append(LoadInfo(comp.id, nm, pn, minus, 0.0, "constant_current", "assumed"))
        sm.assumptions.append(Assumption(f"{comp.id} load", "assumed", f"{cd.current_a} A constant current from {cd.label}'s current field"))


def node_ref(sm: SimModel, ref: str) -> NodeKey | None:
    """Node for a fault reference: a conductor label or id (its 'to' end), a component id (splice / bus), or COMP/CONN/PIN."""
    ctx = sm.ctx
    for i, cd in enumerate(ctx.m.conductors):
        if ref in (cd.label, cd.id): return ctx.net.node(i, 2)
    if "/" in ref:
        cid, con, pin = (ref.split("/") + ["", ""])[:3]
        comp = ctx.comp_by_id.get(cid)
        if comp: return ctx.net.node_of(Terminal(device=comp.raw, connector=con, pin=pin))
    comp = ctx.comp_by_id.get(ref)
    if comp and comp.kind in ("splice", "bus"): return (comp.raw,)
    return None


def upstream(sm: SimModel) -> dict[str, set[str]]:
    """Protective device -> the protective devices it feeds (directly or through buses), for selectivity."""
    ctx, net = sm.ctx, sm.ctx.net
    out: dict[str, set[str]] = defaultdict(set)
    line_of: dict[NodeKey, str] = {}
    for comp in ctx.m.components:
        if comp.kind in ("breaker", "fuse"):
            for key in ctx.by_terminal:
                if key[0] == comp.raw and ctx.pin_type(Terminal(device=key[0], connector=key[1], pin=key[2])) == "power_in":
                    line_of[net.node_of(Terminal(device=key[0], connector=key[1], pin=key[2]))] = comp.id
    for pid in ctx.protected_by:
        comp = ctx.comp_by_id[pid]
        starts = [net.node(i, e) for i, e in net.by_dev[comp.raw] if ctx.pin_type(ctx.m.conductors[i].end(e)) == "power_out"]
        seen: set[NodeKey] = set()
        todo = list(starts)
        while todo:
            n = todo.pop()
            if n in seen: continue
            seen.add(n)
            if n in line_of and line_of[n] != pid: out[pid].add(line_of[n]); continue
            for i, e in net.at[n]:
                far = ctx.m.conductors[i].end(3 - e)
                todo.append(net.node(i, 3 - e))
                for peer in ctx.contact_peers(far): todo.append(net.node_of(peer))
    # transitive closure
    changed = True
    while changed:
        changed = False
        for a in list(out):
            for b in list(out[a]):
                new = out.get(b, set()) - out[a]
                if new: out[a] |= new; changed = True
    return out
