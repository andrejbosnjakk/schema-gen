"""One sheet of a drawing PDF read as a wiring diagram: the wires with their labels, where each wire end lands (pin, node or flag), the nets that dots
and end-to-end joins make, the wire table, the title block. Knows how a drawing looks (a wire is a casing over a core, a dot makes a junction, a
crossing without a dot is nothing, a pin number sits next to the end of its stub) but nothing of the engine."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from .pdfread import Outline, Pt, Run, Sheet

TOL = 0.25                      # mm: points closer than this are one point
LABEL = re.compile(r"^(?P<label>\S+) (?P<gauge>\d+(?:\.\d+)?(?: ?AWG| ?mm\S*)?|[A-Za-z?]+)(?: (?P<colour>[A-Z]{2,8}))?$")
FLAG_TO = re.compile(r"^(?:to|->|→)\s+(?P<far>.+)$")
FLAG_CONT = re.compile(r"continues on sheet (?P<sheet>\d+)")
FLAG_MORE = re.compile(r"^\+\s*(?P<n>\d+) more wires")
DRAWING = re.compile(r"(?:drawing|dwg)\s+(?P<d>[\w.+-]+)", re.I)
SHEETREF = re.compile(r"sheet\s+(?P<s>\d+)", re.I)
RGB = {"BK": (0, 0, 0), "WH": (1, 1, 1), "GY": (.6, .6, .6), "PK": (1, .4, .8), "RD": (1, 0, 0), "OG": (1, .5, 0), "YE": (1, 1, 0), "OL": (.44, .5, 0),
       "GN": (0, 1, 0), "TQ": (0, 1, 1), "LB": (.63, .87, 1), "BU": (0, .4, 1), "VT": (.5, 0, 1), "BN": (.54, .35, .34), "BG": (.8, .72, .45),
       "IV": (.96, .94, .82), "SL": (.44, .5, .56), "CU": (.84, .47, .37), "SN": (.67, .67, .67), "SR": (.52, .53, .55), "GD": (1, .81, .5)}


COLOUR = re.compile("^(?:%s)(?:%s)?$" % ("|".join(RGB), "|".join(RGB)))


def split_label(s: str) -> tuple[str, str, str] | None:
    """Wire text `L05 22 AWG RD` / `P52 22 shielded BU` / `L9 TBD` as (label, gauge without unit word, colour code); None if it is a single word."""
    t = s.split()
    if len(t) < 2: return None
    colour = t[-1] if len(t) >= 3 and COLOUR.match(t[-1]) else ""
    return t[0], re.sub(r"\s*AWG\s*", " ", " ".join(t[1:-1] if colour else t[1:])).strip(), colour


def colour_of(rgb: tuple[float, float, float]) -> str:
    """The nearest colour code to a drawn colour (the code's usual colour, by eye, not the engine's palette)."""
    return min(RGB, key=lambda k: sum((a - b) ** 2 for a, b in zip(RGB[k], rgb)))


def same_colour(code: str, rgb: tuple[float, float, float]) -> bool:
    """A label's colour code agrees with the drawn colour: same nearest code, or silver/grey families, or an unknown code (nothing to compare)."""
    base = code[:2]
    if base not in RGB: return True
    near = colour_of(rgb)
    return near == base or {near, base} <= {"SN", "SR", "GY"}


@dataclass
class End:
    """Where a wire end lands. kind: pin (comp, conn, pin tokens), node (comp), flag (text), none."""
    kind: str
    p: Pt
    comp: str = ""
    conn: str | None = None          # None: the drawing does not say
    pin: str | None = None           # None: the drawing does not say; "?" says something that is not there
    text: str = ""
    net: int = -1
    toks: list[str] = field(default_factory=list)


@dataclass
class WireObs:
    j: int
    pts: list[Pt]
    labels: list[str]
    gauge: str
    colour: str
    rgb: tuple[float, float, float]
    ends: list[End]
    label_runs: list[Run] = field(default_factory=list)
    conflict: str = ""            # the wire's labels (it may carry several) disagree


@dataclass
class FlagObs:
    kind: str                      # continuation, off_sheet, summary
    text: str
    outline: Outline
    wire: int                      # index of the wire that ends here, -1 if none
    sheet: int | None = None       # sheet named (continuation, or a sheet reference)
    drawing: str | None = None     # drawing named
    far: str = ""
    n: int = 0                     # summary: wires covered


