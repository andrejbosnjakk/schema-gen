"""A loaded project for the drawing and sheet code: the typed model (core.load) plus 0.2-style wire dicts.

`Project.model` is the source of truth; `Project.wires` are dict views of its conductors (one per conductor, same
order, `_i` = index) with the 0.2 keys (id, label, name, p1/p1c/p1p, p2/p2c/p2p, func, bus, awg, st, kind, color,
gauge) plus every extra key of the input row and the resolved sides (p1side, p2side).
"""
from collections import defaultdict

from ..core.build import code as _code
from ..core.classes import gauge
from ..core.load import load


class Project:
    def __init__(self, cfg):
        L = load(cfg)
        self.cfg, self.loaded, self.model = L.cfg, L, L.model
        self.dsp, self.disp, self.warnings = L.naming, L.display, L.warnings
        self.names = {}
        self.wires = []
        recs = L.records if len(L.records) == len(self.model.conductors) else [None] * len(self.model.conductors)
        for i, (c, r) in enumerate(zip(self.model.conductors, recs)):
            w = dict(r.data) if r is not None else dict(c.extra, amps=c.current_a if c.current_a is not None else "")
            for e, t in ((1, c.from_), (2, c.to)):
                w[f"p{e}"], w[f"p{e}c"], w[f"p{e}p"], w[f"p{e}side"] = t.device, t.connector, t.pin, t.side
            w.update(id=c.id, label=c.label, name=c.name, func=c.func, bus=c.bus, awg=c.gauge, st=c.status, subsystem=c.subsystem,
                     notes=c.notes, kind=c.kind, color=c.colour_code, gauge=gauge(c.gauge), _i=i)
            self.wires.append(w)
        # connectors with numbered pins per device: pins are named "<connector> <pin>" when a device has several
        self.dev_conns = defaultdict(set)
        for w in self.wires:
            for e in (1, 2):
                if w[f"p{e}p"]: self.dev_conns[w[f"p{e}"]].add(w[f"p{e}c"])
        self._role = {x.raw: x.kind for x in self.model.components}

    # ---------------------------------------------------------------- naming
    @staticmethod
    def code(raw):
        return _code(raw)

    def harness(self, raw):
        return self.dsp.harness(raw)

    def device(self, raw):
        return self.dsp.device(raw, self.disp)

    def terminal(self, dev, c, p):
        return str(self.dsp.terminal(dev, c, p)).lstrip("'")

    def strip(self, t):
        return self.dsp.strip(t)

    def role(self, raw):
        """splice / harness / bus / breaker / device."""
        k = self._role.get(raw)
        if k is not None: return {"fuse": "breaker"}.get(k, k if k in ("splice", "harness", "bus", "breaker") else "device")
        c, cfg = self.code(raw) or "", self.cfg
        if c.startswith(cfg.splice_prefix): return "splice"
        if self.harness(raw): return "harness"
        if c in cfg.buses or c.startswith(tuple(cfg.bus_prefixes)): return "bus"
        if c.startswith(tuple(cfg.breaker_prefixes)): return "breaker"
        return "device"

    def near(self, half):
        """0.2 heuristic (near_words); the model's resolved sides are in w['p1side'] / w['p2side']."""
        return any(t in str(half).lower() for t in self.cfg.near_words)

    def short(self, raw):
        s = self.device(raw)
        return self.dsp.SHORT.get(s, self.code(raw) or s)

    def term(self, dev, c, p):
        if self.role(dev) in ("splice", "bus"): return ""
        t = f"{c} {p}".strip() if p else c
        return self.strip(t) or t
