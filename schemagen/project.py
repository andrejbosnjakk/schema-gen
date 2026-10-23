"""Load a wire-list project: ss??_*.py row modules, labels.json, optional display.py / names.py.

One row = one physical conductor: id, p1/p1c/p1p (from device / connector / pin), p2/p2c/p2p (to), func, bus, awg, st, ...
"""
import importlib.util, json, re, sys

from .display_default import DefaultDisplay
from .styles import classify, gauge


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


class Project:
    def __init__(self, cfg):
        self.cfg = cfg
        wl = cfg.wirelist
        sys.dont_write_bytecode = True  # the wire list folder is input only
        if str(wl) not in sys.path: sys.path.insert(0, str(wl))  # row modules import their own helpers (_lib.py)
        self.dsp = _module(wl / "display.py", "display") if (wl / "display.py").exists() else DefaultDisplay(cfg)
        names = _module(wl / "names.py", "names") if (wl / "names.py").exists() else None
        self.names = getattr(names, "NAMES", {})
        t_ids = getattr(names, "T_IDS", set())
        mods = [_module(p, p.stem) for p in sorted(wl.glob("ss[0-9][0-9]_*.py"))]
        if not mods: raise SystemExit(f"no ss??_*.py row modules in {wl}")
        self.disp = {}
        for m in mods: self.disp.update(getattr(m, "DISPLAY", {}))
        self.dsp.set_protection([p for m in mods for p in getattr(m, "P", [])])
        lf = wl / "labels.json"
        labels = json.loads(lf.read_text(encoding="utf-8")) if lf.exists() else {}
        self.wires = []
        for m in mods:
            for r in m.R:
                if "_hdr" in r: continue
                w = dict(r)
                w["p1"], w["p2"] = str(w["p1"]), str(w["p2"])
                for k in ("p1c", "p1p", "p2c", "p2p"): w[k] = "" if w.get(k) is None else str(w.get(k))
                w["label"] = labels.get(w["id"], w["id"])
                w["dom"] = w.get("dom") or ("T" if w["id"] in t_ids else "L")
                w["name"] = w.get("name") or self.names.get(w["id"]) or self.dsp.strip(w.get("func", ""))
                w["kind"], w["color"] = classify(w, cfg)
                w["gauge"] = gauge(w.get("awg", ""))
                w["subsystem"] = getattr(m, "SUBSYSTEM", (m.__name__,))[0]
                self.wires.append(w)

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
        """True for the near (cockpit / fuselage) half of a harness connector, drawn on the left."""
        return any(t in str(half).lower() for t in self.cfg.near_words)

    def short(self, raw):
        s = self.device(raw)
        return self.dsp.SHORT.get(s, self.code(raw) or s)

    def term(self, dev, c, p):
        if self.role(dev) in ("splice", "bus"): return ""
        t = f"{c} {p}".strip() if p else c
        return self.strip(t) or t
