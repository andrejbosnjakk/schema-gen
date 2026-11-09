"""The readable sheet: the layout a team edits by hand (docs/readable.md).

Columns: Label, Name, From, From connector / pin, To, To connector / pin, Voltage, Current (A), Gauge, Length (m),
Weight (g). Rows: a subsystem title (text in column A only), a component header (text in column B only) or a wire.
Devices are plain names; each gets a code (from the Components tab, else generated from its kind and name) and keeps
its name as the display name. Connector / pin cells follow the grammar in `parse_cp`; a cell that does not parse is
kept as written and reported by the `readable-cell` rule. The original cell text is kept, so an unedited sheet
exports cell for cell as it was read.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .records import Record
from .rows import Tables

HEAD = ["Label", "Name", "From", "From connector / pin", "To", "To connector / pin", "Voltage", "Current (A)", "Gauge",
        "Length (m)", "Weight (g)"]
FIELD = ["label", "name", "p1", "p1t", "p2", "p2t", "bus", "amps", "awg", "length", "weight_g"]
# device kind from its name: first matching pattern wins (override: readable.kinds in schemagen.yml, or the Components tab)
KINDS: dict[str, str] = {"splice": r"\bsplice\b", "bus": r"\bbus\b|\bbus ?bar\b", "breaker": r"^breaker\b|\bcircuit breaker\b",
                         "fuse": r"^fuse\b", "harness": r"\bconnector\b", "relay": r"\brelay\b|\bcontactor\b", "switch": r"\bswitch\b"}
# CAN conductors by name (override: readable.can); a conductor touching a splice whose name matches is CAN too
CAN = r"^(CAN\d|GCAN)|CAN_[HL]\b"
CAN_L = r"(CAN\d*|GCAN)[ _-]?L\b"
# harness connector halves by their cell text (override or extend: readable.sides in schemagen.yml)
SIDES = {"cockpit side": "near", "fuselage side": "near", "cabin side": "near", "nose side": "far", "tank side": "far",
         "wing side": "far", "back cabin side": "far", "side-wall sensor side": "far"}
PREFIX = {"breaker": "CB-", "fuse": "FU-", "splice": "SP-", "bus": "BB-", "harness": "X-", "relay": "K-", "switch": "SW-", "device": ""}

_NOTE = re.compile(r"^(.*?)\s*\(([^()]*)\)$")
_TOKEN = re.compile(r"^[\w+-]+$")
COLOURS = "red|black|brown|yellow|white|blue|green|orange|grey|gray|violet|purple|pink"
_FORMS: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(r"^pin\s+([\w+-]+)$", re.I), lambda m: ("", m[1])),
    (re.compile(r"^terminal\s+([\w+-]+)$", re.I), lambda m: ("", m[1])),
    (re.compile(r"^([A-Za-z][\w-]*)\.([\w+-]+)$"), lambda m: (m[1], m[2])),
    (re.compile(r"^(.+?),\s*pin\s+([\w+-]+)$", re.I), lambda m: (m[1], m[2])),
    (re.compile(r"^lead\s+(\w+)$", re.I), lambda m: ("lead", m[1])),
    (re.compile(rf"^({COLOURS})\s+lead$", re.I), lambda m: ("lead", m[1].lower())),
    (re.compile(r"^coil\s*([+-]|A1|A2)$", re.I), lambda m: ("coil", m[1])),
    (re.compile(r"^(A1|A2)\s*\([+-]\)\s*(?:M\d+\s+)?stud$", re.I), lambda m: ("", m[1].upper())),
    (re.compile(r"^(positive|negative)\s+terminal$", re.I), lambda m: ("+" if m[1].lower() == "positive" else "-", "")),
    (re.compile(r"^(load|line)\s+side$", re.I), lambda m: (m[1].upper(), "")),
    (re.compile(r"^(splice|stud)$", re.I), lambda m: (m[1].capitalize(), "")),
    (re.compile(r"^([\w-]+),\s*([A-Za-z][\w .+/-]*)$"), lambda m: (m[1], m[2])),  # "3, in", "Connector, V_in 5 V"
    (re.compile(r"^$"), lambda m: ("", "")),
]
# a cell without a pin number is a named terminal ("line stud", "fuse output", "TNC", "tip + ring", "loop in"), unless
# it is a placeholder or a question: those stay unparsed
_NAMED = re.compile(r"^(?!(?:pin|terminal)\b)[A-Za-z0-9][\w .,+/&-]*(?:\([^()?]*\)[\w .,+/&-]*)*$", re.I)
_PLACEHOLDER = re.compile(r"^(tbd|tbc|tba|n/?a|none|unknown|spare|see\b.*|check\b.*|ask\b.*)$", re.I)


def parse_cp(cell: Any) -> tuple[str, str] | None:
    """Connector / pin text -> (connector, pin), or None when it does not follow the grammar. A trailing "(note)" is
    allowed and ignored here (it stays in the cell text); text without a pin number is a named terminal (name, "")."""
    s = re.sub(r"\s+", " ", "" if cell is None else str(cell)).strip()
    m = _NOTE.match(s)
    if m: s = m[1]
    for pat, out in _FORMS:
        x = pat.match(s)
        if x: return out(x)
    return (s, "") if _NAMED.match(s) and not _PLACEHOLDER.match(s) else None


def format_cp(con: str, pin: str) -> str:
    """The canonical cell text for (connector, pin): the inverse of parse_cp."""
    if con == "": return f"pin {pin}" if pin else ""
    if con in ("lead", "coil") and pin: return f"{con} {pin}"
    if con in ("+", "-") and not pin: return "positive terminal" if con == "+" else "negative terminal"
    if con in ("LOAD", "LINE") and not pin: return f"{con.lower()} side"
    if con in ("Splice", "Stud") and not pin: return con.lower()
    if not pin: return con
    return f"{con}, pin {pin}" if _TOKEN.match(pin) else f"{con}, {pin}"


def norm_name(s: str) -> str:
    """A name for comparison: lower case, punctuation as spaces, single spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", s.lower())).strip()