@dataclass
class TableRow:
    label: str
    wire: str
    frm: str
    to: str
    sheet: int | None              # the sheet the row speaks of (None: this one)
    y: float


@dataclass
class SheetObs:
    n: int
    page: Sheet
    wires: list[WireObs] = field(default_factory=list)
    flags: list[FlagObs] = field(default_factory=list)
    rows: list[TableRow] = field(default_factory=list)
    title: dict[str, str] = field(default_factory=dict)
    frame: tuple[float, float, float, float] = (0, 0, 0, 0)
    strip: tuple[float, float, float, float] = (0, 0, 0, 0)
    table: tuple[float, float, float, float] | None = None
    anomalies: list[str] = field(default_factory=list)       # junction problems seen while rebuilding nets
    crossings: int = 0
    orphan_labels: list[Run] = field(default_factory=list)


# ------------------------------------------------------------------ geometry helpers
def _eq(a: Pt, b: Pt) -> bool: return abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL


def _on_seg(p: Pt, a: Pt, b: Pt, tol: float = TOL) -> bool:
    """p lies on segment a-b (an axis-aligned one, ends included)."""
    return min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol and min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol and \
        (abs(a[0] - b[0]) <= tol and abs(p[0] - a[0]) <= tol or abs(a[1] - b[1]) <= tol and abs(p[1] - a[1]) <= tol)


def _interior(p: Pt, a: Pt, b: Pt) -> bool: return _on_seg(p, a, b) and not _eq(p, a) and not _eq(p, b)


def _dist_edge(p: Pt, pts: list[Pt]) -> float:
    best = 1e9
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = 0 if dx == dy == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy))
    return best


def _inside(p: Pt, o: Outline) -> bool:
    if not (o.x0 <= p[0] <= o.x1 and o.y0 <= p[1] <= o.y1): return False
    c = False
    for (x1, y1), (x2, y2) in zip(o.pts, o.pts[1:]):
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1: c = not c
    return c


def _cross(a: Pt, b: Pt, c: Pt, d: Pt) -> Pt | None:
    """Where two axis-aligned segments of different direction cross in both interiors; None otherwise."""
    for (h1, h2), (v1, v2) in (((a, b), (c, d)), ((c, d), (a, b))):
        if abs(h1[1] - h2[1]) <= TOL and abs(v1[0] - v2[0]) <= TOL:
            x, y = v1[0], h1[1]
            if min(h1[0], h2[0]) + TOL < x < max(h1[0], h2[0]) - TOL and min(v1[1], v2[1]) + TOL < y < max(v1[1], v2[1]) - TOL: return (x, y)
    return None


class _UF:
    def __init__(s) -> None: s.p: dict[Any, Any] = {}
    def find(s, x: Any) -> Any:
        s.p.setdefault(x, x)
        while s.p[x] != x: s.p[x] = s.p[s.p[x]]; x = s.p[x]
        return x
    def union(s, a: Any, b: Any) -> None: s.p[s.find(a)] = s.find(b)


# ------------------------------------------------------------------ the sheet
def title_fields(page: Sheet) -> dict[str, str]:
    """The title block: the value under each caption (SHEET, PROJECT, SCOPE, REV, DATE, DRAWN BY, SOURCE; a long value goes on to a second line, read as one:
    a scope is an id, so its lines join without a space) and the drawing title (the large text left of SHEET, or its bold lines when it is long)."""
    caps = {"SHEET", "PROJECT", "SCOPE", "REV", "DATE", "DRAWN BY", "SOURCE"}
    out: dict[str, str] = {}
    for r in page.runs:
        if r.s in caps and r.top > page.h * 0.75:
            below = sorted((q for q in page.runs if abs(q.x0 - r.x0) < 1.0 and 2.0 < q.top - r.top < 11.0), key=lambda q: q.top)
            out[r.s.lower().replace(" ", "_")] = ("" if r.s == "SCOPE" else " ").join(q.s for q in below)
            if r.s == "SHEET":
                big = [q for q in page.runs if q.top > page.h * 0.75 and q.em > 4.0 and q.x1 <= r.x0 + 0.5]
                if big: out["title"] = max(big, key=lambda q: q.em).s
                else: out["title"] = " ".join(q.s for q in sorted((q for q in page.runs if q.top > page.h * 0.75 and r.x0 - 100.5 <= q.x0 and q.x1 <= r.x0 + 0.5 and q.top < r.top + 8), key=lambda q: q.top))
    return out


