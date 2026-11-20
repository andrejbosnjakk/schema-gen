"""The overview PDF against the wire list: `overview.pdf` has one page per selection (power distribution, CAN network, all wires). Each page is read like any
drawing (parse), and the set of wires it shows must be exactly the set the wire list puts on that page: label, both ends (part, connector, pin), gauge and
colour of every conductor; dots join, crossings do not; the legibility rules apply. Imports nothing of schemagen.drawing."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from . import expect as X
from . import legible
from .check import Drawing, _show, _term, end_matches
from .parse import COLOUR, End, SheetObs, WireObs, parse_sheet, same_colour, split_label
from .pdfread import Run, Sheet, read

NEAR = 2.0     # mm: a label this close to a wire that is not its own reads as belonging to that one too


def _stack(runs: list[Run]) -> list[Run]:
    """A label that is stacked on two or three lines (`L05` / `22 AWG RD`) is one text: the lines that share an edge, one under the other, join when together they read
    as a label with a gauge and a colour."""
    out: list[Run] = []
    rest = sorted(runs, key=lambda r: (r.top, r.x0))
    used: set[int] = set()
    for a in rest:
        if id(a) in used: continue
        if " " not in a.s:
            chain, last = [a], a
            while len(chain) < 3:
                nxt = next((b for b in rest if id(b) not in used and b is not last and 0 <= b.top - last.bot < 1.6 and abs(b.em - last.em) < 0.05
                            and (abs(b.x0 - last.x0) < 0.3 or abs(b.x1 - last.x1) < 0.3)), None)
                if nxt is None: break
                chain.append(nxt); last = nxt
                sl = split_label(" ".join(r.s for r in chain))
                if sl and sl[2] and COLOUR.match(sl[2]):
                    used |= {id(r) for r in chain}
                    out.append(Run(" ".join(r.s for r in chain), min(r.x0 for r in chain), max(r.x1 for r in chain), chain[0].top, chain[-1].bot, a.em, a.bold))
                    break
            if id(a) in used: continue
        out.append(a)
    return out


def pages_of(path: Path, ex: X.Expected) -> list[Drawing]:
    """One pseudo drawing per page of the overview PDF, so the per-drawing checks run on each page with that page's selection as its scope."""
    out: list[Drawing] = []
    for k, pg in enumerate(read(path), 1):
        pg.runs = _stack(pg.runs)
        d = Drawing.__new__(Drawing)
        d.path, d.ex, d.name, d.pages = path, ex, f"overview-{k}", [pg]
        ob: SheetObs = parse_sheet(pg, ex.lead, ex.conns)
        _taps(ob, ex)
        d.sheets, d.findings = [ob], []
        kind = X.PAGES.get(ob.title.get("title", ""), "")
        d.scope = f"overview:{kind}" if kind else ""
        d.recs = defaultdict(list)
        for w in ob.wires:
            if w.labels: d.recs[w.labels[0]].append((1, w))
        d.table_labels, d.table_only, d.covered = set(), 0, 0
        out.append(d)
    return out


def _taps(ob: SheetObs, ex: X.Expected) -> None:
    """A harness connector is a bar with a tap to each pin: the bar's name stands above it, the pin number beside the tap (the part and pin of a wire that ends there)."""
    pg = ob.page
    near = lambda a, b: abs(a[0] - b[0]) < 0.3 and abs(a[1] - b[1]) < 0.3  # noqa: E731
    for w in ob.wires:
        for e in w.ends:
            if e.kind != "pin" or e.comp != "?": continue
            tap = next(((a, b) for a, b, _, st in pg.segs if st and abs(a[1] - b[1]) < 0.01 and (near(a, e.p) or near(b, e.p))), None)
            if tap is None: continue
            q = tap[1] if near(tap[0], e.p) else tap[0]
            bar = next(((a, b) for a, b, _, st in pg.segs if st and abs(a[0] - b[0]) < 0.01 and abs(a[0] - q[0]) < 0.3 and min(a[1], b[1]) - 0.3 <= q[1] <= max(a[1], b[1]) + 0.3), None)
            if bar is None: continue
            top = min(bar[0][1], bar[1][1])
            comp = next((c for r in sorted((r for r in pg.runs if 0 <= top - r.bot <= 14 and r.x0 - 0.5 <= q[0] <= r.x1 + 0.5), key=lambda r: top - r.bot)
                         for c, rest in [ex.lead(r.s)] if c and not rest), None)
            left = e.p[0] < q[0]
            pin = next((r.s for r in pg.runs if e.p[1] - 4.0 <= r.bot <= e.p[1] + 0.5 and (abs(r.x1 - (q[0] - 1.5)) < 0.8 if left else abs(r.x0 - (q[0] + 1.5)) < 0.8)), None)
            if comp: e.comp, e.pin, e.toks = comp, pin, [pin] if pin else []


