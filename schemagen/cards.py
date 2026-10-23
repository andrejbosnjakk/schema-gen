"""Pin names from datasheet interface cards (markdown files with pin tables).

A pin table is any markdown table whose first header cell starts with 'Pin' or 'Contact'; column 2 is the signal name.
Each table is identified by its context: the last heading plus the last caption line before it.
schemagen.yml maps device/connector to a card table:
    cardmap:
      - {device: '^ECU$', connector: 'J1', card: ECU_card.md, table: 'J1'}
"""
import re


class Cards:
    def __init__(self, folder, cardmap):
        self.folder, self.cardmap, self._tables = folder, cardmap, {}

    def tables(self, fn):
        """[(context text, {pin: signal})] for one card file."""
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
        """Signal name for (device code, connector, pin), or None."""
        for m in self.cardmap:
            if re.search(m["device"], code or "") and re.search(m.get("connector", "."), conn):
                for text, pins in self.tables(m["card"]):
                    if re.search(m["table"], text) and pin in pins: return pins[pin]
        return None
