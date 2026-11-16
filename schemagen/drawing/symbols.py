"""Symbols of the wiring-diagram engine: `build(item, x, y, sides)` turns a scene item (docs/drawing-model.md) into the geometry's
symbol (absolute mm, w and h multiples of GRID, every anchor on a grid point on the symbol's edge) and its texts, which lie inside
the reserved box (x, y, w, h) and touch none of the symbol's own lines, so layout can treat a symbol as one rectangle. Also the
flag builder, the title block, the legend and the notes. Data the model lacks (mating half, part numbers) is left out, never invented.

Anchor rules by symbol (sides maps an anchor id to "L" or "R"; "T" for a ground):
- block: pins on the edge, 5 mm pitch; default side "R", far_end items "L"; spare pins have no anchor.
- harness: near half on the left edge, far half on the right edge (sides can swap the halves).
- splice, bus (per stud), ground (T, all pins the same point): anchor on the node itself; defaults L, R, T.
- breaker, fuse, terminator, battery: two terminals, the first "L", the other "R" (battery: + on R, - on L when the names say).
- switch, relay: contact terminals a/com on L, b/no/nc on R, coil a1 on L and a2 on R.
- dcdc: input pins L, output pins R (read from the pin names), else first half L, second half R."""
from __future__ import annotations

import re
from typing import Any

from .geometry import Anchor, Flag, Prim, Symbol, Text
from .style import (BOLD_ROLES, DETAIL_STROKE, FRAME_STROKE, GREY_ROLES, SIZE, SIZE_TITLE, SYMBOL_STROKE, areas, baseline_dy, ceil_to, em,  # noqa: F401
                    fit, text_h, text_w, wrap)

Item = dict[str, Any]
N, T_, K = SYMBOL_STROKE, DETAIL_STROKE, FRAME_STROKE
_OPP = {"L": "R", "R": "L"}


def _r(v: float) -> float:
    return round(v + 0.0, 3)


class _B:
    """Collects prims, texts and anchors of one symbol in its own coordinates; x, y of the symbol shift them to the sheet."""

    def __init__(s, it: Item, x: float, y: float) -> None:
        s.it, s.ox, s.oy, s.model = it, x, y, it["model"]
        s.prims: list[Prim] = []; s.texts: list[Text] = []; s.anchors: list[Anchor] = []
        s.taps: list[dict[str, str]] = []

    def line(s, x1: float, y1: float, x2: float, y2: float, st: str = N, dash: bool = False) -> None:
        p: Prim = dict(kind="line", stroke=st, x1=_r(s.ox + x1), y1=_r(s.oy + y1), x2=_r(s.ox + x2), y2=_r(s.oy + y2))  # type: ignore[typeddict-item]
        if dash: p["dash"] = True
        s.prims.append(p)

    def rect(s, x: float, y: float, w: float, h: float, st: str = N, fill: str = "none") -> None:
        s.prims.append(dict(kind="rect", stroke=st, fill=fill, x=_r(s.ox + x), y=_r(s.oy + y), w=_r(w), h=_r(h)))  # type: ignore[typeddict-item]

    def poly(s, pts: list[tuple[float, float]], closed: bool = False, st: str = N, fill: str = "none") -> None:
        s.prims.append(dict(kind="polyline", stroke=st, fill=fill, closed=closed, points=[[_r(s.ox + a), _r(s.oy + b)] for a, b in pts]))  # type: ignore[typeddict-item]

    def circle(s, cx: float, cy: float, r: float, st: str = N, fill: str = "none") -> None:
        s.prims.append(dict(kind="circle", stroke=st, fill=fill, cx=_r(s.ox + cx), cy=_r(s.oy + cy), r=_r(r)))  # type: ignore[typeddict-item]

    def arc(s, cx: float, cy: float, r: float, a0: float, a1: float, st: str = N) -> None:
        s.prims.append(dict(kind="arc", stroke=st, cx=_r(s.ox + cx), cy=_r(s.oy + cy), r=_r(r), a0=a0, a1=a1))  # type: ignore[typeddict-item]

    def text(s, t: str, x: float, cy: float, align: str = "left", role: str = "pin", size: float = SIZE, model: str = "") -> None:
        """A text whose capital letters are centred on y = cy; x is the left edge, centre or right edge."""
        if not t: return
        w, h = text_w(t, size, role in BOLD_ROLES), text_h(size)
        left = x if align == "left" else x - w / 2 if align == "centre" else x - w
        top = cy - (baseline_dy(size) - size / 2)
        s.texts.append(Text(s=t, x=_r(s.ox + left), y=_r(s.oy + top), w=w, h=h, size_mm=size, align=align, model=model or s.model, role=role))  # type: ignore[typeddict-item]

    def anchor(s, aid: str, x: float, y: float, side: str, model: str = "") -> None:
        s.anchors.append(Anchor(id=aid, model=model or aid, x=_r(s.ox + x), y=_r(s.oy + y), side=side))  # type: ignore[typeddict-item]


def _tw(t: str, role: str = "pin", size: float = SIZE) -> float:
    return text_w(t, size, role in BOLD_ROLES) if t else 0.0


def _pins(it: Item) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [(b, p) for b in it["blocks"] for p in b["pins"]]


def _pn(p: dict[str, Any], b: dict[str, Any] | None = None) -> str:
    """The terminal's name on a drawing: its pin number, else its connector name, else its pin name."""
    return p.get("n") or (b or {}).get("id") or p.get("name") or ""


