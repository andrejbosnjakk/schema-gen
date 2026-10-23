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
        if h: return h[0]
        t = self.strip(raw).split(" ", 1)
        return t[1] if len(t) == 2 and re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", t[0]) else self.strip(raw)

    def terminal(self, dev, c, p):
        c, p = str(c or ""), str(p or "")
        h = self.harness(dev)
        if h:
            side = "near side" if any(w in c.lower() for w in self.near_words) else f"{h[2]} side"
            return f"{side}, pin {p}" if p else side
        if p: return f"{self.strip(c)}, pin {p}" if c else f"pin {p}"
        return c
