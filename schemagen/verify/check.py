"""The drawing verifier: do the PDFs say exactly what the wire list says? Each drawing PDF is read as a technician reads it (pdfread, parse), compared with
the model of the source (expect), checked for legibility (legible) and for completeness over the whole book. Result: a JSON-ready dict.

Independent of the drawing engine on purpose: it imports nothing from schemagen.drawing, the renderers or the app (a test enforces it), so a bug shared by
engine and verifier cannot hide."""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..core.model import is_link
from . import expect as X
from . import legible
from .parse import End, SheetObs, TableRow, WireObs, parse_sheet, same_colour
from .pdfread import read

NAMES = {"BK": "black", "WH": "white", "GY": "grey", "PK": "pink", "RD": "red", "OG": "orange", "YE": "yellow", "OL": "olive", "GN": "green", "TQ": "turquoise",
         "LB": "light blue", "BU": "blue", "VT": "violet", "BN": "brown", "BG": "beige", "IV": "ivory", "SL": "slate", "CU": "copper", "SN": "silver", "SR": "silver",
         "GD": "gold"}
CONNECTIVITY = ("missing", "extra", "ends", "gauge", "colour", "label", "net", "table", "junction", "book", "toc", "unread")   # kinds that mean "the PDF differs from the wire list"


def words(code: str) -> str:
    base, stripe = code[:2], code[2:4]
    return NAMES.get(base, code) + (f" / {NAMES[stripe]} stripe" if stripe in NAMES else "") if base in NAMES else code


def _is_cont(e: End) -> bool: return e.kind == "flag" and bool(re.search(r"continues on sheet", e.text))


def _toks(s: str) -> list[str]: return [t for t in re.split(r"[\s,()]+", s) if t]


def end_matches(e: End, t: X.Term, ex: X.Expected) -> bool:
    """A resolved wire end is the model's terminal `t` (component, connector, pin)."""
    comp, conn, pin = t
    node = ex.kind.get(comp) in ("splice", "bus")
    if e.kind == "node":   # dots: a splice or bus, or a pin that several wires share (then the pin is printed beside the dots)
        if e.comp != comp: return False
        return node or (not pin and not e.toks) or (bool(pin) and (not e.toks or pin in e.toks)) or (not pin and conn in e.toks)
    if e.kind != "pin" or node or e.comp != comp: return False
    if conn and e.conn not in (None, conn) and not (e.pin is None and e.conn == "?"): return False
    if conn and e.conn == "?": return False
    if pin: return e.pin is None or e.pin == pin
    return not e.toks or conn in e.toks   # the terminal is the connector itself: nothing is printed beside it, or its name


def describes(ex: X.Expected, text: str, e: End | None = None, t: X.Term | None = None) -> bool:
    """A table cell or flag text names a wire end (the component by id or display name, then the connector and pin)."""
    comp, rest = ex.lead(text)
    if e is not None and e.kind in ("node", "pin"):
        if comp is None or comp != e.comp: return False
        if e.kind == "pin" or (e.kind == "node" and e.toks and ex.kind.get(e.comp) not in ("splice", "bus")):
            if e.kind == "node": return not e.toks or _has_pin(rest, e.toks[0])
            if e.pin not in (None, "?") and not _has_pin(rest, e.pin): return False
            if e.conn not in (None, "?", "") and e.conn.lower() not in rest.lower(): return False
        return True
    if t is not None:
        c, conn, pin = t
        if ex.kind.get(c) in ("splice", "bus"): return comp == c   # a splice or bus is named, not its terminal
        return comp == c and (not pin or _has_pin(rest, pin)) and (not conn or conn.lower() in rest.lower() or conn.replace(" ", "").lower() in rest.replace(" ", "").lower())
    return False


