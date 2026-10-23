"""WireViz harness drawing for one harness connector.

Scope: every conductor with one end on the connector. Near half (near_words in schemagen.yml) on the left, far half on the
right, the connector with all its pins (spares shown) in the middle. Far ends are devices (pin tables, card pin
names), or splices/buses drawn as simple boxes carrying the "continues at" note. Wires are bundled per
(side, far item, gauge, length); a CAN H/L pair becomes one shielded twisted-pair bundle.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .checks import harness_checks


@dataclass
class Drawing:
    harness: str          # requested harness id, e.g. X-BH
    code: str             # short code of the harness connector, e.g. X-BH
    designator: str       # connector designator in the drawing
    name: str             # readable connector name
    doc: dict             # WireViz YAML document
    ends: list            # [(wire, harness end, far end, 'near'|'far')]
    checks: list = field(default_factory=list)


def clean_func(f, n=34):
    f = re.sub(r"\s*\([^)]*\)", "", str(f)); f = re.split(r"[;,]|→| — ", f)[0].strip()
    return f[:n].rstrip()


def pv(p):
    """WireViz turns numeric pin references into ints, so pin ids must match that."""
    return int(p) if str(p).isdigit() else p


def safe(t):
    """Graphviz HTML labels: WireViz 0.4.1 does not escape everything."""
    return str(t).replace("&", "and").replace("<", "‹").replace(">", "›").replace('"', "'")


def pin_order(p):
    return int(p) if str(p).isdigit() else 999


def build(pr, net, cards, H, lengths=None):
    lengths = lengths or {}
    rows = []
    for w in pr.wires:
        for e in (1, 2):
            if w[f"p{e}"].startswith(H) and pr.harness(w[f"p{e}"]):
                rows.append((w, e)); break
    if not rows: raise SystemExit(f"no wires on {H}")
    raw = rows[0][0][f"p{rows[0][1]}"]
    hname, hcode, farname = pr.harness(raw)[:3]
    X = hcode if hcode.startswith("X-") else "X-" + hcode
    ends = [(w, e, 3 - e, "near" if pr.near(w[f"p{e}c"]) else "far") for w, e in rows]

    # ---- harness connector: both halves as one connector, all shell pins
    pins, halves = defaultdict(lambda: {"near": [], "far": []}), {"near": set(), "far": set()}
    for w, e, f, sd in ends:
        halves[sd].add(w[f"p{e}c"]); pins[w[f"p{e}p"]][sd].append(w)
    m = re.search(r"D-SUB (\d+)", raw)
    npins = int(m.group(1)) if m else max([int(p) for p in pins if p.isdigit()] or [0])
    pinlist = [str(i) for i in range(1, npins + 1)] + sorted(p for p in pins if not p.isdigit())
    plabels = []
    for p in pinlist:
        ws = pins[p]["near"] + pins[p]["far"]
        names = [n for n in (clean_func(w["func"]) for w in ws) if n] or [clean_func(w["name"]) for w in ws]
        plabels.append(safe(min(names, key=len)) if ws else "spare")
    near_half = " / ".join(sorted(halves["near"])) or "near half"
    far_half = " / ".join(sorted(halves["far"])) or "far half"
    connectors = {X: dict(type=safe(hname), subtype=safe(f"left: {near_half} | right: {far_half}"),
                          pins=[pv(p) for p in pinlist], pinlabels=plabels,
                          notes=safe(f"{raw}. Left = {near_half}, right = {far_half} ({farname} side)."))}

    # ---- far-end items
    des = {}

    def designator(dev):
        if dev in des: return des[dev]
        d = pr.code(dev) or re.sub(r"\W+", "_", pr.strip(dev))[:24].strip("_")
        if d in des.values() or d == X: d = d + "_" + re.sub(r"\W+", "_", pr.strip(dev).split(" ", 1)[-1])[:12]
        des[dev] = d
        return d

    conns = defaultdict(set)
    for w, e, f, sd in ends:
        designator(w[f"p{f}"]); conns[w[f"p{f}"]].add(w[f"p{f}c"])
    devpins, pid_of = defaultdict(dict), {}
    for w, e, f, sd in ends:
        dev, c, p = w[f"p{f}"], w[f"p{f}c"], w[f"p{f}p"]
        if pr.role(dev) in ("splice", "bus"): continue
        if not p: pid = pr.strip(c) or c or "terminal"
        elif len(pr.dev_conns[dev]) > 1: pid = f"{pr.strip(c)} {p}"
        else: pid = p
        lab = cards.pin(pr.code(dev), c, p) or clean_func(w["func"], 30) or clean_func(w["name"], 30)
        devpins[dev].setdefault(pid, lab)
        pid_of[w["id"]] = pid

    # ---- "continues at" notes
    notes = defaultdict(list)
    for w, e, f, sd in ends:
        nxt = net.next_hop(w, f)
        w["_cont"] = ""
        if not nxt: continue
        dev = w[f"p{f}"]
        items = [f"{x['label']}→{pr.short(x[f'p{k}'])}" for x, k in nxt]
        more = f" +{len(items) - 4} more" if len(items) > 4 else ""
        endp = [t for t in net.ends(w) if not t.startswith(pr.short(dev))]
        big = not endp or len(endp) > 12  # e.g. the ground bus: listing every end point helps nobody
        notes[dev].append(f"{w['label']} continues: {', '.join(items[:4])}{more}"
                          + ("" if big else f"; net ends: {', '.join(endp[:3])}{' …' if len(endp) > 3 else ''}"))
        w["_cont"] = ", ".join(i.replace("→", " to ") for i in items) + ("" if big else f" | net ends: {', '.join(endp)}")
    for dev, d in des.items():
        if pr.role(dev) in ("splice", "bus"):
            connectors[d] = dict(style="simple", type=safe(f"{d}: {pr.device(dev)}"))
        else:
            pl = devpins[dev]
            sub = pr.strip(next(iter(conns[dev]))) if len(conns[dev]) == 1 else ""
            connectors[d] = {k: v for k, v in dict(type=safe(pr.device(dev)), subtype=safe(sub) if sub else None,
                                                     pins=[pv(p) for p in pl], pinlabels=[safe(v) for v in pl.values()]).items() if v}
        if notes.get(dev): connectors[d]["notes"] = "<br/>".join(safe(n) for n in notes[dev])

    # ---- bundles
    groups = defaultdict(list)
    for t in ends:
        w, e, f, sd = t
        grp = designator(w[f"p{f}"])
        if w["kind"] == "CAN": grp = re.sub(r"-[HL]$", "", grp) + " CAN"  # own bundle, drawn as a twisted pair
        groups[(sd, grp, w["gauge"], lengths.get(w["label"]))].append(t)

    def first_pin(lst):  # order bundles by harness pin so Graphviz has fewer crossings
        return min(pin_order(t[0][f"p{t[1]}p"]) for t in lst)

    cables, connections, n = {}, [], {"near": 0, "far": 0}
    for (sd, grp, g, ln), lst in sorted(groups.items(), key=lambda kv: (kv[0][0] != "near", first_pin(kv[1]), kv[0][1])):
        lst.sort(key=lambda t: (pin_order(t[0][f"p{t[1]}p"]), t[0]["label"]))
        n[sd] += 1
        cd = f"{hcode}-{'C' if sd == 'near' else 'F'}{n[sd]:02d}"
        cab = dict(category="bundle", colors=[t[0]["color"] for t in lst], wirelabels=[t[0]["label"] for t in lst])
        if g != "TBD": cab["gauge"] = g
        if ln: cab["length"] = ln
        if all(t[0]["kind"] == "CAN" for t in lst): cab.update(type="twisted pair", shield=True)
        opn = [t[0]["label"] for t in lst if str(t[0].get("st", "")).startswith("Open")]
        nts = (["gauge TBD"] if g == "TBD" else []) + ([f"OPEN item: {', '.join(opn)}"] if opn else [])
        if nts: cab["notes"] = "; ".join(nts)
        cables[cd] = cab
        for i, (w, e, f, _) in enumerate(lst, 1):
            dev = w[f"p{f}"]; d = designator(dev)
            far = d if pr.role(dev) in ("splice", "bus") else {d: [pv(pid_of[w["id"]])]}
            hx = {X: [pv(w[f"p{e}p"])]}
            connections.append([far, {cd: [i]}, hx] if sd == "near" else [hx, {cd: [i]}, far])
            w["_cable"] = cd

    doc = dict(metadata=dict(title=f"{hname} ({hcode}) harness", description="Generated by schemagen; do not edit."),
               options=dict(fontname="arial", bgcolor="WH", color_mode="SHORT"),
               connectors=connectors, cables=cables, connections=connections)
    # snapshot the wires: _cont/_cable are per drawing and are overwritten by the next harness
    snap = [(dict(w), e, f, sd) for w, e, f, sd in ends]
    return Drawing(H, hcode, X, hname, doc, snap, harness_checks(pr, hcode, raw, pins, halves, ends))
