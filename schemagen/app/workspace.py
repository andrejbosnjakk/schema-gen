"""The 1.0 main screen in one call (docs/api.md, Workspace) and the popup cards: components in power-flow ranks, wires
bundled per component pair through splices, issues with short titles, zones, positions and the app's sources."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any

from .. import __version__
from ..core.model import Component
from ..core.rules import RULES
from ..exporters.palette import HEX

SEV = {"error": 0, "warning": 1, "info": 2}
RANK = {"battery": 0, "dcdc": 0, "breaker": 1, "fuse": 1, "switch": 1, "relay": 1, "bus": 2, "harness": 3}


def rank(st: Any, c: Component) -> int:
    """Power-flow column: 0 sources, 1 protection and switching, 2 buses, 3 harness connectors, 4 loads."""
    if c.kind in RANK: return RANK[c.kind]
    return 0 if st.ctx.is_source(c) else 4


def _worst(a: str, b: str) -> str:
    return min((x for x in (a, b) if x), key=lambda x: SEV[x], default="")


def severities(st: Any) -> tuple[dict[str, str], dict[str, str]]:
    """Worst issue severity per component id and per conductor id."""
    comp: dict[str, str] = {}
    cond: dict[str, str] = {}
    for iss in st.issues:
        for o in iss.objects:
            typ, _, rest = o.partition(":")
            if typ == "conductor": cond[rest] = _worst(cond.get(rest, ""), iss.severity)
            elif typ in ("component", "connector", "protective", "pin"):
                cid = rest.split("/")[0]; comp[cid] = _worst(comp.get(cid, ""), iss.severity)
    return comp, cond


def issue(k: int, i: Any) -> dict[str, Any]:
    r = RULES.get(i.rule)
    return dict(k=k, rule=i.rule, severity=i.severity, title=r.title if r else i.rule.replace("-", " ").capitalize(), message=i.message,
                fix=i.fix, objects=i.objects)


def ends(st: Any, rk: dict[str, int]) -> list[tuple[str, str]]:
    """(a, b) component ids at the two ends of every conductor, with splices folded: the wires of a splice cluster run
    from its upstream-most end (lowest rank) to each other end."""
    conds, net = st.m.conductors, st.ctx.net
    n = len(conds)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for s in st.m.splices:
        at = net.at.get((s.raw,), [])
        for i, _ in at[1:]: parent[find(i)] = find(at[0][0])
    splice = {s.raw for s in st.m.splices}
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n): groups[find(i)].append(i)
    out: list[tuple[str, str]] = [("", "")] * n
    for idx in groups.values():
        comps = sorted({st.cid(conds[i].end(e).device) for i in idx for e in (1, 2) if conds[i].end(e).device not in splice},
                       key=lambda c: (rk.get(c, 4), c))
        hub = comps[0] if comps else ""
        for i in idx:
            a, b = (st.cid(conds[i].end(e).device) if conds[i].end(e).device not in splice else "" for e in (1, 2))
            if a and b: out[i] = (a, b); continue
            x = a or b or hub
            other = hub if x != hub else (comps[1] if len(comps) > 1 else hub)
            out[i] = (x, other) if a or not b else (other, x)
    return out


def wire_cls(c: Any) -> str:
    return c.can or c.kind


def workspace(st: Any) -> dict[str, Any]:
    """Everything the main screen needs (cached until the next reload)."""
    if st._ws is not None: return dict(st._ws, positions=positions(st))
    m, ctx = st.m, st.ctx
    rk = {c.id: rank(st, c) for c in m.components}
    csev, wsev = severities(st)
    pins: Counter[str] = Counter()
    for (dev, con, pin), _ in ctx.by_terminal.items():
        c = ctx.comp.get(dev)
        if c: pins[c.id] += 1
    hpins = {x.id: x.pin_count for x in m.connectors}
    subs: dict[str, Counter[str]] = defaultdict(Counter)
    for cd in m.conductors:
        if cd.subsystem:
            for e in (1, 2): subs[st.cid(cd.end(e).device)][cd.subsystem] += 1
    sub_of = {k: v.most_common(1)[0][0] for k, v in subs.items()}
    nodes = [dict(id=c.id, name=c.name or c.id, kind=c.kind, zone=c.zone, subsystem=sub_of.get(c.id, ""), pins=hpins.get(c.id) or pins[c.id],
                  rank=rk[c.id], sev=csev.get(c.id, "")) for c in m.components if c.kind != "splice"]
    ab = ends(st, rk)
    wires, bundles = [], defaultdict(list)
    for i, c in enumerate(m.conductors):
        a, b = ab[i]
        wires.append(dict(id=c.id, label=c.label, name=c.name, **{"from": st.pin_text(c.from_), "to": st.pin_text(c.to)}, a=a, b=b,
                          gauge=c.gauge, voltage=c.bus or (c.kind if re.search(r"\d\s*V", c.kind) else ""), current=c.current_a, cls=wire_cls(c),
                          hex=HEX.get(c.colour_code[:2], "#888"), length=c.length_m, harness=c.harness, protection=c.protection,
                          status=c.status, notes=c.notes, sev=wsev.get(c.id, "")))
        if a and b and a != b:
            key = (a, b) if (rk.get(a, 4), a) <= (rk.get(b, 4), b) else (b, a)
            bundles[key].append(i)
    edges = []
    for (a, b), idx in sorted(bundles.items()):
        cnt = Counter(wire_cls(m.conductors[i]) for i in idx)
        edges.append(dict(id=f"{a}~{b}", a=a, b=b, wires=[m.conductors[i].id for i in idx], cls=[k for k, _ in cnt.most_common()],
                          label=", ".join(f"{v} × {k}" for k, v in cnt.most_common())))
    for s in st.sources:
        nodes.append(dict(id=s["id"], name=s.get("name") or s["id"], kind=s.get("type", "battery"), zone="", subsystem="", pins=0, rank=0, sev=""))
        edges.append(dict(id=f"{s['id']}~{s['attach']}", a=s["id"], b=s["attach"], wires=[], cls=[], label=f"{float(s['nominal_V']):g} V"))
    by = "subsystem" if any(n["subsystem"] for n in nodes) else "zone"
    groups: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        if n[by]: groups[n[by]].append(n["id"])
    zname = {z.id: z.name for z in m.zones}
    st._ws = dict(
        project=dict(name=st.cfg.root.name, root=str(st.cfg.root), version=__version__, warnings=st.L.warnings),
        components=nodes, edges=edges, conductors=wires, issues=[issue(k, i) for k, i in enumerate(st.issues)],
        zones=[dict(id=g, name=zname.get(g, g) if by == "zone" else g, members=v) for g, v in sorted(groups.items())],
        sources=st.sources, palette={k: HEX.get(v[:2], "#888") for k, v in st.cfg.colours.items()})
    return dict(st._ws, positions=positions(st))


# ---------------------------------------------------------------- positions (view state, not wire data)
def positions(st: Any) -> dict[str, list[float]]:
    try: d = json.loads((st.cfg.root / "layout.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    pos = d.get("positions", {}) if isinstance(d, dict) else {}
    return {str(k): [float(v[0]), float(v[1])] for k, v in pos.items() if isinstance(v, (list, tuple)) and len(v) == 2}


def save_positions(st: Any, new: dict[str, Any]) -> None:
    pos = positions(st)
    for k, v in new.items():
        if v is None: pos.pop(str(k), None); continue
        if not (isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)):
            raise ValueError(f"position of {k} must be [x, y]")
        pos[str(k)] = [float(v[0]), float(v[1])]
    p = st.cfg.root / "layout.json"
    tmp = p.with_suffix(".json.part")
    tmp.write_text(json.dumps({"positions": pos}, indent=1) + "\n", encoding="utf-8"); tmp.replace(p)


# ---------------------------------------------------------------- cards
def _issues_for(st: Any, refs: set[str], comp: str = "") -> list[dict[str, Any]]:
    return [issue(k, i) for k, i in enumerate(st.issues)
            if any(o in refs or (comp and o.startswith(f"pin:{comp}/")) for o in i.objects)]


def _natural(s: str) -> list[Any]:
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def component_card(st: Any, cid: str) -> dict[str, Any] | None:
    ctx, conds = st.ctx, st.m.conductors
    c = ctx.comp_by_id.get(cid)
    if c is None: return None
    pd = next((p for p in st.m.protective_devices if p.id == cid), None)
    by_con: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i, e in ctx.net.by_dev[c.raw]:
        cd, t = conds[i], conds[i].end(e)
        d = ctx.pin(t)
        other = "; ".join(sorted({st.pin_text(x) for x, _ in ctx.net.reach(i, 3 - e)}))
        by_con[t.connector].append(dict(pin=t.pin, wire=cd.id, wire_label=cd.label, name=d.name if d and d.name else "", other=other, gauge=cd.gauge))
    connectors = [dict(id=k, pins=sorted(v, key=lambda p: (_natural(p["pin"]), p["wire_label"]))) for k, v in sorted(by_con.items(), key=lambda kv: _natural(kv[0]))]
    out = dict(id=c.id, name=c.name or c.id, kind=c.kind, location=c.zone, rating_A=pd.rating_a if pd else None, connectors=connectors,
               issues=_issues_for(st, {f"component:{cid}", f"connector:{cid}", f"protective:{cid}"}, cid))
    sim = (st.overlay or {}).get("items", {}).get(f"component:{cid}")
    if sim: out["sim"] = sim
    return out


def wire_card(st: Any, wid: str) -> dict[str, Any] | None:
    c = next((x for x in st.m.conductors if x.id == wid), None)
    if c is None: return None
    out = dict(id=c.id, label=c.label, name=c.name, **{"from": st.pin_text(c.from_), "to": st.pin_text(c.to)}, gauge=c.gauge,
               voltage=c.bus or "", current=c.current_a, length=c.length_m, colour=c.colour_code, hex=HEX.get(c.colour_code[:2], "#888"),
               harness=c.harness, protection=c.protection, status=c.status, notes=c.notes, issues=_issues_for(st, {f"conductor:{wid}"}))
    sim = (st.overlay or {}).get("items", {}).get(f"conductor:{wid}")
    if sim: out["sim"] = sim
    return out