def _areas(page: Sheet) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    """Frame (the largest box) and the strip below the drawing area (title block, legend, notes: the boxes along the frame's foot)."""
    if not page.boxes: return (0, 0, page.w, page.h), (0, page.h, page.w, page.h)
    f = max(page.boxes, key=lambda b: (b.x1 - b.x0) * (b.y1 - b.y0))
    foot = [b for b in page.boxes if b is not f and b.y1 >= f.y1 - 0.5 and b.y0 > f.y0 + (f.y1 - f.y0) * 0.6]
    top = min((b.y0 for b in foot), default=f.y1)
    return (f.x0, f.y0, f.x1, f.y1), (f.x0, top, f.x1, f.y1)


def _label_of(run: Run) -> re.Match[str] | None:
    return LABEL.match(re.sub(r"\s+", " ", run.s))


def parse_sheet(page: Sheet, lead: Any, conns: dict[str, set[str]]) -> SheetObs:
    """Reads a sheet. `lead(text)`: the component a text starts with, by any of its names, and the rest; `conns`: connector names by component id."""
    ob = SheetObs(page.n, page)
    ob.title = title_fields(page)
    ob.frame, ob.strip = _areas(page)
    sx0, sy0, sx1, sy1 = ob.strip
    drawing_runs = [r for r in page.runs if r.top < sy0 - 0.2]
    _table(ob, drawing_runs)
    if ob.table: drawing_runs = [r for r in drawing_runs if not (ob.table[1] - 0.3 <= r.top <= ob.table[3])]
    flags = _flags(ob, drawing_runs)
    flag_runs = {id(r) for f in flags for r in drawing_runs if f.outline.x0 - .2 <= r.x0 and r.x1 <= f.outline.x1 + .2 and f.outline.y0 - .2 <= r.top and r.bot <= f.outline.y1 + .2}
    free = [r for r in drawing_runs if id(r) not in flag_runs]
    wires = page.wires
    nets, wend, anomalies = _nets(page, ob.strip)
    ob.anomalies = anomalies
    # wires: labels
    lab_runs = []
    for r in free:
        j = _wire_under(r, wires)
        if j is not None and (sl := split_label(r.s)): lab_runs.append((r, j, sl))
        elif (m := _label_of(r)) and ((m.group("colour") and COLOUR.match(m.group("colour")) and m.group("gauge")[0].isdigit()) or "AWG" in r.s or "mm" in r.s): ob.orphan_labels.append(r)
    used: set[int] = set()
    obs: list[WireObs] = []
    for j, w in enumerate(wires):
        obs.append(WireObs(j, w.pts, [], "", "", w.rgb, []))
    for r, j, (lab, gauge, colour) in lab_runs:
        o = obs[j]
        if o.labels and (o.gauge, o.colour, o.labels[0]) != (gauge, colour, lab): o.conflict = f"{o.labels[0]} {o.gauge} {o.colour} / {lab} {gauge} {colour}"
        o.labels.append(lab); o.label_runs.append(r)
        o.gauge, o.colour = gauge, colour
        used.add(id(r))
    for fo in flags:
        for j, w in enumerate(wires):
            for e in (0, 1):
                p = w.pts[0] if e == 0 else w.pts[-1]
                if _dist_edge(p, fo.outline.pts) <= TOL + 0.1 and fo.wire < 0:
                    fo.wire = j
                    obs[j].ends.append(End("flag", p, text=fo.text, net=wend[(j, e)]))
    ob.flags = flags
    # the rest of the ends
    _ends(page, [r for r in free if id(r) not in used], flags, nets, wend, lead, conns, obs)
    ob.wires = obs
    ob.crossings = _crossings(wires)
    return ob