_CODE = re.compile(r"^(?=.*[A-Z].*[A-Z0-9])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")


def name_code(name: str) -> str:
    """The code a harness connector name already carries ("Firewall connector PSW" -> PSW, "X-FW2"), else ""."""
    toks = [t.strip("()[],") for t in name.split()]
    return next((t for t in reversed(toks) if len(t) >= 2 and _CODE.match(t) and not re.match(r"^D-?SUB$", t)), "")


def _slug(name: str, kind: str) -> str:
    q = re.search(r"'([^']+)'", name) if kind in ("breaker", "fuse", "switch") else None
    s = re.sub(r"[^A-Z0-9]+", "-", (q[1] if q else name).upper()).strip("-")[:28].strip("-")
    return s or "DEV"


def classify(name: str, kinds: dict[str, str]) -> str:
    for k, pat in kinds.items():
        if re.search(pat, name, re.I): return k
    return "device"


def _cell(v: Any) -> str:
    return "" if v is None else str(v).strip()


def detect(path: Path) -> bool:
    """True when the first sheet's header row is the readable layout."""
    if path.suffix.lower() != ".xlsx": return False
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for row in wb.worksheets[0].iter_rows(max_row=10, values_only=True):
            if [_cell(v).lower() for v in row[:4]] == [h.lower() for h in HEAD[:4]]: return True
        return False
    finally: wb.close()


