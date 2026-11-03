"""Connectivity over the typed model.

Nodes: a splice or bus is one node; both halves of a harness-connector pin are one node; every other terminal
(device, connector, pin) is its own node. Breakers, fuses, switches and relays are NOT bridged: they are elements, not
connections, so a net stops at them. Drawings, test sheets, rules and the simulation all read this.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .model import Conductor, Model, Terminal

NodeKey = tuple[str, ...]
End = tuple[int, int]  # (conductor index, end 1|2)


class UnionFind:
    def __init__(self) -> None: self.p: dict[NodeKey, NodeKey] = {}

    def find(self, x: NodeKey) -> NodeKey:
        self.p.setdefault(x, x)
        while self.p[x] != x: self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x

    def union(self, a: NodeKey, b: NodeKey) -> None: self.p[self.find(a)] = self.find(b)


ROLE = {"splice": "splice", "harness": "harness", "bus": "bus", "breaker": "breaker", "fuse": "breaker"}


@dataclass
class NetInfo:
    id: str                   # stable: "net:" + the first label (sorted) on it
    name: str                 # readable: a bus, a splice, or the first label
    conductors: list[int] = field(default_factory=list)
    nodes: list[NodeKey] = field(default_factory=list)
    kind: str = ""            # most common function class


class Net:
    def __init__(self, model: Model):
        self.m = model
        self.c: list[Conductor] = model.conductors
        self.kind = {x.raw: x.kind for x in model.components}
        self.hcode = {x.raw: x.id for x in model.components if x.kind == "harness"}
        self.at: dict[NodeKey, list[End]] = defaultdict(list)
        self.by_dev: dict[str, list[End]] = defaultdict(list)
        self.uf = UnionFind()
        for i in range(len(self.c)):
            a, b = self.node(i, 1), self.node(i, 2)
            self.at[a].append((i, 1)); self.at[b].append((i, 2)); self.uf.union(a, b)
            self.by_dev[self.c[i].from_.device].append((i, 1)); self.by_dev[self.c[i].to.device].append((i, 2))
        self.members: dict[NodeKey, list[NodeKey]] = defaultdict(list)
        for n in self.at: self.members[self.uf.find(n)].append(n)
        self._nets: list[NetInfo] | None = None

    def role(self, raw: str) -> str:
        """splice / harness / bus / breaker / device (the net semantics; switches and relays are devices)."""
        return ROLE.get(self.kind.get(raw, "device"), "device")

    def node_of(self, t: Terminal) -> NodeKey:
        r = self.role(t.device)
        if r in ("splice", "bus"): return (t.device,)
        if r == "harness": return (self.hcode[t.device], "pin", t.pin)
        return (t.device, t.connector, t.pin)

    def node(self, i: int, e: int) -> NodeKey:
        """Electrical node that end e (1 or 2) of conductor i lands on."""
        return self.node_of(self.c[i].end(e))

    def root(self, i: int) -> NodeKey:
        return self.uf.find(self.node(i, 1))

    def net_ends(self, i: int) -> list[End]:
        """Every conductor end on the net of conductor i."""
        return [x for n in self.members[self.root(i)] for x in self.at[n]]

    def ends(self, i: int) -> list[End]:
        """Real end points (devices and breakers) of the net conductor i is on."""
        return [(j, e) for j, e in self.net_ends(i) if self.role(self.c[j].end(e).device) in ("device", "breaker")]

    def reach(self, i: int, e: int, path: tuple[str, ...] = ()) -> list[tuple[Terminal, tuple[str, ...]]]:
        """Terminals reachable from end e of conductor i through splices only (splices are sleeved, so not testable);
        stops at devices, breakers, buses and harness pins. Returns [(terminal, labels on the way)]."""
        c = self.c[i]
        path = path + (c.label,)
        t = c.end(e)
        if self.role(t.device) != "splice": return [(t, path)]
        out = []
        for j, k in self.at[(t.device,)]:
            if j != i and self.c[j].label not in path: out += self.reach(j, 3 - k, path)
        return out

    def next_hop(self, i: int, e: int) -> list[End]:
        """Conductors that continue from end e of conductor i (same splice / bus / harness pin, or the other side of a
        breaker). Returns [(conductor, its far end)]."""
        t = self.c[i].end(e)
        r = self.role(t.device)
        if r == "device": return []
        if r == "breaker":
            lst = [(j, k) for j, k in self.by_dev[t.device] if self.c[j].end(k).connector != t.connector]
        else:
            lst = [(j, k) for j, k in self.at[self.node(i, e)] if j != i]
        return [(j, 3 - k) for j, k in lst]

    def nets(self) -> list[NetInfo]:
        """All nets, with stable ids."""
        if self._nets is None:
            groups: dict[NodeKey, list[int]] = defaultdict(list)
            for i in range(len(self.c)): groups[self.root(i)].append(i)
            out = []
            self._by_root: dict[NodeKey, NetInfo] = {}
            for root, idx in groups.items():
                labels = sorted(self.c[i].label for i in idx)
                nodes = self.members[root]
                named = sorted(n[0] for n in nodes if len(n) == 1)
                kinds: dict[str, int] = defaultdict(int)
                for i in idx: kinds[self.c[i].kind] += 1
                nm = (self.m.component(named[0]).id if self.m.component(named[0]) else named[0]) if named else labels[0]  # type: ignore[union-attr]
                info = NetInfo(id="net:" + labels[0], name=nm, conductors=idx, nodes=nodes, kind=max(kinds, key=lambda k: kinds[k]))
                out.append(info); self._by_root[root] = info
            self._nets = sorted(out, key=lambda n: n.id)
        return self._nets

    def net_of(self, i: int) -> NetInfo:
        self.nets()
        return self._by_root[self.root(i)]