def _wire_under(r: Run, wires: list[Any]) -> int | None:
    """The wire a label sits on: a horizontal stretch just below the text and as wide as the text overlaps."""
    best, bd = None, 1e9
    for j, w in enumerate(wires):
        for a, b in zip(w.pts, w.pts[1:]):
            if abs(a[1] - b[1]) > TOL: continue
            ov = min(max(a[0], b[0]), r.x1) - max(min(a[0], b[0]), r.x0)
            d = a[1] - r.bot
            if ov > 0.4 * (r.x1 - r.x0) and -0.8 <= d <= 1.8 and abs(d) < bd: best, bd = j, abs(d)
    return best


def _table(ob: SheetObs, runs: list[Run]) -> None:
    """The wire table, if the sheet has one: rows below the caption row LABEL / WIRE / FROM / TO / SEE. A row whose cells are too long goes on to further lines
    (a line with no label belongs to the row above); a line `Sheet 3` says which sheet the rows after it speak of. The SEE cell is read as the end of the TO cell."""
    heads = [r for r in runs if r.s == "LABEL"]
    for h in heads:
        row = [r for r in runs if abs(r.cy - h.cy) < 0.6 and r.s in ("WIRE", "FROM", "TO", "SEE")]
        if {r.s for r in row} != {"WIRE", "FROM", "TO", "SEE"}: continue
        xs = {"LABEL": h.x0, **{r.s: r.x0 for r in row}}
        body = sorted((r for r in runs if r.top > h.bot - 0.1), key=lambda r: (round(r.cy * 2), r.x0))
        lines: dict[int, list[Run]] = {}
        for r in body: lines.setdefault(round(r.cy / 2.5), []).append(r)
        sheet: int | None = None
        last = h.bot
        acc: list[tuple[dict[str, str], int | None, float]] = []
        for k in sorted(lines):
            rs = lines[k]
            cols = {"LABEL": "", "WIRE": "", "FROM": "", "TO": "", "SEE": ""}
            for r in sorted(rs, key=lambda r: r.x0):
                c = max((n for n in xs if xs[n] <= r.x0 + 1.5), key=lambda n: xs[n], default="LABEL")
                cols[c] = (cols[c] + " " + r.s).strip()
            if cols["LABEL"] and not any(cols[c] for c in ("WIRE", "FROM", "TO", "SEE")) and (m := re.match(r"Sheet (\d+)", cols["LABEL"])):
                sheet, last = int(m.group(1)), max(r.bot for r in rs)
                acc.append(({}, None, 0.0))                 # a heading ends the row above
                continue
            if cols["LABEL"]: acc.append((cols, sheet, rs[0].cy))
            elif acc and acc[-1][0] and 0 < rs[0].top - last < 2.0:         # a further line of the row above
                for c in cols: acc[-1][0][c] = (acc[-1][0][c] + " " + cols[c]).strip()
            else: continue
            last = max(r.bot for r in rs)
        ob.rows += [TableRow(c["LABEL"], c["WIRE"], c["FROM"], (c["TO"] + " " + c["SEE"]).strip(), s, y) for c, s, y in acc if c]
        ob.table = (min(r.x0 for r in row + [h]) - 8, h.top - 0.5, ob.frame[2], last + 1.0)
        return


def _flags(ob: SheetObs, runs: list[Run]) -> list[FlagObs]:
    """Flags: outlines (hexagon or box) whose text says where a wire goes on."""
    out: list[FlagObs] = []
    for o in ob.page.outlines:
        if o.x1 - o.x0 < 6 or o.y1 - o.y0 > 14: continue
        inside = sorted((r for r in runs if o.x0 - .2 <= r.x0 and r.x1 <= o.x1 + .2 and o.y0 - .2 <= r.top and r.bot <= o.y1 + .2), key=lambda r: (round(r.top), r.x0))
        inside = [r for r in inside if not (r.s.isdigit() and r.x1 - o.x0 < 8 and len(inside) > 1)]   # the sheet number in a continuation flag's own cell
        text = " ".join(r.s for r in inside)
        text = re.sub(r"\s+", " ", text).strip()
        cm, mo, to = FLAG_CONT.search(text), FLAG_MORE.match(text), FLAG_TO.match(re.sub(r"^\d+ ", "", text))
        if not (cm or mo or to): continue
        f = FlagObs("continuation" if cm else "summary" if mo else "off_sheet", text, o, -1)
        if cm: f.sheet = int(cm.group("sheet")); f.far = text[cm.end():].lstrip(": ").strip()
        elif mo: f.n = int(mo.group("n")); f.far = text
        else: f.far = to.group("far")  # type: ignore[union-attr]
        sm, dm = SHEETREF.search(text), DRAWING.search(text)
        if sm and not cm: f.sheet = int(sm.group("s"))
        if dm: f.drawing = dm.group("d")
        out.append(f)
    return out


