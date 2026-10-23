"""Connectivity model of the whole wire list.

Nodes: a splice or bus is one node; both halves of a harness-connector pin are one node; every other terminal
(device, connector, pin) is its own node. Breakers and fuses are NOT bridged (they are switching/protective
elements), so a net stops at them. This model is the base for the drawings' "continues at" notes, the test
sheets and, later, the current-flow simulation.
"""
from collections import defaultdict


class UnionFind:
    def __init__(self): self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x: self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x

    def union(self, a, b): self.p[self.find(a)] = self.find(b)


class Net:
    def __init__(self, project):
        self.pr, self.at, self.uf = project, defaultdict(list), UnionFind()
        for w in project.wires:
            a, b = self.node(w, 1), self.node(w, 2)
            self.at[a].append((w, 1)); self.at[b].append((w, 2)); self.uf.union(a, b)

    def node(self, w, e):
        """Electrical node that end e (1 or 2) of wire w lands on."""
        dev, c, p = w[f"p{e}"], w[f"p{e}c"], w[f"p{e}p"]
        r = self.pr.role(dev)
        if r in ("splice", "bus"): return (dev,)
        if r == "harness": return (self.pr.harness(dev)[1], "pin", p)
        return (dev, c, p)

    def ends(self, w):
        """Real end points (devices and breakers) of the net this wire is on, as readable strings."""
        root, pr, out = self.uf.find(self.node(w, 1)), self.pr, []
        for n, lst in self.at.items():
            if self.uf.find(n) != root: continue
            for x, e in lst:
                d = x[f"p{e}"]
                if pr.role(d) in ("device", "breaker"): out.append(f"{pr.short(d)} {pr.term(d, x[f'p{e}c'], x[f'p{e}p'])}".strip())
        return sorted(set(out))

    def reach(self, w, e, path=()):
        """Terminals reachable from end e of wire w through splices only (splices are sleeved, so not testable).
        Returns [((device, connector, pin), (labels on the way))]; stops at devices, breakers, buses and harness pins."""
        path = path + (w["label"],)
        dev = w[f"p{e}"]
        if self.pr.role(dev) != "splice": return [((dev, w[f"p{e}c"], w[f"p{e}p"]), path)]
        out = []
        for x, k in self.at[(dev,)]:
            if x is not w and x["label"] not in path: out += self.reach(x, 3 - k, path)
        return out

    def where(self, w, e):
        """Short text for the place end e of wire w lands on: 'PSW 11', 'CB-MOTOR LOAD', 'SP-H40-VDD'."""
        d, pr, c, p = w[f"p{e}"], self.pr, w[f"p{e}c"], w[f"p{e}p"]
        if pr.role(d) == "harness": return f"{pr.harness(d)[1]} {p}"
        if p and len(pr.dev_conns[d]) <= 1: return f"{pr.short(d)} {p}"  # one connector: the pin says enough
        return f"{pr.short(d)} {pr.term(d, c, p)}".strip()

    def next_hop(self, w, e):
        """Wires that continue from end e of wire w (same splice / bus / harness pin, or the other side of a breaker).
        Returns [(wire, far end of that wire)]."""
        d, c = w[f"p{e}"], w[f"p{e}c"]
        if self.pr.role(d) == "device": return []
        if self.pr.role(d) == "breaker":
            lst = [(x, k) for n, l in self.at.items() if n[0] == d for x, k in l if x[f"p{k}c"] != c]
        else:
            lst = [(x, k) for x, k in self.at[self.node(w, e)] if x is not w]
        return [(x, 3 - k) for x, k in lst]