def _has_pin(rest: Any, pin: str) -> bool:
    """The pin stands in the text as a word of its own, or after the connector's hyphen (`J1-14`); a pin may have spaces (`V_in 5 V`, `- / case`)."""
    s = " ".join(rest) if isinstance(rest, list) else rest
    return re.search(r"(?<![\w])" + re.escape(pin) + r"(?![\w])", s) is not None or re.search(r"-" + re.escape(pin) + r"(?![\w])", s) is not None


class Drawing:
    """One drawing PDF: its sheets and what they show, by conductor label."""

    def __init__(self, path: Path, ex: X.Expected):
        self.path, self.ex = path, ex
        self.name = path.stem
        self.pages = read(path)
        self.sheets: list[SheetObs] = [parse_sheet(p, ex.lead, ex.conns) for p in self.pages]
        self.scope = self.sheets[0].title.get("scope", "") if self.sheets else ""
        if self.scope and ex.scope(self.scope) is None or self.scope.endswith(".."):   # a long id is cut short in the title block: the file name says it
            self.scope_cut = self.scope
            self.scope = next((f"component:{i}" for i in ex.kind if f"component-{i}" == self.name), self.scope)
        self.findings: list[dict[str, Any]] = []
        self.recs: dict[str, list[tuple[int, WireObs]]] = defaultdict(list)
        for sh in self.sheets:
            for w in sh.wires:
                if w.labels: self.recs[w.labels[0]].append((sh.n, w))
        self.table_labels: set[str] = {r.label for sh in self.sheets for r in sh.rows}
        self.table_only = 0
        self.covered = 0

    def add(self, kind: str, msg: str, sheet: int | None = None, **kw: Any) -> None:
        self.findings.append(dict(kind=kind, drawing=self.name, sheet=sheet, msg=msg, **kw))


def check_drawing(d: Drawing, source: dict[str, str] | None = None, others: dict[str, Drawing] | None = None) -> None:
    """All per-drawing checks; the findings go to d.findings."""
    if not d.sheets: d.add("unread", "no pages"); return
    _title(d, source)
    _wires(d)
    _nets(d)
    _tables(d)
    _flags(d, others)
    for sh in d.sheets:
        for a in sh.anomalies: d.add("junction", a, sh.n)
        for r in sh.orphan_labels: d.add("label", f"label text '{r.s}' is not on any wire", sh.n)
        for f in legible.findings(sh): d.add(f.pop("kind"), f.pop("msg"), sh.n)


def _title(d: Drawing, source: dict[str, str] | None) -> None:
    m = len(d.sheets)
    if getattr(d, "scope_cut", ""): d.add("title_truncated", f"title block scope '{d.scope_cut}' is cut short")
    for sh in d.sheets:
        t = sh.title
        if t.get("sheet") != f"{sh.n} of {m}": d.add("title", f"title block says sheet '{t.get('sheet')}' on page {sh.n} of {m}", sh.n)
        for k in ("scope", "project", "title"):
            if t.get(k) != d.sheets[0].title.get(k): d.add("title", f"title block {k} differs from sheet 1", sh.n)
        if not t.get("rev"): d.add("title_revision_missing", "title block has no revision", sh.n)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", t.get("date", "")): d.add("title_date_missing", f"title block date '{t.get('date', '')}'", sh.n)
        src = t.get("source", "")
        h = re.search(r"#([0-9a-f]{8,64})", src)
        if not h: d.add("title_hash_missing", f"title block source '{src}' carries no content hash", sh.n)
        elif source:
            if not source["sha256"].startswith(h.group(1)): d.add("title", f"source hash {h.group(1)} is not the hash of {source['name']} ({source['sha256'][:8]})", sh.n)
        if source and h and ".." not in src and source["name"] not in src: d.add("title", f"title block source '{src}' is not '{source['name']}'", sh.n)