def _nets(page: Sheet, strip: tuple[float, float, float, float]) -> tuple[_UF, dict[tuple[int, int], Any], list[str]]:
    """Joins: wire ends and straight symbol lines that meet end to end (two of them) are one net; at a dot everything that ends there or passes through is;
    three or more ends without a dot are joined and reported; a crossing, or an end on the side of another line, joins nothing (a dot there is reported)."""
    uf = _UF()
    an: list[str] = []
    wends: list[tuple[Any, Pt]] = [(("w", j, e), (w.pts[0] if e == 0 else w.pts[-1])) for j, w in enumerate(page.wires) for e in (0, 1)]
    lines: list[tuple[Any, Pt, Pt]] = [(("s", i), a, b) for i, (a, b, w, st) in enumerate(page.segs) if st and (abs(a[0] - b[0]) <= TOL or abs(a[1] - b[1]) <= TOL) and a[1] < strip[1] - 0.5]
    for wk, _ in wends: uf.find(wk)
    for lk, _a, _b in lines: uf.find(lk)
    ends: list[tuple[Any, Pt]] = [*wends, *((k, a) for k, a, b in lines), *((k, b) for k, a, b in lines)]
    dots = [d for d in page.dots if d[1] < strip[1] - 0.5]
    # group the end points
    groups: list[tuple[Pt, list[Any]]] = []
    for k, p in ends:
        for g in groups:
            if _eq(g[0], p): g[1].append(k); break
        else: groups.append((p, [k]))
    for p, ks in groups:
        dot = any(_eq(d, p) for d in dots)
        thru = [k for k, a, b in lines if _interior(p, a, b) and k not in ks]
        wthru = [j for j, w in enumerate(page.wires) if any(_interior(p, a, b) for a, b in zip(w.pts, w.pts[1:]))]
        if dot:
            for k in ks[1:] + thru: uf.union(ks[0], k)
            for k in thru[1:]: uf.union(thru[0], k)
            if wthru: an.append(f"dot on the body of a wire at {p[0]:.1f},{p[1]:.1f}")
        else:
            n = len(ks) + len(thru)
            if n >= 3:
                for k in ks[1:] + thru: uf.union(ks[0], k)
                an.append(f"junction of {n} lines without a dot at {p[0]:.1f},{p[1]:.1f}")
            elif len(ks) == 2: uf.union(ks[0], ks[1])
            if wthru and any(k[0] == "w" for k in ks): an.append(f"wire end on the body of another wire without a dot at {p[0]:.1f},{p[1]:.1f}")
    # dots that join several lines passing through (a bar) but have no end of their own at the dot
    for d in dots:
        if any(_eq(d, p) for p, _ in groups): continue
        thru = [k for k, a, b in lines if _on_seg(d, a, b)]
        for k in thru[1:]: uf.union(thru[0], k)
        if any(_on_seg(d, a, b) for w in page.wires for a, b in zip(w.pts, w.pts[1:])): an.append(f"dot on the body of a wire at {d[0]:.1f},{d[1]:.1f}")
        if not thru: an.append(f"dot on nothing at {d[0]:.1f},{d[1]:.1f}")
    wend = {(j, e): uf.find(("w", j, e)) for j in range(len(page.wires)) for e in (0, 1)}
    return uf, wend, an


