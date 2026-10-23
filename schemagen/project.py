"""Load a wire-list project: rows from ss??_*.py modules or from a table (see table.py), labels.json, and the optional
display.py (readable names) and names.py (NAMES: id -> wire name) next to them.

One row = one physical conductor: id, p1/p1c/p1p (from device / connector / pin), p2/p2c/p2p (to), func, bus, awg, st, ...
"""
import importlib.util, json, re, sys
from collections import defaultdict

from . import table
from .display_default import DefaultDisplay
from .styles import classify, gauge


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def _module_rows(wl):
    """(rows with 'subsystem' filled in, DISPLAY names, protection list P) from the ss??_*.py modules."""
    mods = [_module(p, p.stem) for p in sorted(wl.glob("ss[0-9][0-9]_*.py"))]
    if not mods: raise SystemExit(f"no ss??_*.py row modules in {wl} (or set 'source' in schemagen.yml)")
    disp, prot, rows = {}, [], []
    for m in mods:
        disp.update(getattr(m, "DISPLAY", {})); prot += getattr(m, "P", [])
        sub = getattr(m, "SUBSYSTEM", (m.__name__,))[0]
        rows += [dict(r, subsystem=r.get("subsystem") or sub) for r in m.R if "_hdr" not in r]
    return rows, disp, prot


class Project:
    def __init__(self, cfg):
        self.cfg = cfg
        wl = cfg.wirelist
        sys.dont_write_bytecode = True  # the wire list folder is input only
        if wl.exists() and str(wl) not in sys.path: sys.path.insert(0, str(wl))  # row modules import their helpers (_lib.py)
        self.dsp = _module(wl / "display.py", "display") if (wl / "display.py").exists() else DefaultDisplay(cfg)
        names = _module(wl / "names.py", "names") if (wl / "names.py").exists() else None
        self.names = getattr(names, "NAMES", {})
        if cfg.source: rows, self.disp, prot = table.read(cfg), {}, []
        else: rows, self.disp, prot = _module_rows(wl)
        self.dsp.set_protection(prot)
        lf = wl / "labels.json"
        labels = json.loads(lf.read_text(encoding="utf-8")) if lf.exists() else {}
        self.wires = []
        for r in rows:
            w = dict(r)
            w["p1"], w["p2"] = str(w["p1"]), str(w["p2"])
            for k in ("p1c", "p1p", "p2c", "p2p"): w[k] = "" if w.get(k) is None else str(w.get(k))
            w["label"] = w.get("label") or labels.get(w["id"], w["id"])
            w["name"] = w.get("name") or self.names.get(w["id"]) or self.dsp.strip(w.get("func", ""))
            w["kind"], w["color"] = classify(w, cfg)
            w["gauge"] = gauge(w.get("awg", ""))
            self.wires.append(w)
        # connectors with numbered pins per device: pins are named "<connector> <pin>" when a device has several
        self.dev_conns = defaultdict(set)
        for w in self.wires:
            for e in (1, 2):
                if w[f"p{e}p"]: self.dev_conns[w[f"p{e}"]].add(w[f"p{e}c"])

    # ---------------------------------------------------------------- naming
    @staticmethod
    def code(raw):
        tok = raw.split()[0] if raw.split() else raw
        return tok if re.fullmatch(r"[A-Z0-9][A-Za-z0-9_.-]*", tok) and any(c.isupper() for c in tok) else None

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
        c, cfg = self.code(raw) or "", self.cfg
        if c.startswith(cfg.splice_prefix): return "splice"
        if self.harness(raw): return "harness"
        if c in cfg.buses or c.startswith(tuple(cfg.bus_prefixes)): return "bus"
        if c.startswith(tuple(cfg.breaker_prefixes)): return "breaker"
        return "device"

    def near(self, half):
        """True for the near half of a harness connector (drawn on the left); set by near_words in schemagen.yml."""
        return any(t in str(half).lower() for t in self.cfg.near_words)

    def short(self, raw):
        s = self.device(raw)
        return self.dsp.SHORT.get(s, self.code(raw) or s)

    def term(self, dev, c, p):
        if self.role(dev) in ("splice", "bus"): return ""
        t = f"{c} {p}".strip() if p else c
        return self.strip(t) or t