def _terms(w: list[tuple[int, WireObs]]) -> tuple[list[End], list[End], list[End]]:
    """Terminal ends, far-end flags (off-sheet) and continuation flags of every piece of a conductor."""
    t: list[End] = []
    f: list[End] = []
    c: list[End] = []
    for _, p in w:
        for e in p.ends: (c if _is_cont(e) else f if e.kind == "flag" else t if e.kind in ("pin", "node") else f).append(e)
    seen: set[tuple[Any, ...]] = set()
    uniq: list[End] = []
    for e in t:   # a splice drawn on two sheets is one end
        k = (e.kind, e.comp, e.conn, e.pin)
        if k not in seen: seen.add(k); uniq.append(e)
    t = uniq
    return t, f, c


def _wires(d: Drawing) -> None:
    ex = d.ex
    want = d.ex.scope(d.scope)
    if want is None:
        d.add("scope_unknown", f"scope '{d.scope}' is not checked (only component, harness, selection, system)"); return
    by_label: dict[str, list[X.Cond]] = defaultdict(list)
    for i in want: by_label[ex.conds[i].label].append(ex.conds[i])
    for sh in d.sheets:
        bylab: dict[str, list[WireObs]] = defaultdict(list)
        for w in sh.wires:
            if not w.labels:
                if not any(e.kind == "flag" and re.match(r"^\+\s*\d+ more wires", e.text) for e in w.ends): d.add("label", "a wire has no label text on it", sh.n)
                continue
            if len(set(w.labels)) > 1: d.add("label", f"a wire carries two labels {w.labels}", sh.n)
            if w.conflict: d.add("label", f"the labels of one wire disagree: {w.conflict}", sh.n)
            bylab[w.labels[0]].append(w)
        for k, ws in bylab.items():   # one label on several wires is a loop drawn as two flags: each piece must end in a flag
            if len(ws) > 1 and not all(any(e.kind == "flag" and not _is_cont(e) for e in w.ends) for w in ws): d.add("label", f"label {k} is on {len(ws)} wires of the sheet", sh.n)
    covered = sum(f.n for sh in d.sheets for f in sh.flags if f.kind == "summary")
    for lab, cs in by_label.items():
        if lab not in d.recs:
            if lab in d.table_labels: d.table_only += 1; continue
            if covered >= len(cs): covered -= len(cs); continue     # behind a summary flag: listed on the bus's own drawing (D116)
            for cc in cs: d.add("missing", f"wire {lab} is not in the drawing", conductor=cc.id)
            continue
        if len(cs) > 1: continue   # two conductors with one label: not decidable from the label
        c = cs[0]
        pieces = d.recs[lab]
        t, f, _ = _terms(pieces)
        g = {p.gauge for _, p in pieces}
        if g != {c.gauge}: d.add("gauge", f"wire {lab}: drawn {sorted(g)}, wire list {c.gauge!r}", pieces[0][0], conductor=c.id)
        col = {p.colour for _, p in pieces}
        if col != {c.colour}: d.add("colour", f"wire {lab}: label says {sorted(col)}, wire list {c.colour!r}", pieces[0][0], conductor=c.id)
        if c.colour:
            for n, p in pieces:
                if not same_colour(c.colour, p.rgb): d.add("colour", f"wire {lab}: drawn in a colour that is not {c.colour}", n, conductor=c.id)
        _ends(d, c, t, f, pieces)
    extra = set(d.recs) - set(by_label)
    for lab in sorted(extra): d.add("extra", f"wire {lab} is drawn but the wire list does not put it in this drawing", d.recs[lab][0][0])
    d.covered = covered