def _rating(it: Item) -> str:
    r = it["attrs"].get("rating_a")
    return f"{r:g} A" if isinstance(r, (int, float)) else ""


def flat(t: str) -> str:
    """t in lower case without punctuation, to tell whether a name only repeats a code."""
    return "".join(c for c in t.lower() if c.isalnum())


def _head(it: Item) -> tuple[str, str]:
    """Code and display name (the name only when it says more than the code: not the code again in words)."""
    name = " ".join(it["name"].replace(it["code"], "").split()) if it["name"] else ""      # "Wing root connector X-WR" -> "Wing root connector"
    return it["code"], name if name and flat(name) != flat(it["code"]) else ""


def _two(it: Item, sides: dict[str, str]) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    """The first two terminals of an in-line part with their sides: the first L, the other R unless sides says otherwise."""
    ts = _pins(it)[:2]
    out: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for i, (b, p) in enumerate(ts):
        s = sides.get(p["anchor"], "L" if i == 0 else "R")
        if i and s == out[0][2]: s = _OPP[s]
        out.append((b, p, s))
    return out


def _labels(B: _B, rows: list[tuple[str, str]], w: float, y0: float) -> float:
    """Centred label rows below y0 (4.5 mm pitch); returns the symbol height, on the grid."""
    for r, (t, role) in enumerate(rows): B.text(t, w / 2, y0 + 4.5 * r, "centre", role)
    return ceil_to(y0 + 4.5 * (len(rows) - 1) + text_h() / 2 + 0.3) if rows else ceil_to(y0)


def _inline_w(rows: list[tuple[str, str]], base: float = 20.0) -> float:
    return ceil_to(max([base, *(_tw(t, r) + 2 for t, r in rows)]))


def _leads(B: _B, w: float, y: float, xa: float, xb: float, two: list[Any]) -> None:
    """Terminal leads of an in-line part: edge to xa on the left, xb to the edge on the right, and the anchors."""
    B.line(0, y, xa, y); B.line(xb, y, w, y)
    for _, p, s in two: B.anchor(p["anchor"], 0 if s == "L" else w, y, s)


