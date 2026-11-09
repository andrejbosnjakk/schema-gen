"""WireViz harness drawing for one harness connector (or one part of it).

Scope: every conductor with one end on the connector. Near half (near_words in schemagen.yml) on the left, far half on the
right, the connector with all its pins (spares shown) in the middle. Far ends are devices (pin tables, card pin
names), or splices/buses drawn as simple boxes with a short "next hop" note; the full continuation and net ends go
into numbered footnotes. Wires are bundled per (side, far item); each wire label carries its gauge. A CAN H/L pair
gets its own shielded twisted-pair bundle.

Wide harnesses are split into parts: by side ('near'/'far') or by function ('power'/'can'/'signal').
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field

from ..core.classes import connector_size
from .checks import harness_checks

PARTS = {"side": ("near", "far"), "function": ("power", "can", "signal")}


@dataclass
class Drawing:
    harness: str          # drawing name: harness id, or harness id + '_' + part (X-BH, X-PSW_far)
    code: str             # short code of the harness connector, e.g. X-BH
    designator: str       # connector designator in the drawing
    name: str             # readable connector name
    doc: dict             # WireViz YAML document
    ends: list            # [(wire, harness end, far end, 'near'|'far')] of this drawing
    checks: list = field(default_factory=list)
    footnotes: list = field(default_factory=list)  # [(n, label, text)]
    parent: str = ""      # harness id when this drawing is a part


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


def function_part(w):
    return "can" if w["kind"] == "CAN" else "signal" if w["kind"] == "signal" else "power"


def harness_ends(pr, H):
    """[(wire, harness end, far end, side)] for every conductor with one end on harness connector H."""
    out = []
    for w in pr.wires:
        for e in (1, 2):
            if w[f"p{e}"].startswith(H) and pr.harness(w[f"p{e}"]):
                out.append((w, e, 3 - e, w.get(f"p{e}side") or ("near" if pr.near(w[f"p{e}c"]) else "far"))); break
    if not out: raise SystemExit(f"no wires on {H}")
    return out


def split_mode(pr, H, ends, mode):
    """Resolve 'auto' to 'side' when the drawing would have more far items than split_threshold."""
    if mode != "auto": return mode
    items = {w[f"p{f}"] for w, e, f, sd in ends}
    return "side" if len(items) > pr.cfg.split_threshold else "none"


def build(pr, net, cards, H, lengths=None, part=None):
    lengths = lengths or {}
    all_ends = harness_ends(pr, H)
    raw = all_ends[0][0][f"p{all_ends[0][1]}"]
    hname, hcode, farname = pr.harness(raw)[:3]
    X = hcode if hcode.startswith("X-") else "X-" + hcode
    keep = (lambda t: True) if part is None else (lambda t: t[3] == part) if part in PARTS["side"] else (lambda t: function_part(t[0]) == part)
    ends = [t for t in all_ends if keep(t)]
    name = H if part is None else f"{H}_{part}"

    # ---- harness connector: both halves as one connector, all shell pins (labels from the whole harness)
    pins, halves = defaultdict(lambda: {"near": [], "far": []}), {"near": set(), "far": set()}
    for w, e, f, sd in all_ends:
        halves[sd].add(w[f"p{e}c"]); pins[w[f"p{e}p"]][sd].append(w)
    npins = connector_size(raw, *halves["near"], *halves["far"]) or max([int(p) for p in pins if p.isdigit()] or [0])
    pinlist = [str(i) for i in range(1, npins + 1)] + sorted(p for p in pins if not p.isdigit())
    used_here = {w[f"p{e}p"] for w, e, f, sd in ends}
    plabels = []
    for p in pinlist:
        ws = pins[p]["near"] + pins[p]["far"]
        names = [n for n in (clean_func(w["func"]) for w in ws) if n] or [clean_func(w["name"]) for w in ws]
        lab = min(names, key=len) if ws else "spare"
        if ws and part in PARTS["function"] and p not in used_here: lab = f"({lab})"  # wired in another part
        plabels.append(safe(lab))
    near_half = " / ".join(sorted(halves["near"])) or "near half"
    far_half = " / ".join(sorted(halves["far"])) or "far half"
    xnote = f"{raw}. Left = {near_half}, right = {far_half} ({farname} side)."
    if part: xnote += f" This drawing: {part} part only."
    connectors = {X: dict(type=safe(hname), subtype=safe(f"left: {near_half} | right: {far_half}"),
                          pins=[pv(p) for p in pinlist], pinlabels=plabels, notes=safe(xnote))}

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

    # ---- short "next hop" notes; the full continuation goes into numbered footnotes
    notes, footnotes = defaultdict(list), []
    for w, e, f, sd in sorted(ends, key=lambda t: t[0]["label"]):
        nxt = net.next_hop(w, f)
        w["_cont"] = ""
        if not nxt: continue
        hops = [f"{x['label']} ({net.where(x, k)})" for x, k in nxt]
        endp = [t for t in net.ends(w) if not t.startswith(pr.short(w[f"p{f}"]))]
        big = not endp or len(endp) > 12  # e.g. the ground bus: listing every end point helps nobody
        full = ", ".join(hops) + ("" if big else f" | net ends: {', '.join(endp)}")
        footnotes.append((len(footnotes) + 1, w["label"], full))
        more = f" +{len(hops) - 3}" if len(hops) > 3 else ""
        notes[w[f"p{f}"]].append(f"{w['label']} → {', '.join(hops[:3])}{more} [{len(footnotes)}]")
        w["_cont"] = full
    for dev, d in des.items():
        if pr.role(dev) in ("splice", "bus"):
            connectors[d] = dict(style="simple", type=safe(f"{d}: {pr.device(dev)}"))
        else:
            pl = devpins[dev]
            sub = pr.strip(next(iter(conns[dev]))) if len(conns[dev]) == 1 else ""
            connectors[d] = {k: v for k, v in dict(type=safe(pr.device(dev)), subtype=safe(sub) if sub else None,
                                                     pins=[pv(p) for p in pl], pinlabels=[safe(v) for v in pl.values()]).items() if v}
        if notes.get(dev): connectors[d]["notes"] = "<br/>".join(safe(n) for n in notes[dev])

    # ---- bundles: one per (side, far item); CAN pairs separate so they can be drawn twisted
    groups = defaultdict(list)
    for t in ends:
        w, e, f, sd = t
        grp = designator(w[f"p{f}"])
        if w["kind"] == "CAN": grp = re.sub(r"-[HL]$", "", grp) + " CAN"
        groups[(sd, grp)].append(t)

    def first_pin(lst):  # order bundles by harness pin so Graphviz has fewer crossings
        return min(pin_order(t[0][f"p{t[1]}p"]) for t in lst)

    cables, connections, n = {}, [], {"near": 0, "far": 0}
    for (sd, grp), lst in sorted(groups.items(), key=lambda kv: (kv[0][0] != "near", first_pin(kv[1]), kv[0][1])):
        lst.sort(key=lambda t: (pin_order(t[0][f"p{t[1]}p"]), t[0]["label"]))
        n[sd] += 1
        cd = f"{hcode}-{'C' if sd == 'near' else 'F'}{n[sd]:02d}"
        gauges = {t[0]["gauge"] for t in lst}
        lens = {lengths.get(t[0]["label"]) for t in lst}
        cab = dict(category="bundle", colors=[t[0]["color"] for t in lst],
                   wirelabels=[t[0]["label"] + ("" if t[0]["gauge"] == "TBD" else f" · {t[0]['gauge'].split()[0]}") for t in lst])
        if len(gauges) == 1 and "TBD" not in gauges: cab["gauge"] = gauges.pop()
        if len(lens) == 1 and None not in lens: cab["length"] = lens.pop()
        if all(t[0]["kind"] == "CAN" for t in lst): cab.update(type="twisted pair", shield=True)
        opn = [t[0]["label"] for t in lst if str(t[0].get("st", "")).startswith("Open")]
        tbd = [t[0]["label"] for t in lst if t[0]["gauge"] == "TBD"]
        nts = ([f"gauge TBD: {', '.join(tbd)}"] if tbd else []) + ([f"OPEN item: {', '.join(opn)}"] if opn else [])
        if nts: cab["notes"] = "; ".join(nts)
        cables[cd] = cab
        for i, (w, e, f, _) in enumerate(lst, 1):
            dev = w[f"p{f}"]; d = designator(dev)
            far = d if pr.role(dev) in ("splice", "bus") else {d: [pv(pid_of[w["id"]])]}
            hx = {X: [pv(w[f"p{e}p"])]}
            connections.append([far, {cd: [i]}, hx] if sd == "near" else [hx, {cd: [i]}, far])
            w["_cable"] = cd

    title = f"{hname} ({hcode}) harness" + (f", {part} part" if part else "")
    doc = dict(metadata=dict(title=title, description="Generated by schemagen; do not edit."),
               options=dict(fontname="arial", bgcolor="WH", color_mode="SHORT"),
               connectors=connectors, cables=cables, connections=connections)
    # snapshot the wires: _cont/_cable are per drawing and are overwritten by the next one
    snap = [(dict(w), e, f, sd) for w, e, f, sd in ends]
    checks = harness_checks(pr, hcode, raw, pins, halves, all_ends) if part is None else []
    return Drawing(name, hcode, X, hname, doc, snap, checks, footnotes, H if part else "")


def build_set(pr, net, cards, H, lengths=None, mode="auto"):
    """The full drawing of H (for cut list, test sheet, checks) plus the drawings to render (itself, or its parts)."""
    full = build(pr, net, cards, H, lengths)
    mode = split_mode(pr, H, full.ends, mode)
    if mode in (None, "none"): return full, [full]
    which = (lambda t, p: t[3] == p) if mode == "side" else (lambda t, p: function_part(t[0]) == p)
    parts = [build(pr, net, cards, H, lengths, part=p) for p in PARTS[mode] if any(which(t, p) for t in full.ends)]
    # cut list and test sheet must name the bundles as drawn, so take the wires from the parts
    full.ends = [t for d in parts for t in d.ends]
    return full, parts
