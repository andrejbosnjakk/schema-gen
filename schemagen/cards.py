"""Pin data from datasheet interface cards: the start of a part library.

Preferred: a structured block anywhere in a card (markdown file), fenced as ```yaml schemagen:

    device: '^ECU$'                 # regex on the device code in the wire list
    connectors:
      - id: J1
        match: 'J1'                 # regex on the wire list's connector field
        part: TE 776286-1           # optional
        pins:
          - {n: 1, name: VBAT, type: power_in, v_max: 16, i_max: 5}

Fallback for cards without a block: markdown pin tables (first header 'Pin' or 'Contact', column 2 = signal),
picked by a `cardmap` entry in schemagen.yml: {device, connector, card, table} regexes.
"""
import re

import yaml

BLOCK = re.compile(r"^```ya?ml schemagen\s*\n(.*?)^```", re.M | re.S)


class Cards:
    def __init__(self, folder, cardmap=()):
        self.folder, self.cardmap, self._tables = folder, list(cardmap), {}
        self.blocks = []  # [(card file, block dict)]
        for path in sorted(folder.glob("*.md")) if folder.exists() else []:
            for m in BLOCK.finditer(path.read_text(encoding="utf-8")):
                self.blocks.append((path.name, yaml.safe_load(m.group(1)) or {}))

    def connector(self, code, conn):
        """Structured connector entry for (device code, connector field), or None."""
        for fn, b in self.blocks:
            if re.search(str(b.get("device", "$^")), code or ""):
                for c in b.get("connectors", []):
                    if re.search(str(c.get("match", c.get("id", ""))), conn): return c
        return None

    def tables(self, fn):
        """[(context text, {pin: signal})] for one card file (markdown pin tables)."""
        if fn in self._tables: return self._tables[fn]
        tabs, head, cap, cur = [], "", "", None
        path = self.folder / fn
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        for line in lines:
            s = line.strip()
            if s.startswith("|"):
                cells = [c.strip() for c in s.strip("|").split("|")]
                if cur is None:
                    if re.match(r"(Pin|Contact)\b", cells[0]) and len(cells) > 1:
                        cur = {}; tabs.append((head + " " + cap, cur))
                    continue
                if set(cells[0]) <= set("-: "): continue
                sig = re.sub(r"\*\*|`", "", cells[1]).strip()
                cur[re.sub(r"\*\*", "", cells[0])] = re.sub(r"\s*\(.*$", "", sig)[:30]
                continue
            cur = None
            if s.startswith("#"): head, cap = s, ""
            elif s: cap = s[:120]
        self._tables[fn] = tabs
        return tabs

    def pin(self, code, conn, pin):
        """Signal name for (device code, connector, pin), or None. Structured blocks win over markdown tables."""
        c = self.connector(code, conn)
        if c:
            for p in c.get("pins", []):
                if str(p.get("n")) == str(pin): return str(p.get("name", ""))[:30] or None
        for m in self.cardmap:
            if re.search(m["device"], code or "") and re.search(m.get("connector", "."), conn):
                for text, pins in self.tables(m["card"]):
                    if re.search(m["table"], text) and pin in pins: return pins[pin]
        return None