def _ground(pg: Sheet, p: tuple[float, float], q: tuple[float, float]) -> bool:
    """A ground mark stands at the end p of a wire that comes from q: three short bars across the line of the wire, just beyond p."""
    dx, dy = p[0] - q[0], p[1] - q[1]
    n = (dx * dx + dy * dy) ** .5 or 1.0
    ux, uy = dx / n, dy / n
    bars = 0
    for a, b, _, _ in pg.segs:
        ln = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** .5
        if not 0.5 < ln <= 4.5 or abs((b[0] - a[0]) * ux + (b[1] - a[1]) * uy) > 0.2: continue       # a bar across the wire
        m = ((a[0] + b[0]) / 2 - p[0], (a[1] + b[1]) / 2 - p[1])
        if 1.0 <= m[0] * ux + m[1] * uy <= 5.0 and abs(m[0] * uy - m[1] * ux) <= 0.3: bars += 1
    return bars >= 2


def _wires(d: Drawing) -> None:
    """The wires of the page against the wire list: every conductor of the selection once, no other; gauge, colour and both ends of each (a splice or bus by the
    wires that meet on it, a ground by its mark, a pin by its part, connector and pin)."""
    ex, ob = d.ex, d.sheets[0]
    want = [ex.conds[i] for i in sorted(ex.scope(d.scope) or ())]
    by_label: dict[str, list[X.Cond]] = defaultdict(list)
    for c in want: by_label[c.label].append(c)
    bylab: dict[str, list[WireObs]] = defaultdict(list)
    for w in ob.wires:
        if not w.labels: d.add("label", "a wire has no label text on it", 1); continue
        if len(set(w.labels)) > 1: d.add("label", f"a wire carries two labels {w.labels}", 1)
        if w.conflict: d.add("label", f"the labels of one wire disagree: {w.conflict}", 1)
        bylab[w.labels[0]].append(w)
    for k, ws in bylab.items():
        if len(ws) > 1: d.add("label", f"label {k} is on {len(ws)} wires of the sheet", 1)
    net: dict[Any, set[str]] = defaultdict(set)         # the labels of the wires that meet in a drawn net
    for w in ob.wires:
        for e in w.ends:
            if e.kind == "node" and w.labels: net[e.net].add(w.labels[0])
    node = lambda comp: {c.label for c in want if comp in (c.a[0], c.b[0])}  # noqa: E731

    def matches(w: WireObs, e: End, t: X.Term) -> bool:
        i = 0 if e.p == w.pts[0] else -1
        if t[0] in ex.ground: return _ground(d.pages[0], e.p, w.pts[1 if i == 0 else -2])
        if ex.kind.get(t[0]) in ("splice", "bus"):      # the wires of a splice or bus meet at dots, one at each end
            return e.kind == "node" and e.comp in ("?", t[0]) and net[e.net] == node(t[0]) and (ex.kind[t[0]] == "bus" or any(abs(x - e.p[0]) < 5.6 and abs(y - e.p[1]) < 0.3 for x, y in d.pages[0].dots))
        return end_matches(e, t, ex)
    for lab, cs in by_label.items():
        if lab not in d.recs:
            for c in cs: d.add("missing", f"wire {lab} is not in the drawing", 1, conductor=c.id)
            continue
        if len(cs) > 1 or len(d.recs[lab]) > 1: continue        # one label on several conductors or wires: not decidable from the label
        c, w = cs[0], d.recs[lab][0][1]
        if w.gauge != c.gauge: d.add("gauge", f"wire {lab}: drawn {w.gauge!r}, wire list {c.gauge!r}", 1, conductor=c.id)
        if w.colour != c.colour or (c.colour and not same_colour(c.colour, w.rgb)): d.add("colour", f"wire {lab}: drawn {w.colour!r}, wire list {c.colour!r}", 1, conductor=c.id)
        if len(w.ends) != 2: d.add("ends", f"wire {lab}: {len(w.ends)} ends found, expected two", 1, conductor=c.id); continue
        e1, e2 = w.ends
        if not ((matches(w, e1, c.a) and matches(w, e2, c.b)) or (matches(w, e1, c.b) and matches(w, e2, c.a))):
            d.add("ends", f"wire {lab}: ends at {_show(e1)} and {_show(e2)}, wire list says {_term(c.a)} and {_term(c.b)}", 1, conductor=c.id)
    for lab in sorted(set(d.recs) - set(by_label)): d.add("extra", f"wire {lab} is drawn but the wire list does not put it on this page", 1)


