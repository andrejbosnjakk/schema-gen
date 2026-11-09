"""Interface drawings: one WireViz drawing per item (device, breaker or bus) that has a conductor no harness drawing
reaches. An item's drawing shows every conductor on it (its grounds too, though the ground bus drawing has them as
well); a conductor drawn more than once is labelled with the other drawings. Conductors still undrawn after that
(splice to splice, harness to harness) go on splice drawings picked greedily, the one with the most first."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from ..core.classes import connector_size
from .harness import Drawing, clean_func, pv, safe

PRIORITY = {"device": 0, "breaker": 1, "bus": 2, "splice": 3}


def pick_items(pr: Any, wires: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """[(item device string, its conductors)] covering every wire given: each item on one of them with all of its
    conductors, then splices (greedy set cover) for the rest."""
    on: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for w in pr.wires:
        for d in dict.fromkeys((w["p1"], w["p2"])): on[d].append(w)
    mine: dict[str, int] = defaultdict(int)
    for w in wires:
        for d in dict.fromkeys((w["p1"], w["p2"])):
            if pr.role(d) not in ("harness", "splice"): mine[d] += 1
    out = [(d, on[d]) for d in sorted(mine, key=lambda d: (-mine[d], PRIORITY.get(pr.role(d), 0), d))]
    drawn = {w["_i"] for _, ws in out for w in ws}
    left = {w["_i"]: w for w in wires if w["_i"] not in drawn}
    while left:
        cnt: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for w in left.values():
            for e in (1, 2):
                d = w[f"p{e}"]
                if pr.role(d) != "harness" and w not in cnt[d]: cnt[d].append(w)
        if not cnt:  # harness-to-harness conductors: draw them on their first connector
            for w in left.values(): cnt[w["p1"]].append(w)
        best = min(cnt, key=lambda d: (-len(cnt[d]), PRIORITY.get(pr.role(d), 0), d))
        out.append((best, cnt[best]))
        for w in cnt[best]: left.pop(w["_i"], None)
    return out


def _pid(pr: Any, dev: str, c: str, p: str) -> str:
    if not p: return pr.strip(c) or c or "terminal"
    if len(pr.dev_conns[dev]) > 1: return f"{pr.strip(c)} {p}"
    return p


def _code(pr: Any, dev: str) -> str:
    return pr.code(dev) or re.sub(r"\W+", "_", pr.strip(dev))[:24].strip("_")


def build_item(pr: Any, net: Any, cards: Any, dev: str, wires: list[dict[str, Any]], also: dict[int, list[str]] | None = None) -> Drawing:
    """Drawing of one item with the given conductors: the item in the middle, each far item with its own bundle.
    `also`: conductor index -> the other drawings it is on (written after its label)."""
    code = _code(pr, dev)
    name = f"IF-{code}"
    also = also or {}
    simple = pr.role(dev) in ("splice", "bus")
    connectors: dict[str, Any] = {}
    me = code
    ends = []
    for w in wires:
        e = 1 if w["p1"] == dev else 2
        ends.append((w, e, 3 - e, "far"))
    mypins: dict[str, str] = {}
    for w, e, f, _ in ends:
        if not simple:
            pid = _pid(pr, dev, w[f"p{e}c"], w[f"p{e}p"])
            mypins.setdefault(pid, cards.pin(pr.code(dev), w[f"p{e}c"], w[f"p{e}p"]) or clean_func(w["func"], 30) or clean_func(w["name"], 30))
    if not simple:  # the real size when the name says it ("D-sub 25"): unused pins listed as spare
        conns = {w[f"p{e}c"] for w, e, f, _ in ends}
        for c in sorted(conns):
            n = connector_size(c) or (connector_size(pr.device(dev)) if len(conns) == 1 else None)
            for k in range(1, (n or 0) + 1): mypins.setdefault(_pid(pr, dev, c, str(k)), "spare")
            if n: mypins = dict(sorted(mypins.items(), key=lambda kv: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", kv[0])]))
    connectors[me] = dict(style="simple", type=safe(f"{me}: {pr.device(dev)}")) if simple else \
        dict(type=safe(pr.device(dev)), pins=[pv(p) for p in mypins], pinlabels=[safe(v) for v in mypins.values()])
    des: dict[str, str] = {}
    farpins: dict[str, dict[str, str]] = defaultdict(dict)
    notes: dict[str, list[str]] = defaultdict(list)
    footnotes: list[tuple[int, str, str]] = []
    for w, e, f, _ in sorted(ends, key=lambda t: t[0]["label"]):
        d = w[f"p{f}"]
        if d not in des:
            x = pr.code(d) or re.sub(r"\W+", "_", pr.strip(d))[:24].strip("_")
            if x == me or x in des.values(): x = f"{x}_{len(des) + 1}"
            des[d] = x
        role = pr.role(d)
        if role == "harness":
            farpins[d].setdefault(w[f"p{f}p"], f"{w[f'p{f}c']}")
        elif role not in ("splice", "bus"):
            farpins[d].setdefault(_pid(pr, d, w[f"p{f}c"], w[f"p{f}p"]),
                                  cards.pin(pr.code(d), w[f"p{f}c"], w[f"p{f}p"]) or clean_func(w["func"], 30) or clean_func(w["name"], 30))
        nxt = net.next_hop(w, f)
        w["_cont"] = ""
        if nxt:
            hops = [f"{x['label']} ({net.where(x, k)})" for x, k in nxt]
            footnotes.append((len(footnotes) + 1, w["label"], ", ".join(hops)))
            more = f" +{len(hops) - 3}" if len(hops) > 3 else ""
            notes[d].append(f"{w['label']} → {', '.join(hops[:3])}{more} [{len(footnotes)}]")
            w["_cont"] = ", ".join(hops)
    for d, x in des.items():
        role = pr.role(d)
        if role in ("splice", "bus"): connectors[x] = dict(style="simple", type=safe(f"{x}: {pr.device(d)}"))
        else:
            pl = farpins[d]
            connectors[x] = dict(type=safe(pr.device(d)), pins=[pv(p) for p in pl], pinlabels=[safe(v) for v in pl.values()])
        if notes.get(d): connectors[x]["notes"] = "<br/>".join(safe(n) for n in notes[d])
    groups: dict[str, list[Any]] = defaultdict(list)
    for t in ends: groups[des[t[0][f"p{t[2]}"]]].append(t)
    cables, connections = {}, []
    for k, (x, lst) in enumerate(sorted(groups.items()), 1):
        lst.sort(key=lambda t: t[0]["label"])
        cd = f"{me}-W{k:02d}"
        cab: dict[str, Any] = dict(category="bundle", colors=[t[0]["color"] for t in lst],
                                   wirelabels=[t[0]["label"] + ("" if t[0]["gauge"] == "TBD" else f" · {t[0]['gauge'].split()[0]}")
                                               + _also([x for x in also.get(t[0]["_i"], []) if x != name]) for t in lst])
        gauges = {t[0]["gauge"] for t in lst}
        if len(gauges) == 1 and "TBD" not in gauges: cab["gauge"] = gauges.pop()
        if all(t[0]["kind"] == "CAN" for t in lst): cab.update(type="twisted pair", shield=True)
        cables[cd] = cab
        for i, (w, e, f, _) in enumerate(lst, 1):
            d = w[f"p{f}"]
            mine = me if simple else {me: [pv(_pid(pr, dev, w[f"p{e}c"], w[f"p{e}p"]))]}
            role = pr.role(d)
            far = x if role in ("splice", "bus") else {x: [pv(w[f"p{f}p"] if role == "harness" else _pid(pr, d, w[f"p{f}c"], w[f"p{f}p"]))]}
            connections.append([mine, {cd: [i]}, far])
            w["_cable"] = cd
    title = f"{pr.device(dev)} ({code}) interface"
    doc = dict(metadata=dict(title=title, description="Generated by schemagen; do not edit."),
               options=dict(fontname="arial", bgcolor="WH", color_mode="SHORT"), connectors=connectors, cables=cables, connections=connections)
    snap = [(dict(w), e, f, sd) for w, e, f, sd in ends]
    return Drawing(name, code, me, pr.device(dev), doc, snap, [], footnotes, "")


def _also(names: list[str]) -> str:
    if not names: return ""
    return f" (also on {', '.join(names[:2])}{f' +{len(names) - 2}' if len(names) > 2 else ''})"


def build_all(pr: Any, net: Any, cards: Any, covered: dict[int, list[str]]) -> list[Drawing]:
    """Interface drawings for every conductor whose index is not in `covered` (index -> the harness drawings it is on)."""
    items = pick_items(pr, [w for w in pr.wires if w["_i"] not in covered])
    also: dict[int, list[str]] = defaultdict(list)
    for i, names in covered.items(): also[i] += names
    for d, ws in items:
        for w in ws: also[w["_i"]].append(f"IF-{_code(pr, d)}")
    return [build_item(pr, net, cards, d, ws, also) for d, ws in items]
