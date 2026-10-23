"""Fallback readable names, used when a project has no display.py of its own.

A project display module must provide: HARNESS, SHORT, harness(raw), device(raw, extra=None), terminal(dev, conn, pin),
strip(text) and set_protection(P). This default derives everything from the raw strings and schemagen.yml.
"""
import re


class DefaultDisplay:
    def __init__(self, cfg):
        # prefix -> (display name, short code, far side name)
        self.HARNESS = {k: tuple(v) for k, v in cfg.harnesses.items()}
        self.SHORT = {}
        self.near_words = cfg.near_words

    def set_protection(self, P):
        pass

    @staticmethod
    def strip(t):
        t = re.sub(r"\s*\([^)]*\)", "", str(t)); t = re.sub(r"\s*\[[^]]*\]\s*", "", t)
        return re.sub(r"\s{2,}", " ", t).strip()

    def harness(self, raw):
        for k, v in self.HARNESS.items():
            if str(raw).startswith(k): return v
        return None

    def device(self, raw, extra=None):
        raw = str(raw)
        if extra and raw in extra: return extra[raw]
        h = self.harness(raw)
        return h[0] if h else self.strip(raw)  # keep the device code: "CB-ECU 5 A", "ECU engine control unit"

    def terminal(self, dev, c, p):
        c, p = str(c or ""), str(p or "")
        h = self.harness(dev)
        if h: return f"{c}, pin {p}" if p else c  # the half's own name: "Cabin half, pin 1"
        if p: return f"{self.strip(c)}, pin {p}" if c else f"pin {p}"
        return c