def _ends(d: Drawing, c: X.Cond, t: list[End], f: list[End], pieces: list[tuple[int, WireObs]]) -> None:
    ex = d.ex
    sheet = None
    bad = f"wire {c.label}: ends at {{}}, wire list says {_term(c.a)} and {_term(c.b)}"
    far_of = lambda e: re.sub(r"^(?:to|->|→)\s+", "", e.text)  # noqa: E731
    if len(t) == 2 and not f:
        if not ((end_matches(t[0], c.a, ex) and end_matches(t[1], c.b, ex)) or (end_matches(t[0], c.b, ex) and end_matches(t[1], c.a, ex))):
            d.add("ends", bad.format(f"{_show(t[0])} and {_show(t[1])}"), sheet, conductor=c.id)
    elif len(t) == 1 and len(f) == 1:
        for mine, other, oi in ((c.a, c.b, 2), (c.b, c.a, 1)):
            if end_matches(t[0], mine, ex) and _names_end(d, far_of(f[0]), c, other, oi): return
        d.add("ends", bad.format(f"{_show(t[0])} and a flag '{f[0].text}'"), sheet, conductor=c.id)
    elif len(t) == 2 and len(f) == 2 and len(pieces) == 2:   # a loop drawn as two flags: each piece's flag names the other piece's terminal
        for (mine, other), (m2, o2) in (((c.a, c.b), (c.b, c.a)), ((c.b, c.a), (c.a, c.b))):
            if all(end_matches(a, m, ex) and _names_end(d, far_of(next(e for e in p.ends if e.kind == "flag")), c, o, 2 if o is c.b else 1)
                   for (a, m, o), (_, p) in zip(((t[0], mine, other), (t[1], m2, o2)), pieces)): return
        d.add("ends", bad.format(f"{_show(t[0])} and {_show(t[1])} with flags '{f[0].text}', '{f[1].text}'"), sheet, conductor=c.id)
    else: d.add("ends", f"wire {c.label}: {len(t)} pin/node ends and {len(f)} flags found, expected two ends", sheet, conductor=c.id)


def _run_names(d: Drawing, text: str, c: X.Cond, end: int) -> bool:
    """A text (a flag, a table cell) names where the run behind end 1 or 2 of conductor c goes: each `->` step is a component on that run."""
    reach = d.ex.reach(c, end)
    ids = [d.ex.lead(seg)[0] for seg in re.split(r"\s*->\s*", text)]
    return bool(ids) and all(i in reach for i in ids)


def _names_end(d: Drawing, far: str, c: X.Cond, t: X.Term, end: int) -> bool:
    """A flag's text names where the far end of conductor c is: every component it mentions is on the run that leaves that end, and when it names the
    terminal's own component it gives the connector and pin."""
    if not _run_names(d, far, c, end): return False
    seg = re.split(r"\s*->\s*", far)[0]
    comp, rest = d.ex.lead(seg)
    if comp != t[0] or not rest: return True   # a flag may name the component without its terminal
    return describes(d.ex, seg, None, t)


def _show(e: End) -> str:
    return f"{e.comp} {e.conn or ''} {e.pin or ''}".replace("  ", " ").strip() if e.kind == "pin" else f"{e.comp} (node)"


def _term(t: X.Term) -> str: return " ".join(x for x in t if x) or "?"


def _nets(d: Drawing) -> None:
    """Dots and joins make nets; a net must hold one model node, and the wires of a splice or bus on a sheet must be one net."""
    ex = d.ex
    for sh in d.sheets:
        sites: dict[Any, set[tuple[str, ...]]] = defaultdict(set)
        by_node: dict[str, set[Any]] = defaultdict(set)
        for w in sh.wires:
            for e in w.ends:
                if e.kind == "node":
                    sites[e.net].add((e.comp,))
                    if ex.kind.get(e.comp) in ("splice", "bus"): by_node[e.comp].add(e.net)    # one node; a harness pin drawn as a bar is one node per pin
                elif e.kind == "pin":
                    key = (e.comp, "pin", e.pin or "") if ex.kind.get(e.comp) == "harness" else (e.comp, e.conn or "", e.pin or "")
                    sites[e.net].add(key)
        for net, ks in sites.items():
            if len({k[0] for k in ks}) > 1 or (len(ks) > 1 and any(len(k) == 1 for k in ks)): d.add("net", f"{sorted(ks)} are joined in the drawing", sh.n)
        for comp, nets in by_node.items():
            if len(nets) > 1: d.add("net", f"the wires of {comp} are not all joined in the drawing ({len(nets)} separate nets)", sh.n)