def _bars(ob: SheetObs) -> None:
    """A harness connector is drawn as a bar with a tap each side of a pin: the two taps meet the bar without a dot, which is how a pin reads, not a junction."""
    keep = []
    for a in ob.anomalies:
        if a.startswith("junction of 3 lines without a dot at "):
            x, y = (float(v) for v in a.rsplit(" at ", 1)[1].split(","))
            seg = lambda s: (min(s[0][0], s[1][0]) - 0.01, min(s[0][1], s[1][1]) - 0.01, max(s[0][0], s[1][0]) + 0.01, max(s[0][1], s[1][1]) + 0.01)  # noqa: E731
            hs = [seg(s) for s in ob.page.segs if abs(s[0][1] - y) < 0.01 and abs(s[1][1] - y) < 0.01]
            if any(h[2] - 0.01 <= x <= h[2] + 0.01 for h in hs) and any(h[0] - 0.01 <= x <= h[0] + 0.01 for h in hs): continue
        keep.append(a)
    ob.anomalies = keep


def _page(d: Drawing, k: int, n: int, source: dict[str, str] | None) -> None:
    """Every finding of one page; they go to d.findings."""
    ob = d.sheets[0]
    t = ob.title
    if not d.scope: d.add("title", f"page {k} is titled {t.get('title')!r}, which is none of the overview's pages ({', '.join(X.PAGES)})", 1)
    if t.get("sheet") != f"{k} of {n}": d.add("title", f"title block says sheet {t.get('sheet')!r} on page {k} of {n}", 1)
    if t.get("scope") != "overview": d.add("title", f"title block scope is {t.get('scope')!r}, not 'overview'", 1)
    if source and t.get("source") and source["name"] not in t["source"]: d.add("title", f"title block source {t.get('source')!r} is not {source['name']!r}", 1)
    if d.scope: _wires(d)
    _bars(ob)
    for a in ob.anomalies: d.add("junction", a, 1)
    for r in ob.orphan_labels: d.add("label", f"label text '{r.s}' is not on any wire", 1)
    for w in ob.wires:      # a label must read as belonging to one wire: no other wire within NEAR mm of it
        for r in w.label_runs:
            for j, o in enumerate(ob.wires):
                if j == w.j: continue
                if any(min(max(r.x0 - max(a[0], b[0]), 0, min(a[0], b[0]) - r.x1) ** 2 + max(r.top - max(a[1], b[1]), 0, min(a[1], b[1]) - r.bot) ** 2, 1e9) ** .5 < NEAR
                       for a, b in zip(o.pts, o.pts[1:])):
                    d.add("label", f"label '{r.s}' sits next to another wire ({'/'.join(o.labels) or '?'})", 1)
                    break
    for f in legible.findings(ob, True): d.add(f.pop("kind"), f.pop("msg"), 1)


def check_overview(ex: X.Expected, path: Path, source: dict[str, str] | None = None) -> tuple[list[Drawing], list[dict[str, Any]]]:
    """The overview PDF's pages and all their findings (kinds as in check_drawings). Three pages are expected, in the order power, can, all."""
    ds = pages_of(path, ex)
    out: list[dict[str, Any]] = []
    if [X.PAGES.get(d.sheets[0].title.get("title", ""), "") for d in ds] != ["power", "can", "all"]:
        out.append(dict(kind="title", drawing="overview", sheet=None, msg=f"the overview should have the pages {', '.join(X.PAGES)} in that order"))
    for k, d in enumerate(ds, 1):
        _page(d, k, len(ds), source)
        out += d.findings
    return ds, out