def read(cfg: Any, src: dict[str, Any]) -> Tables:
    """Wire records, display names and component overrides from a readable workbook; registers the generated codes'
    kinds in cfg (prefixes, harness connectors, sides) so the model builder classifies them."""
    from openpyxl import load_workbook
    path = cfg.root / src["path"]
    opts = dict(cfg.raw.get("readable") or {})
    kinds = {**KINDS, **(opts.get("kinds") or {})}
    can = re.compile(str(opts.get("can", CAN)), re.I)
    sides = {str(k).lower(): str(v) for k, v in {**SIDES, **(opts.get("sides") or {})}.items()}
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[src["sheet"]] if src.get("sheet") else wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        comp_rows = [list(r) for r in wb["Components"].iter_rows(values_only=True)] if "Components" in wb.sheetnames else []
    finally: wb.close()
    sheet = f"{path.name} [{ws.title}]"
    over: dict[str, dict[str, str]] = {}  # normalised name -> Components tab row (name, kind, code, location, part)
    if comp_rows:
        hd = [_cell(h).lower() for h in comp_rows[0]]
        for r in comp_rows[1:]:
            row = {h: _cell(v) for h, v in zip(hd, r) if h}
            if row.get("name"): over[norm_name(row["name"])] = row
    hr = next((i for i, r in enumerate(rows) if [_cell(v).lower() for v in r[:4]] == [h.lower() for h in HEAD[:4]]), None)
    if hr is None: raise SystemExit(f"{sheet}: no header row {HEAD[:4]}")
    col = {_cell(h).lower(): j for j, h in enumerate(rows[hr])}
    idx = [col.get(h.lower()) for h in HEAD]
    t = Tables()
    raw_of: dict[str, str] = {}   # device name as written -> raw device string ("CODE name")
    used: Counter[str] = Counter()

    def device(name: str) -> str:
        if name in raw_of: return raw_of[name]
        o = over.get(norm_name(name), {})
        kind = o.get("kind") or classify(name, kinds)
        code = o.get("code") or (kind == "harness" and name_code(name)) or PREFIX.get(kind, "") + _slug(name, kind)
        taken = tuple(p for p in (*cfg.breaker_prefixes, *cfg.bus_prefixes, cfg.splice_prefix, *cfg.relay_prefixes, *cfg.switch_prefixes,
                                  *PREFIX.values(), *cfg.harnesses) if p)
        if kind == "device" and not o.get("code") and (code.startswith(taken) or code in cfg.buses): code = "D-" + code  # never read as another kind
        base, k = code, 2
        while used[code]: code = f"{base}-{k}"; k += 1
        used[code] += 1
        raw = raw_of[name] = f"{code} {name}"
        t.display[raw] = name
        if kind == "harness": cfg.harnesses[code] = [name, code, ""]
        for lst, pre in (("breaker_prefixes", "CB-"), ("breaker_prefixes", "FU-"), ("bus_prefixes", "BB-"), ("relay_prefixes", "K-"),
                         ("switch_prefixes", "SW-")):
            if code.startswith(pre) and pre not in getattr(cfg, lst): getattr(cfg, lst).append(pre)
        if kind == "splice" and not code.startswith(cfg.splice_prefix): cfg.splice_prefix = "SP-"
        if o: t.components.append(Record({"device": raw, "name": name, "zone": o.get("location", ""), "part": o.get("part", "")}, sheet))
        return raw

    subsystem, header = "", ""
    for n, r in enumerate(rows[hr + 1:], hr + 2):
        cells = [_cell(r[j]) if j is not None and j < len(r) else "" for j in idx]
        vals = {f: (r[j] if j is not None and j < len(r) else None) for f, j in zip(FIELD, idx)}
        if not any(cells): continue
        if cells[0] and not any(cells[1:]): subsystem, header = cells[0], ""; continue
        if cells[1] and not cells[0] and not any(cells[2:]): header = cells[1]; continue
        d: dict[str, Any] = {"id": cells[0] or f"R{n}", "label": cells[0], "name": cells[1], "subsystem": subsystem}
        rd: dict[str, Any] = {"header": header, "from": vals["p1t"], "to": vals["p2t"], **({} if cells[0] else {"nolabel": True})}
        for e, f in ((1, "p1"), (2, "p2")):
            d[f] = device(cells[2 if e == 1 else 4]) if cells[2 if e == 1 else 4] else ""
            cp = parse_cp(vals[f"{f}t"])
            column = HEAD[3 if e == 1 else 5]
            if cp is None:
                cp = (_cell(vals[f"{f}t"]), "")
                rd.setdefault("unparsed", []).append(dict(sheet=sheet, row=n, column=column, text=_cell(vals[f"{f}t"])))
            d[f"{f}c"], d[f"{f}p"] = cp
            side = sides.get(cp[0].lower())
            if side: cfg.sides.setdefault(d[f].split()[0], {})[cp[0]] = side
        cans = ([cells[1]] if can.search(cells[1]) else []) + [cells[c] for c in (2, 4) if classify(cells[c], kinds) == "splice"
                                                               and re.search(r"\bG?CAN", cells[c], re.I)]
        if cans: d["cls"] = "CAN_L" if re.search(CAN_L, cans[0], re.I) else "CAN_H"  # no direction (bus order), never a one-way signal
        for f in ("bus", "amps", "awg", "length", "weight_g"):
            if vals[f] not in (None, ""): d[f] = vals[f]
        d["readable"] = rd
        t.rows.append(Record(d, sheet, n, {"p1": HEAD[2], "p2": HEAD[4], "p1c": HEAD[3], "p2c": HEAD[5], "label": HEAD[0], "amps": HEAD[7], "length": HEAD[9]}))
    uses = Counter(r.data[f] for r in t.rows for f in ("p1", "p2"))
    t.warnings += [f"{sheet}: device names '{a}' and '{b}' look like one device (schemagen fix names proposes the merge)"
                   for a, b in near_duplicates(list(raw_of), uses, raw_of)]
    return t