def _tables(d: Drawing) -> None:
    """The wire tables of a drawing hold every wire once: under the first sheet that draws it (or, for a wire only a summary flag speaks of, under the sheet of
    that flag). Every row is held against the lines drawn on its sheet, and every drawn wire must have its row."""
    ex = d.ex
    rows: dict[int, list[TableRow]] = defaultdict(list)
    for sh in d.sheets:
        for r in sh.rows: rows[r.sheet or sh.n].append(r)
    n_sheets = len(d.sheets)
    by_label = {c.label: c for c in ex.conds}
    count = Counter(c.label for c in ex.conds)
    first = {lab: min(n for n, _ in recs) for lab, recs in d.recs.items()}
    listed: dict[str, int] = {}
    for k, rs in sorted(rows.items()):
        if k > n_sheets: d.add("table", f"the wire table speaks of sheet {k}, which does not exist"); continue
        sh = d.sheets[k - 1]
        drawn: dict[str, list[WireObs]] = defaultdict(list)
        for w in sh.wires:
            if w.labels: drawn[w.labels[0]].append(w)
        cover = sum(f.n for f in sh.flags if f.kind == "summary")
        undrawn = 0
        for r in rs:
            if r.label in listed and count[r.label] == 1: d.add("table", f"label {r.label} twice in the wire tables (sheets {listed[r.label]} and {k})", k)
            listed.setdefault(r.label, k)
            ws = drawn.get(r.label)
            if ws is None:
                undrawn += 1
                c = by_label.get(r.label)
                if c is None: d.add("table", f"table row {r.label} is not a wire of the wire list", k); continue
                if r.label in first and not (k < first[r.label] and cover): d.add("table", f"table row {r.label} is under sheet {k}, which does not draw it (sheet {first[r.label]} does)", k)
                _row_vs_model(d, r, c, k)
                continue
            if k != first[r.label]: d.add("table", f"table row {r.label} is under sheet {k}, but the wire is first drawn on sheet {first[r.label]}", k)
            w = ws[0]
            if r.wire:
                cw = words(w.colour) if w.colour else ""
                gtxt = r.wire[:-len(cw)] if cw and r.wire.endswith(cw) else r.wire
                if is_link(w.gauge): gtxt = gtxt.removesuffix(", no wire")    # a bus strip is a link, not a wire
                if cw and not r.wire.endswith(cw): d.add("table", f"table row {r.label}: '{r.wire}' but the wire is {w.colour} ({cw})", k)
                if re.sub(r"\s*AWG", "", gtxt).strip() != w.gauge: d.add("table", f"table row {r.label}: gauge '{r.wire}' but the wire is {w.gauge}", k)
            _row_vs_wire(d, r, ws, k)
        if undrawn > cover: d.add("table", f"{undrawn - cover} table rows of sheet {k} are for wires that are not drawn and no summary flag covers them", k)
    for lab, n in sorted(first.items()):
        if lab not in listed: d.add("table", f"wire {lab} has no row in the wire tables of the drawing (it is drawn on sheet {n})", n)


def _row_vs_wire(d: Drawing, r: TableRow, ws: list[WireObs], k: int) -> None:
    ends = ws[0].ends if len(ws) == 1 else [e for w in ws for e in w.ends if e.kind != "flag"]
    texts = [r.frm, r.to]
    for first in (0, 1):
        ok = True
        for e, text in zip(ends, [texts[first], texts[1 - first]]):
            ok = ok and _row_end(d.ex, e, text)
        if ok and len(ends) == 2: return
    d.add("table", f"table row {r.label}: '{r.frm}' -> '{r.to}' does not match the ends drawn ({', '.join(_show(e) if e.kind != 'flag' else e.text for e in ends)})", k)