# ---------------------------------------------------------------- block
def _block(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    far = it["role"] == "far_end"
    dflt = "L" if far else "R"
    code, name = _head(it)
    part, loc = it["part"], it["location"]
    n = 1 + bool(part)
    need = 2.5 + _tw(code, "name") + (2 + _tw(name) if name else 0) + (4 + _tw(loc) if loc else 0) + 2.5
    if part: need = max(need, 5 + _tw(part))
    plan = []
    for b in it["blocks"]:
        m = int(bool(b["id"] or b["part"])) + bool(b["mate"])
        pins = []
        for p in b["pins"]:
            nm = p["name"]
            lab = f"{nm} (spare)" if p["spare"] and nm else "spare" if p["spare"] else nm
            pins.append((p, fit(lab, SIZE, 90)))
        nw = max((_tw(p["n"]) for p, _ in pins), default=0.0)
        need = max(need, 8 + _tw(b["id"], "name") + (3 + _tw(b["part"]) if b["part"] else 0), 8 + _tw("mates " + b["mate"]) if b["mate"] else 0,
                   *(8 + nw + (2 + _tw(lab) if lab else 0) for _, lab in pins))
        if m or pins: plan.append((b, m, pins, nw))
    W = max(30.0, ceil_to(need))
    H = 5 * n + 5 + sum(5 * (m + len(pins)) for _, m, pins, _ in plan) + 5 * max(0, len(plan) - 1) if plan else 5 * n + 5
    live = [p["anchor"] for _, _, pins, _ in plan for p, _ in pins if not p["spare"]]
    fs = _OPP[sides.get(live[0], dflt)] if live else _OPP[dflt]   # the far (broken) edge: opposite the pins
    if it["partial"]:
        xn, xf, d = (0.0, W, -1.0) if fs == "R" else (W, 0.0, 1.0)
        pts = [(xn, 0.0), (xf, 0.0)] + [(xf + (d * 1.25 if i % 2 else 0), 2.5 * i) for i in range(1, int(H / 2.5))] + [(xf, H), (xn, H)]
        B.poly(pts, True, N, "white")
    else: B.rect(0, 0, W, H, N, "white")
    B.text(code, 2.5, 3.75, "left", "name")
    if name: B.text(name, 2.5 + _tw(code, "name") + 2, 3.75, "left", "pin")
    B.text(loc, W - 2.5, 3.75, "right", "pin")
    B.text(part, 2.5, 8.75, "left", "part")
    top = 5 * n + 2.5
    for b, m, pins, nw in plan:
        h = 5 * (m + len(pins))
        B.rect(2.5, top, W - 5, h, N, "white")
        r = 0
        if b["id"] or b["part"]:
            B.text(b["id"], 4, top + 2.5, "left", "name", model=B.model)
            B.text(b["part"], W - 4, top + 2.5, "right", "part"); r = 1
        if b["mate"]: B.text("mates " + b["mate"], 4, top + 2.5 + 5 * r, "left", "part")
        if m and pins: B.line(2.5, top + 5 * m, W - 2.5, top + 5 * m, T_)
        for i, (p, lab) in enumerate(pins):
            y = top + 5 * m + 2.5 + 5 * i
            s = sides.get(p["anchor"], dflt)
            sp = "spare" if p["spare"] else "pin"
            if s == "R":
                B.text(p["n"], W - 4, y, "right", sp, model=B.model if p["spare"] else p["anchor"])
                B.text(lab, W - 4 - nw - (2 if nw else 0), y, "right", sp, model=B.model if p["spare"] else p["anchor"])
            else:
                B.text(p["n"], 4, y, "left", sp, model=B.model if p["spare"] else p["anchor"])
                B.text(lab, 4 + nw + (2 if nw else 0), y, "left", sp, model=B.model if p["spare"] else p["anchor"])
            if not p["spare"]:
                B.line(*((W - 2.5, y, W, y) if s == "R" else (0, y, 2.5, y)))
                B.anchor(p["anchor"], W if s == "R" else 0, y, s)
        top += h + 5
    return W, H


# ---------------------------------------------------------------- harness connector
def _harness(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    bl = it["blocks"][:2]
    if len(bl) == 2:  # the half with an anchor on L goes left
        sd = [sides.get(b["pins"][0]["anchor"], d) if b["pins"] else d for b, d in zip(bl, ("L", "R"))]
        if sd[0] == sd[1]: sd[1] = _OPP[sd[0]]
        if sd[0] == "R": bl, sd = bl[::-1], sd[::-1]
    else: sd = ["L"]
    code, name = _head(it)
    k = 2 + any(b["part"] for b in bl) + any(b["mate"] for b in bl)
    rows = max((len(b["pins"]) for b in bl), default=0)
    nums = [p["n"] for b in bl for p in b["pins"]]
    cw = max([20.0, *(_tw(x) + 6 for x in nums), *(_tw(b["id"], "name") + 4 for b in bl), *(_tw(b["part"]) + 4 for b in bl),
              *(_tw("mates " + b["mate"]) + 4 for b in bl),
              (_tw(code, "name") + (2 + _tw(name) if name else 0) + 4) / max(1, len(bl))])
    cw = ceil_to(cw, 2.5)
    W, H = cw * max(1, len(bl)), 5 * k + 5 + 5 * rows
    B.rect(0, 0, W, H, N, "white")
    B.text(code, W / 2 - (2 + _tw(code, "name") + _tw(name)) / 2 if name else W / 2, 3.5, "left" if name else "centre", "name")
    if name: B.text(name, W / 2 - (2 + _tw(code, "name") + _tw(name)) / 2 + _tw(code, "name") + 2, 3.5, "left", "pin")
    B.line(0, 5 * k + 2.5, W, 5 * k + 2.5, T_); B.line(0, 6, W, 6, T_)
    if len(bl) == 2: B.line(W / 2, 6, W / 2, H, T_)
    for c, b in enumerate(bl):
        cx = cw * c + cw / 2
        B.text(b["id"], cx, 8.75, "centre", "name")
        B.text(b["part"], cx, 13.25, "centre", "part")
        if b["mate"]: B.text("mates " + b["mate"], cx, 13.25 + 4.5 * bool(b["part"]), "centre", "part")
        for i, p in enumerate(b["pins"]):
            y = 5 * k + 5 + 5 * i
            s = sd[c]
            sp = "spare" if p["spare"] else "pin"
            B.text(p["n"], 2 if s == "L" else W - 2, y, "left" if s == "L" else "right", sp, model=B.model if p["spare"] else p["anchor"])
            if not p["spare"]: B.anchor(p["anchor"], 0 if s == "L" else W, y, s)
    return W, H


# ---------------------------------------------------------------- distribution parts
def _bartaps(it: Item, B: _B) -> tuple[float, float]:
    """Splice, bus or ground with one anchor per wire (taps) along a vertical bar: the i-th tap on the left and the i-th on the right share a row,
    so a wire can run straight through. A tap is {id, model, side, text}; its anchor id is the tap's id, its model the pin ref it stands for."""
    k = it["symbol"]
    cls = it["attrs"].get("function_class") or "" if k == "bus" else ""
    sd = {s: [t for t in B.taps if t["side"] == s] for s in "LR"}
    labs = [t["text"] for t in B.taps if t.get("text")]
    half = ceil_to(max([5.0, (_tw(it["code"], "name") + 2) / 2, (_tw(cls) + 2) / 2, *(_tw(t) + 3 for t in labs)]))
    W, hdr = 2 * half, 5 * (1 + bool(cls)) if k != "splice" else 5
    rows = max(1, len(sd["L"]), len(sd["R"]))
    y0 = hdr + 5
    B.text(it["code"], half, 3.75, "centre", "name")
    if cls: B.text(cls, half, 8.25, "centre", "pin")
    yb = y0 + 5 * (rows - 1) + 2.5
    B.line(half, y0 - 2.5, half, yb, K if k == "bus" else N)
    for s, ts in sd.items():
        for i, t in enumerate(ts):
            y = y0 + 5 * i
            B.line(half, y, 0 if s == "L" else W, y); B.circle(half, y, 0.9, N, "black")
            B.text(t.get("text", ""), half + 1.5 if s == "L" else half - 1.5, y - 2.5, "left" if s == "L" else "right", "pin", model=t["model"])
            B.anchor(t["id"], 0 if s == "L" else W, y, s, t["model"])
    if k == "ground":
        B.line(half, yb, half, yb + 2.5); B.line(half - 5, yb + 2.5, half + 5, yb + 2.5); B.line(half - 3, yb + 5, half + 3, yb + 5); B.line(half - 1, yb + 7.5, half + 1, yb + 7.5)  # noqa: E501
        yb += 7.5
    return W, ceil_to(yb + 2.5)


def _splice(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    if B.taps: return _bartaps(it, B)
    code = it["code"]
    W = ceil_to(4 + _tw(code, "name"))
    pins = _pins(it)
    s = sides.get(pins[0][1]["anchor"], "L") if pins else "L"
    dx = 0 if s == "L" else W
    B.circle(dx, 5, 1.25, N, "black")
    B.text(code, 3 if s == "L" else W - 3, 5, "left" if s == "L" else "right", "name")
    for _, p in pins: B.anchor(p["anchor"], dx, 5, s)
    return W, 10


def _ground(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    if B.taps: return _bartaps(it, B)
    W = ceil_to(max(10.0, _tw(it["code"], "name") + 2), 10)
    c = W / 2
    B.line(c, 0, c, 5); B.line(c - 5, 5, c + 5, 5); B.line(c - 3, 7.5, c + 3, 7.5); B.line(c - 1, 10, c + 1, 10)
    B.text(it["code"], c, 12.9, "centre", "name")
    for _, p in _pins(it): B.anchor(p["anchor"], c, 0, "T")
    return W, 15


def _bus(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    if B.taps: return _bartaps(it, B)
    pins = _pins(it) or [({}, {"n": "", "name": "", "anchor": ""})]
    cls = it["attrs"].get("function_class") or ""
    rows = 1 + bool(cls)
    lab = [p["n"] or p["name"] for _, p in pins]
    half = ceil_to(max([10.0, *(_tw(t) + 3 for t in lab), (_tw(it["code"], "name") + 2) / 2, (_tw(cls) + 2) / 2]))
    W, H = 2 * half, 5 * rows + 5 * len(pins) + 5
    B.text(it["code"], half, 3.75, "centre", "name")
    B.text(cls, half, 8.25, "centre", "pin")
    B.line(half, 5 * rows + 2.5, half, H - 2.5, K)
    for i, ((_, p), t) in enumerate(zip(pins, lab)):
        y = 5 * rows + 5 + 5 * i
        s = sides.get(p["anchor"], "R")
        B.line(half, y, W if s == "R" else 0, y)
        B.circle(half, y, 0.9, N, "black")
        B.text(t, half - 1.5 if s == "R" else half + 1.5, y, "right" if s == "R" else "left", "pin", model=p["anchor"])
        if p["anchor"]: B.anchor(p["anchor"], W if s == "R" else 0, y, s)
    return W, H


def _breaker(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    fuse = it["symbol"] == "fuse"
    code, _ = _head(it)
    rows = [(code, "name"), *[(t, "pin") for t in (_rating(it), it["attrs"].get("panel") or "") if t]]
    W = _inline_w(rows)
    c = W / 2
    two = _two(it, sides)
    _leads(B, W, 5, c - 5, c + 5, two)
    if fuse:
        B.rect(c - 5, 2.5, 10, 5, N, "white"); B.line(c - 5, 5, c + 5, 5)
    else:
        B.arc(c, 5, 5, 180, 360)
        B.circle(c - 5, 5, 0.9, N, "white"); B.circle(c + 5, 5, 0.9, N, "white")
        B.line(c - 5, 5, c + 2, 1.5)
    return W, _labels(B, rows, W, 10.5)


def _terminator(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    """A resistor drawn upright between its two terminals, which are both on one side (default L): it closes a bus from the side."""
    rows = [(it["code"], "name"), *[(t, "pin") for t in (it["attrs"].get("value") or "",) if t]]
    W = _inline_w(rows)
    c = W / 2
    ts = _pins(it)[:2]
    s = sides.get(ts[0][1]["anchor"], "L") if ts else "L"
    e = 0 if s == "L" else W
    B.line(e, 5, c, 5); B.line(e, 15, c, 15)
    B.poly([(c, 5), (c, 7), (c + 2, 8), (c - 2, 10), (c + 2, 12), (c, 13), (c, 15)])
    for y, (_, p) in zip((5, 15), ts): B.anchor(p["anchor"], e, y, s)
    return W, _labels(B, rows, W, 21.5)


def _battery(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    v = it["attrs"].get("voltage")
    rows = [(it["code"], "name"), *[(t, "pin") for t in ((f"{v:g} V" if isinstance(v, (int, float)) else ""),) if t]]
    W = _inline_w(rows)
    c = W / 2
    ts = _pins(it)[:2]
    pol = [("+" if re.search(r"\+|pos|plus", t) else "-" if re.search(r"-|−|neg|gnd|minus", t) else "")
           for t in (f"{b['id']} {p['n']} {p['name']} {p['type']}".lower() for b, p in ts)]
    if len(ts) == 2 and pol[0] == "+" and pol[1] != "+": ts, pol = ts[::-1], pol[::-1]   # minus first (L), plus second (R)
    two = [(b, p, sides.get(p["anchor"], "L" if i == 0 else "R")) for i, (b, p) in enumerate(ts)]
    if len(two) == 2 and two[0][2] == two[1][2] and all(p["anchor"] in sides for _, p, _ in two):   # both leads on one side: the cell drawn upright
        s, (pl, mi) = two[0][2], (two[0], two[1]) if pol[0] == "+" else (two[1], two[0])
        e = 0 if s == "L" else W
        B.line(c, 5, c, 8.5); B.line(c, 11.5, c, 15); B.line(c - 3, 8.5, c + 3, 8.5); B.line(c - 1.5, 11.5, c + 1.5, 11.5, K)
        for (_, p, _), y, q in ((pl, 5, "+"), (mi, 15, "−")):
            B.line(c, y, e, y); B.anchor(p["anchor"], e, y, s); B.text(q, e + (3.5 if s == "L" else -3.5), y - 2.5, "centre", "pin")
        return W, _labels(B, rows, W, 21.5)
    if len(two) == 2 and two[0][2] == two[1][2]: two[1] = (two[1][0], two[1][1], _OPP[two[0][2]])
    plus_r = next((s == "R" for (_, _, s), q in zip(two, pol) if q == "+"), next((s == "L" for (_, _, s), q in zip(two, pol) if q == "-"), True))
    a, b2 = (c + 1.5, c - 1.5) if plus_r else (c - 1.5, c + 1.5)   # x of the long plate, of the short plate
    B.line(0, 5, min(a, b2), 5); B.line(max(a, b2), 5, W, 5)
    B.line(a, 1.5, a, 8.5); B.line(b2, 3, b2, 7, K)
    for (_, p, s), q in zip(two, pol):
        B.anchor(p["anchor"], 0 if s == "L" else W, 5, s)
        B.text("+" if q == "+" else "−" if q == "-" else "", 1.5 if s == "L" else W - 1.5, 2.5, "left" if s == "L" else "right", "pin")
    return W, _labels(B, rows, W, 11.5)


def _dcdc(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    ps = _pins(it)
    v = it["attrs"].get("voltage")
    code, name = _head(it)
    hdr = [(code, "name")] + ([(name, "pin")] if name else []) + ([(f"out {v:g} V", "pin")] if isinstance(v, (int, float)) else [])

    def side(i: int, b: dict[str, Any], p: dict[str, Any]) -> str:
        if p["anchor"] in sides: return sides[p["anchor"]]
        t = f"{b['id']} {p['n']} {p['name']} {p['type']}".lower()
        return "R" if "out" in t else "L" if re.search(r"\bin|vin|input", t) else "L" if i < (len(ps) + 1) // 2 else "R"
    col: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {"L": [], "R": []}
    for i, (b, p) in enumerate(ps): col[side(i, b, p)].append((b, p))
    lw = max((_tw(_pn(p, b)) for b, p in col["L"]), default=0.0)
    rw = max((_tw(_pn(p, b)) for b, p in col["R"]), default=0.0)
    W = max(30.0, ceil_to(max(lw + rw + 14, *(_tw(t, r) + 5 for t, r in hdr))))
    n, R = len(hdr), max(1, len(col["L"]), len(col["R"]))
    H = 5 * n + 5 * R + 5
    B.rect(0, 0, W, H, N, "white")
    for r, (t, role) in enumerate(hdr): B.text(t, W / 2, 3.75 + 5 * r, "centre", role)
    for s, items in col.items():
        for i, (b, p) in enumerate(items):
            y = 5 * n + 5 + 5 * i
            B.line(*((W - 2.5, y, W, y) if s == "R" else (0, y, 2.5, y)))
            B.text(_pn(p, b), W - 4 if s == "R" else 4, y, "right" if s == "R" else "left", "pin", model=p["anchor"])
            B.anchor(p["anchor"], W if s == "R" else 0, y, s)
    return W, H


def _contacts(it: Item) -> tuple[list[list[str]], dict[str, str] | None]:
    """Poles as lists of pin refs ([a, b] or [com, no, nc]) and the relay coil; terminals the contacts leave out become poles of their own."""
    poles: list[list[str]] = []
    for c in it["attrs"].get("contacts") or []:
        poles.append([c.get("com", ""), c.get("no", ""), c.get("nc", "")] if "com" in c else [c.get("a", ""), c.get("b", "")])
    coil = it["attrs"].get("coil")
    used = {r for p in poles for r in p} | ({coil["a1"], coil["a2"]} if coil else set())
    rest = [p["anchor"] for _, p in _pins(it) if p["anchor"] not in used]
    poles += [rest[i:i + 2] for i in range(0, len(rest), 2)]
    return poles, coil


def _switch(it: Item, B: _B, sides: dict[str, str]) -> tuple[float, float]:
    relay = it["symbol"] == "relay"
    poles, coil = _contacts(it)
    look = {p["anchor"]: (b, p) for b, p in _pins(it)}

    def tn(ref: str) -> str:
        if ref in look: return _pn(look[ref][1], look[ref][0])
        q = ref.rsplit("/", 2)
        return q[-1] or (q[-2] if len(q) > 1 else "")
    refs = [r for p in poles for r in p if r] + ([coil["a1"], coil["a2"]] if coil else [])
    code, name = _head(it)
    rows = [(code, "name"), *[(t, "part") for t in (name, it["part"]) if t]]
    W = max(30.0, ceil_to(max(2 * (max((_tw(tn(r)) for r in refs), default=0.0) + 2.5) + 16, *(_tw(t, r) + 2 for t, r in rows))))
    c = W / 2

    def term(ref: str, y: float, s: str) -> None:
        if not ref: return
        B.text(tn(ref), 1.5 if s == "L" else W - 1.5, y - 2.5, "left" if s == "L" else "right", "pin", model=ref if ref in look else B.model)
        if ref in look: B.anchor(ref, 0 if s == "L" else W, y, s)

    def sidepair(r1: str, r2: str) -> tuple[str, str]:
        s1 = sides.get(r1, "L"); s2 = sides.get(r2, _OPP[s1])
        return (s1, _OPP[s1]) if s2 == s1 else (s1, s2)
    y, blade = 0.0, None
    for pole in poles:
        if len(pole) == 3 and all(pole):
            yc = y + 10
            B.line(0, yc, c - 6, yc); B.line(c + 6, yc - 5, W, yc - 5); B.line(c + 6, yc + 5, W, yc + 5)
            for q in ((c - 6, yc), (c + 6, yc - 5), (c + 6, yc + 5)): B.circle(q[0], q[1], 0.9, N, "white")
            tip = (c + 6, yc + 5) if relay else (c + 4.5, yc)
            B.line(c - 6, yc, *tip)
            term(pole[0], yc, "L"); term(pole[1], yc - 5, "R"); term(pole[2], yc + 5, "R")
            if blade is None: blade = yc + (tip[1] - yc) / 2
            y += 20
        else:
            a, b = (pole + ["", ""])[:2] if len(pole) < 3 else (pole[0], pole[1] or pole[2])
            yc = y + 5
            sa, sb = sidepair(a, b)
            B.line(0, yc, c - 6, yc); B.line(c + 6, yc, W, yc)
            B.circle(c - 6, yc, 0.9, N, "white"); B.circle(c + 6, yc, 0.9, N, "white")
            shut = len(pole) == 3 and not pole[1] and bool(pole[2]) and relay
            B.line(c - 6, yc, c + 6, yc) if shut else B.line(c - 6, yc, c + 5, yc - 3.5)
            term(a, yc, sa); term(b, yc, sb)
            if blade is None: blade = yc if shut else yc - 3.5 * 6 / 11
            y += 10
    if coil:
        yc = y + 10
        sa, sb = sidepair(coil["a1"], coil["a2"])
        B.line(0, yc, c - 6, yc); B.line(c + 6, yc, W, yc); B.rect(c - 6, yc - 2.5, 12, 5, N, "white")
        term(coil["a1"], yc, sa); term(coil["a2"], yc, sb)
        if blade is not None: B.line(c, yc - 2.5, c, blade, T_, True)
        y = yc + 5
    return W, _labels(B, rows, W, y + 3) if y else _labels(B, rows, W, 3)


_BUILD = {"block": _block, "harness": _harness, "splice": _splice, "ground": _ground, "bus": _bus, "breaker": _breaker, "fuse": _breaker,
          "terminator": _terminator, "battery": _battery, "dcdc": _dcdc, "switch": _switch, "relay": _switch}


def text(s: str, x: float, cy: float, align: str = "left", role: str = "pin", size: float = SIZE, model: str = "") -> Text:
    """A free text (caption, wire label, note) with its exact bounding box; capitals centred on y = cy, x as the `align` edge."""
    B = _B({"model": model}, 0, 0)
    B.text(s, x, cy, align, role, size)
    return B.texts[0]


def build(item: Item, x: float = 0.0, y: float = 0.0, sides: dict[str, str] | None = None, taps: list[dict[str, str]] | None = None) -> tuple[Symbol, list[Text]]:
    """The symbol of a scene item with its top left at (x, y) (multiples of GRID), and its texts. `sides` maps anchor ids to "L"/"R".
    `taps` (splice, bus, ground only): one anchor per wire, see _bartaps."""
    f = _BUILD.get(item["symbol"])
    if f is None: raise ValueError(f"no symbol for {item['symbol']!r}")
    B = _B(item, x, y)
    B.taps = (taps or []) if item["symbol"] in ("splice", "bus", "ground") else []
    w, h = f(item, B, sides or {})
    return Symbol(id=item["id"], kind=item["symbol"], model=item["model"], x=x, y=y, w=_r(w), h=_r(h), anchors=B.anchors, prims=B.prims), B.texts


def size(item: Item, sides: dict[str, str] | None = None) -> tuple[float, float]:
    """(w, h) of the symbol build() draws."""
    s, _ = build(item, 0.0, 0.0, sides)
    return s["w"], s["h"]


# ---------------------------------------------------------------- flags
FLAG_H = 10.0
FLAG_TIP = 3.0     # the pointed ends of an off-sheet flag
FLAG_TAB = 7.5     # the sheet-number cell of a continuation flag
FLAG_CHARS = 52.0  # mm of text per line (two lines at most)


def _plain(text: str) -> str:
    """Where a flag leads, in words: no arrow, and the bracket after the name (what the part is) only while the whole text stays short."""
    t = " ".join(text.removeprefix("→ ").split())
    head, sep, par = t.rpartition(" (")
    return head if sep and t.endswith(")") and (len(t) > 34 or head.split()[0] in par) else t


def _flag_lines(kind: str, text: str, sheet: int | None = None) -> list[str]:
    """The flag's text on at most two lines, as narrow as FLAG_CHARS lets it and wider only when it would be cut off. An off-sheet flag says
    `to X-FW cockpit side 11`; a continuation says `continues on sheet 2: ...`; a summary flag (`+ 8 more wires on X`) is narrow."""
    if text.startswith("+ "): return wrap(text, 44.0, SIZE, True, 2)
    body = (f"continues on sheet {sheet or 9}: " if kind == "continuation" else "to ") + _plain(text)
    for w in (FLAG_CHARS, FLAG_CHARS + 12, FLAG_CHARS + 30):
        lines = wrap(body, w, SIZE, True, 2)
        if not lines[-1].endswith(".."): break
    return lines


def flag(id: str, model: str, kind: str, text: str, target: str, sheet: int | None = None, x: float = 0.0, y: float = 0.0, side: str = "L") -> Flag:
    """A flag at (x, y) on the grid, sized to its text. The wire attaches at the middle of its left or right edge (a grid point,
    (x, y + 5) or (x + w, y + 5)). off_sheet: a pennant with pointed ends (text = where it leads); continuation: a box with a cell
    for the sheet number (text = the pin it continues to). `sheet` is the continuation's sheet number. `side` is the edge the wire enters."""
    lines = _flag_lines(kind, text, sheet)
    pad = 2 * FLAG_TIP + 1 if kind == "off_sheet" else FLAG_TAB + 3
    w = ceil_to(max([_tw(t, "flag") for t in lines] or [0.0]) + pad)
    return Flag(id=id, model=model, x=x, y=y, w=max(w, 15.0), h=FLAG_H, text=text, target=target, sheet=sheet, kind=kind, side=side)  # type: ignore[typeddict-item]


def flag_shapes(f: Flag) -> tuple[list[Prim], list[Text]]:
    """The prims and texts a renderer draws for a flag."""
    B = _B({"model": f["model"]}, f["x"], f["y"])
    w, h = f["w"], f["h"]
    lines = _flag_lines(f["kind"], f["text"], f.get("sheet"))
    if f["kind"] == "off_sheet":
        k = FLAG_TIP
        B.poly([(0, h / 2), (k, 0), (w - k, 0), (w, h / 2), (w - k, h), (k, h)], True, N, "white")
        x0, x1 = k, w - k
    else:
        B.rect(0, 0, w, h, N, "white"); B.line(FLAG_TAB, 0, FLAG_TAB, h, T_)
        B.text(str(f["sheet"] or ""), FLAG_TAB / 2, h / 2, "centre", "flag")
        x0, x1 = FLAG_TAB + 1.5, w - 1.5
    for i, t in enumerate(lines): B.text(t, (x0 + x1) / 2, h / 2 + (i - (len(lines) - 1) / 2) * 4.5, "centre", "flag")
    return B.prims, B.texts


# ---------------------------------------------------------------- sheet furniture
LEGEND_NAMES = {"block": "Component", "harness": "Harness conn.", "splice": "Splice", "bus": "Bus bar", "ground": "Ground", "breaker": "Breaker", "fuse": "Fuse",
                "switch": "Switch (open)", "relay": "Relay (off)", "terminator": "Terminator", "battery": "Battery", "dcdc": "DC/DC conv.", "spare": "Spare pin",
                "off_sheet": "Off-sheet", "continuation": "Continued"}


def _mini(kind: str, B: _B) -> None:
    """Draws a pictogram of a symbol kind in a 10 x 5 mm cell at the builder's origin."""
    if kind == "block": B.rect(2, 0.5, 6, 4); B.line(0, 1.5, 2, 1.5); B.line(8, 3.5, 10, 3.5)
    elif kind == "harness": B.rect(1, 0.5, 8, 4); B.line(5, 0.5, 5, 4.5, T_)
    elif kind == "splice": B.line(0, 2.5, 5, 2.5); B.circle(5, 2.5, 1.1, N, "black")
    elif kind == "bus": B.line(5, 0, 5, 5, K); B.line(5, 1.5, 10, 1.5); B.line(5, 3.5, 10, 3.5)
    elif kind == "ground": B.line(5, 0, 5, 2); B.line(2.5, 2, 7.5, 2); B.line(3.5, 3.2, 6.5, 3.2); B.line(4.4, 4.4, 5.6, 4.4)
    elif kind == "breaker": B.line(0, 3.5, 2, 3.5); B.line(8, 3.5, 10, 3.5); B.arc(5, 3.5, 3, 180, 360); B.line(2, 3.5, 6.5, 1.2)
    elif kind == "fuse": B.line(0, 2.5, 10, 2.5); B.rect(2.5, 1, 5, 3, N, "white"); B.line(2.5, 2.5, 7.5, 2.5)
    elif kind == "switch": B.line(0, 3.5, 2.5, 3.5); B.line(7.5, 3.5, 10, 3.5); B.line(2.5, 3.5, 7, 1)
    elif kind == "relay": B.line(0, 2.5, 3, 2.5); B.line(7, 2.5, 10, 2.5); B.line(3, 2.5, 7, 0.5); B.line(5, 3.2, 5, 1.4, T_, True); B.rect(3.5, 3.2, 3, 1.8)
    elif kind == "terminator": B.poly([(0, 2.5), (2, 2.5), (3, 0.5), (4.5, 4.5), (6, 0.5), (7, 2.5), (10, 2.5)])
    elif kind == "battery": B.line(0, 2.5, 4, 2.5); B.line(6, 2.5, 10, 2.5); B.line(6, 0.3, 6, 4.7); B.line(4, 1.2, 4, 3.8, K)
    elif kind == "dcdc": B.rect(1, 0.5, 8, 4); B.line(1, 4.5, 9, 0.5, T_)
    elif kind == "spare": B.rect(1, 0.5, 8, 4, T_); B.line(2.5, 2.5, 7.5, 2.5, T_, True)
    elif kind == "off_sheet": B.poly([(0.5, 2.5), (2.5, 0.5), (7.5, 0.5), (9.5, 2.5), (7.5, 4.5), (2.5, 4.5)], True)
    elif kind == "continuation": B.rect(0.5, 0.5, 9, 4); B.line(3, 0.5, 3, 4.5, T_)


def legend(kinds_used: list[str], size: str = "A3") -> list[dict[str, Any]]:
    """Legend entries {kind, prims, texts} for the symbol kinds used (at most 15; 3 columns of 5), in the strip's legend area."""
    x0, y0, _, _ = areas(size)["legend"]
    out = []
    for i, k in enumerate(dict.fromkeys(kinds_used)):
        if k not in LEGEND_NAMES or i >= 15: continue
        cx, cy = x0 + 45 * (i // 5) + 1.5, y0 + 2.5 + 5 * (i % 5)
        B = _B({"model": ""}, cx, cy - 2.5)
        _mini(k, B)
        B.text(LEGEND_NAMES[k], 13.5, 2.5, "left", "pin")
        out.append(dict(kind=k, prims=B.prims, texts=B.texts))
    return out


def notes(lines: list[str], size: str = "A3") -> tuple[list[Prim], list[Text]]:
    """The notes box of the strip (A3 only) and its lines as texts; lines that do not fit are dropped."""
    x, y, w, h = areas(size)["notes"]
    if not w: return [], []
    B = _B({"model": ""}, 0, 0)
    B.rect(x, y, w, h, N)
    B.text("NOTES", x + 1.5, y + 2.5, "left", "caption")
    for i, t in enumerate(lines[:5]): B.text(fit(t, SIZE, w - 3), x + 1.5, y + 7.5 + 4.5 * i, "left", "note")
    return B.prims, B.texts


def title_block(meta: dict[str, str], sheet: dict[str, Any]) -> tuple[list[Prim], list[Text]]:
    """The sheet frame and the title block (project, drawing title, scope, sheet n of m, revision, date, drawn by, source file).
    meta: title, scope, project, revision, date, drawn_by, source (missing keys are left blank); sheet: n, of, size."""
    a = areas(sheet["size"])
    B = _B({"model": ""}, 0, 0)
    fx, fy, fw, fh = a["frame"]
    B.rect(fx, fy, fw, fh, K)
    x, y, w, h = a["title"]
    B.rect(x, y, w, h, N)
    B.line(x, y + 10, x + w, y + 10, T_); B.line(x, y + 20, x + w, y + 20, T_); B.line(x + 100, y, x + 100, y + 10, T_); B.line(x + 70, y + 10, x + 70, y + 20, T_)
    for cx in (20, 50, 90): B.line(x + cx, y + 20, x + cx, y + h, T_)

    def cell(cx: float, cy: float, cw: float, label: str, value: str) -> None:
        B.text(label, x + cx + 1.5, y + cy + 2.5, "left", "caption")
        B.text(fit(value, SIZE, cw - 3, False), x + cx + 1.5, y + cy + 7.0, "left", "pin")
    B.text(fit(meta.get("title", ""), SIZE_TITLE, 97, True), x + 1.5, y + 5, "left", "title", SIZE_TITLE)
    cell(100, 0, 40, "SHEET", f"{sheet['n']} of {sheet['of']}")
    cell(0, 10, 70, "PROJECT", meta.get("project", ""))
    cell(70, 10, 70, "SCOPE", meta.get("scope", ""))
    cell(0, 20, 20, "REV", meta.get("revision", ""))
    cell(20, 20, 30, "DATE", meta.get("date", ""))
    cell(50, 20, 40, "DRAWN BY", meta.get("drawn_by", ""))
    cell(90, 20, 50, "SOURCE", meta.get("source", ""))
    return B.prims, B.texts


def furniture(meta: dict[str, str], size: str, n: int, of: int, kinds_used: list[str], note_lines: list[str] | None = None) -> dict[str, Any]:
    """Everything a sheet needs besides symbols and wires: {"title_block": {..., prims, texts}, "legend": [...], "notes": [texts]}.
    The title block dict holds the frame, the title block, the legend box and the notes box as `prims`, and the title-block `texts`;
    the layout copies these three keys into the sheet (title_block, legend, notes)."""
    tp, tt = title_block(meta, dict(n=n, of=of, size=size))
    a = areas(size)
    lx, ly, lw, lh = a["legend"]
    B = _B({"model": ""}, 0, 0)
    B.rect(lx, ly, lw, lh, N)
    npr, ntx = notes(note_lines or [], size)
    tb = dict(title=meta.get("title", ""), scope=meta.get("scope", ""), project=meta.get("project", ""), revision=meta.get("revision", ""),
              date=meta.get("date", ""),
              drawn_by=meta.get("drawn_by", ""), sheet=f"{n} of {of}", source=meta.get("source", ""), prims=[*tp, *B.prims, *npr], texts=tt)
    return dict(title_block=tb, legend=legend(kinds_used, size), notes=ntx)