def _ends(page: Sheet, free: list[Run], flags: list[FlagObs], uf: _UF, wend: dict[tuple[int, int], Any], lead: Any, conns: dict[str, set[str]],
          obs: list[WireObs]) -> None:
    """Resolves every wire end that is not at a flag: a node (it shares a net with a dot) or a pin. Appends to each wire's `ends` in point order."""
    net_dots: dict[Any, list[Pt]] = {}
    lines = [(("s", i), a, b) for i, (a, b, w, st) in enumerate(page.segs) if st]
    for d in page.dots:
        for k, a, b in lines:
            if _on_seg(d, a, b): net_dots.setdefault(uf.find(k), []).append(d)
        for j, w in enumerate(page.wires):
            for e in (0, 1):
                if _eq(d, w.pts[0] if e == 0 else w.pts[-1]): net_dots.setdefault(uf.find(("w", j, e)), []).append(d)
    cand: list[tuple[Run, str]] = []
    cont: set[int] = set()         # lines that only go on a name from the line above
    for r in free:
        if id(r) in cont: continue
        c, more = _lead_run(r, free, lead)
        if c: cand.append((r, c)); cont |= {id(q) for q in more}
    ends_pts = [pt for w in page.wires for pt in (w.pts[0], w.pts[-1])]
    touch = lambda p: any(_eq(a, p) or _eq(b, p) for _, a, b in lines) or any(_dist_edge(p, o.pts) <= 0.35 for o in page.outlines)  # noqa: E731
    outs = sorted((o for o in page.outlines if o.x1 - o.x0 >= 6 and o.y1 - o.y0 >= 6), key=lambda o: -(o.x1 - o.x0) * (o.y1 - o.y0))
    flag_outs = {id(f.outline) for f in flags}
    outs = [o for o in outs if id(o) not in flag_outs]
    for j, w in enumerate(page.wires):
        pend = [e for e in obs[j].ends if e.kind == "flag"]
        flagged = {_which(w, e.p) for e in pend}
        ends = []
        for e in (0, 1):
            if e in flagged: continue
            p = w.pts[0] if e == 0 else w.pts[-1]
            q = w.pts[1] if e == 0 else w.pts[-2]
            nid = wend[(j, e)]
            if nid in net_dots:
                ends.append(_node(p, nid, net_dots[nid], cand, free, uf))
            else:
                ends.append(_pin(p, q, nid, lines, free, outs, cand, conns, uf, ends_pts) if touch(p) else End("pin", p, "?", net=nid))   # an end on nothing is a pin of nothing
        obs[j].ends = sorted(obs[j].ends + ends, key=lambda x: (x.p[0], x.p[1]))


def _which(w: Any, p: Pt) -> int: return 0 if _eq(w.pts[0], p) else 1


def _node(p: Pt, nid: Any, dots: list[Pt], cand: list[tuple[Run, str]], free: list[Run], uf: _UF) -> End:
    """A splice, bus or ground, or a pin that several wires share (they meet at dots): the component whose name stands nearest the net's dots, and what is
    printed right beside a dot (a pin name)."""
    best, bd = None, 1e9
    for r, c in cand:
        d = min(max(r.x0 - q[0], 0, q[0] - r.x1) ** 2 + max(r.top - q[1], 0, q[1] - r.bot) ** 2 for q in dots) ** .5
        if d < bd: best, bd = c, d
    near = sorted((min(abs(r.x0 - q[0]) if r.x0 > q[0] else abs(q[0] - r.x1) for q in dots if abs(r.cy - q[1]) <= 1.4 and -0.5 <= (r.x0 - q[0]) <= 8 or -0.5 <= (q[0] - r.x1) <= 8), r.s)
                  for r in free if any(abs(r.cy - q[1]) <= 1.4 and (-0.5 <= r.x0 - q[0] <= 8 or -0.5 <= q[0] - r.x1 <= 8) for q in dots))
    toks = [s for _, s in near if not any(r.s == s or c == s for r, c in cand)]   # a name printed beside the dot is the part's name, not a pin
    if best is None or bd > 14: return End("node", p, "?", net=nid, toks=toks)
    return End("node", p, best, net=nid, toks=toks)