def _row_end(ex: X.Expected, e: End, text: str) -> bool:
    if e.kind == "flag":
        far = " ".join(re.sub(r"\s*\(drawing [^)]*\)$", "", re.sub(r"^(?:\d+ )?(?:continues on sheet \d+:?|to|->|→)\s*", "", e.text)).split())
        t = " ".join(re.sub(r"\s*\(drawing [^)]*\)$", "", re.sub(r"\s*\(sheet \d+\)$", "", text)).split())
        if t.endswith("..") and far.endswith(".."): a, b = t[:-2].rstrip(), far[:-2].rstrip(); return a.startswith(b) or b.startswith(a)
        if t.endswith("..") and not far.endswith(".."): return far.startswith(t[:-2].rstrip())
        if far.endswith(".."): return t.startswith(far[:-2].rstrip())   # a flag text cut short by the drawing: the table has all of it
        return far == t or not far or t.startswith(far) or far.startswith(t)   # the table may add the long name in brackets
    return describes(ex, text, e)


def _row_vs_model(d: Drawing, r: TableRow, c: X.Cond, k: int) -> None:
    """Rows of wires covered by a summary flag: the lines say nothing, so the row is held against the wire list."""
    for first in (c.a, c.b):
        other = c.b if first is c.a else c.a
        if describes(d.ex, r.frm, None, first) and (describes(d.ex, r.to, None, other) or _run_names(d, r.to, c, 2 if other is c.b else 1)): break
    else: d.add("table", f"table row {r.label}: '{r.frm}' -> '{r.to}' is not {_term(c.a)} -> {_term(c.b)}", k)
    cw = words(c.colour) if c.colour else ""
    gtxt = r.wire[:-len(cw)] if cw and r.wire.endswith(cw) else r.wire
    if is_link(c.gauge): gtxt = gtxt.removesuffix(", no wire")
    if r.wire and re.sub(r"\s*AWG", "", gtxt).strip() != c.gauge: d.add("table", f"table row {r.label}: '{r.wire}' but the wire list says {c.gauge} {cw}", k)
    d.table_only += 1


def _flags(d: Drawing, others: dict[str, Drawing] | None) -> None:
    """Every flag must name the drawing and the sheet it goes on to, and that sheet must show the wire's far end. Continuations inside this PDF are
    checked against the sheet they name (the wire must be there and point back); off-sheet flags that name a drawing are checked in that drawing
    (when the other drawings are at hand: `others` is None for a PDF checked alone)."""
    for sh in d.sheets:
        for f in sh.flags:
            w = sh.wires[f.wire] if f.wire >= 0 else None
            lab = w.labels[0] if w and w.labels else ""
            if f.kind == "summary":   # `+ 59 more wires on GND-BUS (drawing GND-BUS, sheet 1-3)`: the drawing and a sheet of it that exist
                if f.drawing is None or f.sheet is None: d.add("flag_no_target", f"summary flag '{f.text}' names no drawing and no sheet", sh.n); continue
                tg = d if f.drawing in (d.name, d.scope.split(":")[-1]) else (others or {}).get(f.drawing) or (others or {}).get("component-" + f.drawing)
                if others is None and tg is None: continue
                if tg is None or not 1 <= f.sheet <= len(tg.sheets): d.add("flag", f"summary flag '{f.text}': drawing {f.drawing} sheet {f.sheet} does not exist", sh.n)
                continue
            if f.drawing is None and f.sheet is None: d.add("flag_no_target", f"flag '{f.text}' names neither a drawing nor a sheet", sh.n)
            elif f.drawing is None: d.add("flag_no_drawing", f"flag '{f.text}' names sheet {f.sheet} but no drawing", sh.n)
            elif f.sheet is None: d.add("flag_no_sheet", f"flag '{f.text}' names drawing {f.drawing} but no sheet", sh.n)
            if w is None: d.add("flag", f"flag '{f.text}' has no wire ending in it", sh.n); continue
            if not lab: continue
            target: Drawing | None
            if f.drawing is None or (others or {}).get(f.drawing) is d or f.drawing == d.name or f.drawing == d.scope.split(":")[-1]: target, tn = d, f.sheet
            else: target, tn = (others or {}).get(f.drawing) or (others or {}).get("component-" + f.drawing), f.sheet
            if others is None and target is None: continue
            if f.drawing is not None and target is None: d.add("flag", f"flag '{f.text}': no drawing {f.drawing} among the PDFs", sh.n); continue
            if tn is None: continue
            if target is None or not 1 <= tn <= len(target.sheets): d.add("flag", f"flag '{f.text}': sheet {tn} does not exist", sh.n); continue
            there = [x for n, x in target.recs.get(lab, []) if n == tn]
            if not there: d.add("flag", f"flag '{f.text}': wire {lab} is not on sheet {tn}", sh.n); continue
            if f.kind == "continuation" and target is d and not _reaches(d, lab, tn, sh.n, w):
                d.add("flag", f"flag '{f.text}': wire {lab} on sheet {tn} does not lead on to the other end of the wire", sh.n)


