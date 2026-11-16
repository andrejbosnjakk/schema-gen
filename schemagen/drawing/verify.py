"""The accuracy check (docs/drawing-model.md, Round trip): the netlist a drawing shows, rebuilt from its geometry (or its
scene) alone, against the netlist the model gives for the same scope. Empty difference = the drawing says what the model says."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from ..core.net import NodeKey
from .geometry import Geometry, Scene
from .scope import members

Entry = tuple[str, str, str, str, str, str]  # conductor id, end, end (sorted pin refs), label, gauge, colour


def _entries(ends: dict[str, set[str]], facts: dict[str, set[tuple[str, str, str]]]) -> set[Entry]:
    out: set[Entry] = set()
    for cid, es in ends.items():
        e = sorted(es)
        a, b = (e[0], e[0]) if len(e) == 1 else (e[0], e[1]) if len(e) == 2 else (" + ".join(e), "?")  # more than two ends: a difference
        out |= {(cid, a, b, *f) for f in facts[cid]}
    return out


def netlist(g: Geometry) -> set[Entry]:
    """From geometry only: each wire's conductor, the anchors (their `model`) or flags (their `target`) its ends reference,
    merged over all sheets, with the wire's label, gauge and colour."""
    ends: dict[str, set[str]] = defaultdict(set)
    facts: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for sh in g["sheets"]:
        ref = {a["id"]: a["model"] for s in sh["symbols"] for a in s["anchors"]} | {f["id"]: f["target"] for f in sh["flags"]}
        for w in sh["wires"]:
            cid = w["model"].removeprefix("conductor:")
            ends[cid] |= {ref.get(w["a"], "?" + w["a"]), ref.get(w["b"], "?" + w["b"])}
            facts[cid].add((w["label"], w["gauge"], w["colour"]))
    return _entries(ends, facts)


def scene_netlist(sc: Scene) -> set[Entry]:
    """The same from a scene (before layout): wires by their anchors, flags by their anchor and target."""
    anchors = {p["anchor"] for it in sc["items"] for b in it["blocks"] for p in b["pins"]}
    ends: dict[str, set[str]] = defaultdict(set)
    facts: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for w in sc["wires"]:
        cid = w["model"].removeprefix("conductor:")
        ends[cid] |= {x if x in anchors else "?" + x for x in (w["a"], w["b"])}
        facts[cid].add((w["label"], w["gauge"], w["colour"]))
    for f in sc["flags"]:
        cid = f["model"].removeprefix("conductor:")
        ends[cid] |= {f["at"] if f["at"] in anchors else "?" + f["at"], f["target"]}
        facts[cid].add((f["label"], f["gauge"], f["colour"]))
    return _entries(ends, facts)


def expected(st: Any, sc: Scene) -> set[Entry]:
    """From the model: every conductor on a node the scope's drawing must show, with its two ends. The nodes are found
    independently of the scene builder (a breadth-first closure over core/net.py nodes from the scope's pins, through
    splice and harness pins); for a connection, whose runs are filtered by where they lead, the scene's own nodes."""
    ctx, net, conds = st.ctx, st.ctx.net, st.m.conductors
    if sc["scope"]["kind"] == "connection":
        node_of = {ctx.ref(conds[i].end(e)): net.node(i, e) for i in range(len(conds)) for e in (1, 2)}
        nodes = {node_of[p["anchor"]] for it in sc["items"] for b in it["blocks"] for p in b["pins"] if p["anchor"] in node_of}
    else:
        S, _ = members(st, sc["scope"])
        start = {net.node(i, e) for c in S for i, e in net.by_dev[c.raw]}
        nodes, todo = set(start), deque(start)
        while todo:
            n: NodeKey = todo.popleft()
            for j, k in net.at[n]:
                far = net.node(j, 3 - k)
                if far not in nodes:
                    nodes.add(far)
                    if net.role(conds[j].end(3 - k).device) in ("splice", "harness"): todo.append(far)
    out: set[Entry] = set()
    for i, c in enumerate(conds):
        if net.node(i, 1) in nodes or net.node(i, 2) in nodes:
            a, b = sorted((ctx.ref(c.from_), ctx.ref(c.to)))
            out.add((c.id, a, b, c.label, c.gauge, c.colour_code or c.colour))
    return out


def diff(got: set[Entry], want: set[Entry]) -> list[str]:
    fmt = lambda e: f"{e[0]} {e[1]} - {e[2]} ({', '.join(x for x in e[3:] if x)})"  # noqa: E731
    return sorted([f"missing: {fmt(e)}" for e in want - got] + [f"extra: {fmt(e)}" for e in got - want])


def roundtrip(st: Any, sc: Scene, g: Geometry) -> list[str]:
    """Differences between what the geometry draws and what the model says for the scene's scope; [] = identical."""
    return diff(netlist(g), expected(st, sc))