def _pin(p: Pt, q: Pt, nid: Any, lines: list[Any], free: list[Run], outs: list[Outline], cand: list[tuple[Run, str]], conns: dict[str, set[str]], uf: _UF, ends_pts: list[Pt]) -> End:
    """A pin: which symbol is behind the end of the wire (the outline it points into, else the nearest name), the connector header above it and the
    pin number or name standing next to it."""
    # direction into the symbol: along the stub that ends here, else against the wire
    far = None
    for k, a, b in lines:
        if uf.find(k) == nid:
            if _eq(a, p): far = b
            elif _eq(b, p): far = a
            if far: break
    if far is None or _eq(far, p): far = p; dx, dy = p[0] - q[0], p[1] - q[1]
    else: dx, dy = far[0] - p[0], far[1] - p[1]
    n = math.hypot(dx, dy) or 1
    ux, uy = dx / n, dy / n
    probe = (far[0] + ux * 1.0, far[1] + uy * 1.0)
    comp, box = "", None
    for o in outs:
        if _inside(probe, o):
            heads = [(r, c) for r, c in cand if o.x0 - .2 <= r.x0 and r.x1 <= o.x1 + .2 and o.y0 - .2 <= r.top and r.bot <= o.y1 + .2 and r.top - o.y0 < 12]
            if heads: comp, box = min(heads, key=lambda x: (x[0].top, x[0].x0))[1], o; break
    if not comp:
        near = [(min(max(r.x0 - p[0], 0, p[0] - r.x1) ** 2 + max(r.top - p[1], 0, p[1] - r.bot) ** 2, 1e9) ** .5, c) for r, c in cand]
        near = [x for x in near if x[0] <= 30]
        if near: comp = min(near, key=lambda x: x[0])[1]
    # tokens on the pin's row, nearest first, on the symbol's side
    row = [r for r in free if abs(r.cy - p[1]) <= 1.4] if abs(uy) < .5 else [r for r in free if abs(r.cx - p[0]) <= 1.4]
    toks: list[tuple[float, str]] = []
    for r in row:
        if abs(uy) < .5:
            if ux > 0 and r.x0 >= p[0] - 0.3: d = r.x0 - p[0]
            elif ux < 0 and r.x1 <= p[0] + 0.3: d = p[0] - r.x1
            else: continue
        else:
            if uy > 0 and r.top >= p[1] - 0.3: d = r.top - p[1]
            elif uy < 0 and r.bot <= p[1] + 0.3: d = p[1] - r.bot
            else: continue
        if d <= 16 and (box is None or (box.x0 - .3 <= r.x0 and r.x1 <= box.x1 + .3)): toks.append((d, r.s))
    toks.sort()
    names = conns.get(comp, set())
    conn = None
    if box is not None and names - {""}:
        hs = [r for r in free if r.s in names and not any(abs(q[1] - r.cy) <= 1.4 and r.x0 - 8 <= q[0] <= r.x1 + 8 for q in ends_pts) and box.x0 - .2 <= r.x0 and r.x1 <= box.x1 + .2 and box.y0 <= r.top and r.bot <= p[1] + .5]
        if hs:
            top = max(r.bot for r in hs)
            row_h = [r for r in hs if top - r.bot < 1.0]
            conn = min(row_h, key=lambda r: abs(r.cx - p[0])).s
    pin = toks[0][1] if toks else ("?" if box is not None else None)
    return End("pin", p, comp or "?", conn, pin, net=nid, toks=[t for _, t in toks])


def _crossings(wires: list[Any]) -> int:
    n = 0
    for i, w in enumerate(wires):
        bi = (min(p[0] for p in w.pts), min(p[1] for p in w.pts), max(p[0] for p in w.pts), max(p[1] for p in w.pts))
        for v in wires[i + 1:]:
            if v.pts is w.pts: continue
            if max(p[0] for p in v.pts) < bi[0] or min(p[0] for p in v.pts) > bi[2] or max(p[1] for p in v.pts) < bi[1] or min(p[1] for p in v.pts) > bi[3]: continue
            n += sum(1 for a, b in zip(w.pts, w.pts[1:]) for c, d in zip(v.pts, v.pts[1:]) if _cross(a, b, c, d))
    return n


def _lead_run(r: Run, free: list[Run], lead: Any) -> tuple[str | None, list[Run]]:
    """The component a text run names, and the further lines of its name. A name that goes on to a second or third line (a long box name) is read with its
    lines: the shortest run of stacked lines (same left edge or centre, the next just below) that is a whole name; else the run alone."""
    s, last = r.s, r
    more: list[Run] = []
    for _ in range(3):
        c, rest = lead(s)
        if c and not rest: return str(c), more
        nxt = next((q for q in free if (abs(q.x0 - last.x0) < 0.3 or abs(q.cx - last.cx) < 0.3) and 0 <= q.top - last.bot < 2.4 and abs(q.em - last.em) < 0.05), None)
        if nxt is None: break
        s, last = s + ("" if s.endswith("-") else " ") + nxt.s, nxt
        more.append(nxt)
    c = lead(r.s)[0]
    return (str(c) if c else None), []