def _reaches(d: Drawing, lab: str, n: int, here: int, mine: WireObs) -> bool:
    """The wire `lab` on sheet n, or on the sheets its own continuation flags lead to, ends at the end of the conductor that this piece (`mine`, on sheet `here`) does not."""
    cs = [c for c in d.ex.conds if c.label == lab]
    mt = [e for e in mine.ends if e.kind in ("pin", "node")]
    if len(cs) != 1 or not mt: return True   # not decidable here (unknown or loop-split label); the other checks report it
    c = cs[0]
    other = c.b if end_matches(mt[0], c.a, d.ex) else c.a
    seen, todo = {here}, [n]
    while todo:
        k = todo.pop()
        if k in seen or not 1 <= k <= len(d.sheets): continue
        seen.add(k)
        for x in [x for m, x in d.recs.get(lab, []) if m == k]:
            if any(e.kind in ("pin", "node") and end_matches(e, other, d.ex) for e in x.ends): return True
            if any(e.kind == "flag" and not _is_cont(e) and _names_end(d, re.sub(r"^(?:to|->|→)\s+", "", e.text), c, other, 2 if other is c.b else 1) for e in x.ends): return True
            todo += [int(m.group(1)) for e in x.ends if _is_cont(e) and (m := re.search(r"sheet (\d+)", e.text))]
    return False


def _digest(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def summary(rep: dict[str, Any]) -> str:
    """The report as a short human summary."""
    t = rep["totals"]
    out = [f"{t['drawings']} drawings, {t['sheets']} sheets, {t['wire_pieces']} wires drawn, {t['conductor_checks']} conductor checks against {t['conductors']} source wires.",
           f"connectivity findings: {t['connectivity']}  ({', '.join(f'{k} {v}' for k, v in sorted(t['by_kind'].items()) if k in CONNECTIVITY) or 'none'})",
           f"flag findings: {t['flags']}  title findings: {t['title']}  crossings: {t['crossings']}",
           "legibility: " + (", ".join(f"{k} {v}" for k, v in sorted(t["legibility"].items())) or "none")]
    for name, dr in rep["drawings"].items():
        bad = {k: v for k, v in dr["by_kind"].items()}
        if bad: out.append(f"  {name}: " + ", ".join(f"{k} {v}" for k, v in sorted(bad.items())) + f"  (sheets {dr['sheets']}, crossings {dr['crossings']})")
    out.append("verdict: " + ("PDFs agree with the wire list" if t["connectivity"] == 0 else f"{t['connectivity']} differences between PDFs and wire list"))
    return "\n".join(out)
