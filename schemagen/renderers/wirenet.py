"""0.2 interface to the connectivity model (schemagen.core.net) for code that works on wire dicts.

Breakers and switches are elements, not connections: a net stops at them.
"""
from ..core.net import Net as CoreNet
from ..core.net import UnionFind  # noqa: F401  (0.2 name)


class Net:
    def __init__(self, project):
        self.pr, self.core = project, CoreNet(project.model)
        self.uf, self.at = self.core.uf, self.core.at

    def _w(self, i):
        return self.pr.wires[i]

    def node(self, w, e):
        return self.core.node(w["_i"], e)

    def ends(self, w):
        """Real end points (devices and breakers) of the net this wire is on, as readable strings."""
        pr, out = self.pr, []
        for j, e in self.core.ends(w["_i"]):
            x = self._w(j); d = x[f"p{e}"]
            out.append(f"{pr.short(d)} {pr.term(d, x[f'p{e}c'], x[f'p{e}p'])}".strip())
        return sorted(set(out))

    def reach(self, w, e, path=()):
        """[((device, connector, pin), (labels on the way))] from end e through splices only."""
        return [(t.key(), p) for t, p in self.core.reach(w["_i"], e, tuple(path))]

    def where(self, w, e):
        """Short text for the place end e of wire w lands on: 'PSW 11', 'CB-MOTOR LOAD', 'SP-H40-VDD'."""
        d, pr, c, p = w[f"p{e}"], self.pr, w[f"p{e}c"], w[f"p{e}p"]
        if pr.role(d) == "harness": return f"{pr.harness(d)[1]} {p}"
        if p and len(pr.dev_conns[d]) <= 1: return f"{pr.short(d)} {p}"  # one connector: the pin says enough
        return f"{pr.short(d)} {pr.term(d, c, p)}".strip()

    def next_hop(self, w, e):
        """[(wire, far end of that wire)] continuing from end e of wire w."""
        return [(self._w(j), k) for j, k in self.core.next_hop(w["_i"], e)]