def _dist(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein distance, stopped at cap."""
    if abs(len(a) - len(b)) >= cap: return cap
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1): cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) >= cap: return cap
        prev = cur
    return min(prev[-1], cap)


def near_duplicates(names: list[str], uses: Counter[str] | None = None, raw_of: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """(variant, canonical) pairs of names that differ only in case, spacing or punctuation, or by a typo of at most
    two letters in a word longer than two letters. Never when their numbers differ, or when a short token differs
    (L/R, A/B). The canonical name is the more used one (then the first)."""
    uses = uses or Counter()
    count = (lambda n: uses[raw_of[n]]) if raw_of else (lambda n: uses[n])
    keys = {n: norm_name(n) for n in names}
    order = {n: i for i, n in enumerate(names)}
    out: list[tuple[str, str]] = []
    canon: dict[str, str] = {}
    for a in names:
        for b in names:
            if order[b] >= order[a] or b in canon or a in canon: continue
            ka, kb = keys[a], keys[b]
            same = ka == kb
            if not same:
                if re.findall(r"\d+", ka) != re.findall(r"\d+", kb) or min(len(ka), len(kb)) < 6: continue
                ta, tb = ka.split(), kb.split()
                if len(ta) != len(tb): continue
                diff = [(x, y) for x, y in zip(ta, tb) if x != y]
                if len(diff) != 1 or min(len(diff[0][0]), len(diff[0][1])) <= 2 or _dist(*diff[0]) > (1 if len(diff[0][0]) < 6 else 2): continue
            keep, drop = (a, b) if (count(a), -order[a]) > (count(b), -order[b]) else (b, a)
            canon[drop] = keep
            out.append((drop, keep))
    return out


def export(m: Any, path: Path) -> None:
    """Write the model in the readable layout: subsystem bars, component headers, wire rows in model order. Cells
    are written as read unless the model changed them (then in the grammar's canonical form)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    comp = {c.raw: c for c in m.components}
    wb = Workbook(); ws = wb.active; ws.title = "Wires"  # type: ignore[union-attr]
    ws.append(HEAD)  # type: ignore[union-attr]
    for c in ws[1]: c.font = Font(bold=True)  # type: ignore[union-attr]
    bar = PatternFill("solid", fgColor="D9E2F3")
    sub: str | None = None
    head: str | None = None
    for cd in m.conductors:
        rd = cd.extra.get("readable") or {}
        if cd.subsystem != sub:
            sub, head = cd.subsystem, None
            if sub:
                ws.append([sub])  # type: ignore[union-attr]
                n = ws.max_row  # type: ignore[union-attr]
                ws.merge_cells(start_row=n, start_column=1, end_row=n, end_column=len(HEAD))  # type: ignore[union-attr]
                ws.cell(n, 1).fill, ws.cell(n, 1).font = bar, Font(bold=True)  # type: ignore[union-attr]
        if rd.get("header", "") != (head or ""):
            head = rd.get("header", "")
            if head:
                ws.append([None, head])  # type: ignore[union-attr]
                ws.cell(ws.max_row, 2).font = Font(bold=True, italic=True)  # type: ignore[union-attr]
        row: list[Any] = [None if rd.get("nolabel") else cd.label or None, cd.name or None]
        for t, key in ((cd.from_, "from"), (cd.to, "to")):
            c = comp.get(t.device)
            written = rd.get(key)
            same = (parse_cp(written) or (_cell(written), "")) == (t.connector, t.pin)  # unedited: write the cell as read
            cp = written if same else format_cp(t.connector, t.pin)
            row += [(c.name if c else t.device) or None, cp if cp != "" else None]
        g = cd.gauge
        num = lambda v, key: cd.extra.get(key) if v is None else v  # text in a number column ("TBD") is kept in extra
        row += [cd.bus or None, num(cd.current_a, "amps"), int(g) if g.isdigit() else (g or None), num(cd.length_m, "length"),
                cd.extra.get("weight_g")]
        ws.append(row)  # type: ignore[union-attr]
    for j, w in enumerate((8, 26, 26, 22, 26, 22, 9, 11, 7, 10, 10), 1):
        ws.column_dimensions[ws.cell(1, j).column_letter].width = w  # type: ignore[union-attr]
    wb.save(path)
