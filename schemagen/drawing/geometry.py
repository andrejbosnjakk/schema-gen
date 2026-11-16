"""The two data contracts of the drawing engine (docs/drawing-model.md): the Scene (what is drawn, from scope.py) and the
Geometry (where it is drawn, the only thing renderers read). Plain JSON dicts at run time, typed here for the checker."""
from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

VERSION = 1
SHEETS = {"A3": (420.0, 297.0), "A4": (297.0, 210.0)}  # landscape, mm
GRID = 5.0
MIN_TEXT = 2.5
SIDES = ("L", "R", "T", "B")
PRIMS = ("line", "polyline", "rect", "circle", "arc", "path")
STROKES = ("none", "thin", "normal", "thick")                 # suggested 0.18 / 0.35 / 0.5 mm
WEIGHTS = ("fine", "light", "medium", "heavy")                # wire line weight classes, see scope.weight()
FLAG_KINDS = ("off_sheet", "continuation")


# ---------------------------------------------------------------- scene
class Scope(TypedDict):
    kind: Literal["component", "connection", "harness", "selection", "subsystem", "system"]
    ids: list[str]
    text: str                     # as parsed, e.g. "component:VCU"


class Pin(TypedDict):
    n: str                        # pin number as written ("" when the connector is the terminal, e.g. a battery "+")
    name: str
    type: str
    anchor: str                   # anchor id = pin ref "pin:<component>/<connector>/<pin>"
    spare: bool


class Block(TypedDict):
    id: str                       # connector (or harness half) name
    part: str
    mate: str                     # mating half part number; "" unknown
    side: str                     # harness halves: near | far; else ""
    pins: list[Pin]


class Item(TypedDict):
    id: str                       # = model
    model: str                    # component:ID, or connector:ID for a harness connector
    role: Literal["in_scope", "harness", "part", "far_end"]
    symbol: str                   # scope.SYMBOLS
    kind: str                     # model kind
    code: str
    name: str
    part: str
    location: str
    partial: bool                 # only the touched pins are listed
    column: int                   # left-to-right order hint
    blocks: list[Block]
    attrs: dict[str, Any]         # symbol data: rating_a, panel, contacts, coil, value, voltage, function_class


class Fault(TypedDict):
    status: str
    reason: str


class SceneWire(TypedDict):
    id: str                       # conductor id
    model: str                    # conductor:ID
    label: str
    name: str
    gauge: str
    colour: str
    hex: str
    cls: str                      # function class (CAN_H / CAN_L, else 14 V, GND, signal ...)
    weight: str
    a: str                        # anchor of the from end
    b: str                        # anchor of the to end
    pair: str
    shield: str
    harness: str
    sev: str
    fault: Fault | None


class Cover(TypedDict):
    id: str                       # a conductor a summary flag stands for
    at: str                       # its end on the drawn node
    target: str                   # its other end
    label: str
    gauge: str
    colour: str
    text: str                     # where the other end is, in words


class _SceneFlag(TypedDict):
    id: str                       # flag:<conductor id>
    model: str                    # conductor:ID
    kind: Literal["off_sheet"]
    at: str                       # anchor on the drawn node
    target: str                   # pin ref of the conductor's other end
    target_item: str              # model id of the component there
    text: str
    label: str
    gauge: str
    colour: str
    hex: str
    cls: str
    weight: str


class SceneFlag(_SceneFlag, total=False):
    covers: list[Cover]           # summary flag: the conductors it stands for (D111); `at`, `target`, label ... are the first one's


class Scene(TypedDict):
    version: int
    scope: Scope
    title: str
    project: str
    items: list[Item]
    wires: list[SceneWire]
    flags: list[SceneFlag]


# ---------------------------------------------------------------- geometry
class Anchor(TypedDict):
    id: str
    model: str
    x: float
    y: float
    side: Literal["L", "R", "T", "B"]


class Prim(TypedDict, total=False):
    kind: str                     # PRIMS
    stroke: str                   # STROKES
    fill: str                     # "none" | "black" | "white"
    dash: bool
    x1: float; y1: float; x2: float; y2: float      # line
    points: list[list[float]]                       # polyline
    closed: bool
    x: float; y: float; w: float; h: float          # rect
    cx: float; cy: float; r: float                  # circle, arc
    a0: float; a1: float                            # arc: degrees from +x, clockwise (y down)
    d: str                                          # path: SVG path data, avoid


class Symbol(TypedDict):
    id: str
    kind: str
    model: str
    x: float
    y: float
    w: float
    h: float
    anchors: list[Anchor]
    prims: list[Prim]


class Wire(TypedDict):
    id: str
    model: str
    label: str
    gauge: str
    colour: str
    hex: str
    weight: str
    points: list[list[float]]
    a: str
    b: str
    pair: str
    shield: str
    fault: Fault | None


class Text(TypedDict):
    s: str
    x: float
    y: float
    w: float
    h: float
    size_mm: float
    align: Literal["left", "centre", "right"]
    model: str
    role: str


class _Flag(TypedDict):
    id: str
    model: str
    x: float
    y: float
    w: float
    h: float
    text: str
    target: str
    sheet: int | None
    kind: Literal["off_sheet", "continuation"]


class Flag(_Flag, total=False):
    side: Literal["L", "R"]       # the edge the wire enters (middle of the edge)
    covers: list[Cover]           # summary flag: the conductors it stands for


class Sheet(TypedDict):
    n: int
    of: int
    size: Literal["A3", "A4"]
    w_mm: float
    h_mm: float
    grid_mm: float
    symbols: list[Symbol]
    wires: list[Wire]
    texts: list[Text]
    flags: list[Flag]
    notes: list[Text]
    legend: list[dict[str, Any]]
    title_block: dict[str, Any]


class DrawingInfo(TypedDict):
    title: str
    scope: str
    project: str
    revision: str
    date: str
    drawn_by: str
    source: str


class Geometry(TypedDict):
    version: int
    drawing: DrawingInfo
    sheets: list[Sheet]


def to_json(g: Geometry | Scene) -> str:
    return json.dumps(g, ensure_ascii=False, indent=1)


def from_json(s: str) -> Geometry:
    """A geometry from its JSON text; ValueError when it is not one (use validate() for the details)."""
    g = json.loads(s)
    if not isinstance(g, dict) or not isinstance(g.get("sheets"), list) or g.get("version") != VERSION:
        raise ValueError(f"not a version {VERSION} drawing geometry")
    return g  # type: ignore[return-value]


def _on(v: float, grid: float) -> bool:
    return abs(v / grid - round(v / grid)) < 1e-6


def _inside(x: float, y: float, b: Any, tol: float = 1e-6) -> bool:
    return b["x"] - tol <= x <= b["x"] + b["w"] + tol and b["y"] - tol <= y <= b["y"] + b["h"] + tol


def validate(g: Geometry) -> list[str]:
    """Problems that make a geometry unusable or ambiguous; [] when it is fine. Checks the contract, not the looks:
    sizes, grid, orthogonal wires that start and end on what they reference, text size, unique ids, flags used once."""
    out: list[str] = []
    if g.get("version") != VERSION: out.append(f"version is {g.get('version')!r}, expected {VERSION}")
    sheets = g.get("sheets") or []
    if not sheets: out.append("no sheets")
    for sh in sheets:
        p = f"sheet {sh.get('n')}"
        size = SHEETS.get(sh.get("size", ""))
        if size is None: out.append(f"{p}: size {sh.get('size')!r} is not A3 or A4")
        elif (sh["w_mm"], sh["h_mm"]) != size: out.append(f"{p}: {sh['size']} is {size[0]:g} x {size[1]:g} mm, not {sh['w_mm']:g} x {sh['h_mm']:g}")
        if sh.get("of") != len(sheets): out.append(f"{p}: of is {sh.get('of')}, the drawing has {len(sheets)} sheets")
        grid = sh.get("grid_mm") or 0
        if grid != GRID: out.append(f"{p}: grid is {grid}, expected {GRID:g} mm"); grid = GRID
        W, H = sh.get("w_mm", 0), sh.get("h_mm", 0)
        seen: set[str] = set()

        def uid(i: str, what: str) -> None:
            if i in seen: out.append(f"{p}: duplicate id {i!r} ({what})")
            seen.add(i)
        anchors: dict[str, Anchor] = {}
        for s in sh.get("symbols", []):
            uid(s["id"], "symbol")
            if "model" not in s: out.append(f"{p}: symbol {s['id']} has no model")
            for a in s.get("anchors", []):
                uid(a["id"], "anchor"); anchors[a["id"]] = a
                if a.get("side") not in SIDES: out.append(f"{p}: anchor {a['id']} side {a.get('side')!r}")
                if not (_on(a["x"], grid) and _on(a["y"], grid)): out.append(f"{p}: anchor {a['id']} is off the grid")
            for q in s.get("prims", []):
                if q.get("kind") not in PRIMS: out.append(f"{p}: symbol {s['id']} prim kind {q.get('kind')!r}")
                if q.get("stroke", "normal") not in STROKES: out.append(f"{p}: symbol {s['id']} stroke {q.get('stroke')!r}")
        flags: dict[str, Flag] = {}
        for f in sh.get("flags", []):
            uid(f["id"], "flag"); flags[f["id"]] = f
            if f.get("kind") not in FLAG_KINDS: out.append(f"{p}: flag {f['id']} kind {f.get('kind')!r}")
            to = f.get("sheet")
            if f.get("kind") == "continuation" and not (isinstance(to, int) and 1 <= to <= len(sheets) and to != sh.get("n")):
                out.append(f"{p}: continuation flag {f['id']} points at sheet {f.get('sheet')!r}")
            if not f.get("model", "").startswith("conductor:"): out.append(f"{p}: flag {f['id']} model {f.get('model')!r} is not a conductor")
            if "side" in f and f["side"] not in ("L", "R"): out.append(f"{p}: flag {f['id']} side {f['side']!r}")
        used: dict[str, int] = {}
        for w in sh.get("wires", []):
            uid(w["id"], "wire")
            if not w.get("model", "").startswith("conductor:"): out.append(f"{p}: wire {w['id']} model {w.get('model')!r} is not a conductor")
            if w.get("weight") not in WEIGHTS: out.append(f"{p}: wire {w['id']} weight {w.get('weight')!r}")
            pts = w.get("points") or []
            if len(pts) < 2: out.append(f"{p}: wire {w['id']} has {len(pts)} points"); continue
            if any(not (_on(x, grid) and _on(y, grid)) for x, y in pts): out.append(f"{p}: wire {w['id']} has points off the grid")
            if any(x0 != x1 and y0 != y1 for (x0, y0), (x1, y1) in zip(pts, pts[1:])): out.append(f"{p}: wire {w['id']} is not orthogonal")
            if any(not (0 <= x <= W and 0 <= y <= H) for x, y in pts): out.append(f"{p}: wire {w['id']} leaves the sheet")
            for end, pt in (("a", pts[0]), ("b", pts[-1])):
                ref = w.get(end, "")
                if ref in anchors:
                    if (anchors[ref]["x"], anchors[ref]["y"]) != tuple(pt): out.append(f"{p}: wire {w['id']} end {end} is not on anchor {ref}")
                elif ref in flags:
                    used[ref] = used.get(ref, 0) + 1
                    if flags[ref]["model"] != w["model"]: out.append(f"{p}: wire {w['id']} ends on flag {ref} of {flags[ref]['model']}")
                    if not _inside(pt[0], pt[1], flags[ref]): out.append(f"{p}: wire {w['id']} end {end} is not on flag {ref}")
                    elif flags[ref].get("side") and (pt[0], pt[1]) != ((flags[ref]["x"] + (flags[ref]["w"] if flags[ref]["side"] == "R" else 0)), flags[ref]["y"] + flags[ref]["h"] / 2):  # noqa: E501
                        out.append(f"{p}: wire {w['id']} end {end} is not at the middle of the {flags[ref]['side']} edge of flag {ref}")
                else: out.append(f"{p}: wire {w['id']} end {end} references {ref!r}, which is not an anchor or flag on this sheet")
        for fid in flags:
            if used.get(fid, 0) != 1: out.append(f"{p}: flag {fid} is the end of {used.get(fid, 0)} wires, expected 1")
        texts = [*sh.get("texts", []), *sh.get("notes", [])]
        for k, t in enumerate(texts):
            for u in texts[k + 1:]:
                if t["x"] < u["x"] + u["w"] and u["x"] < t["x"] + t["w"] and t["y"] < u["y"] + u["h"] and u["y"] < t["y"] + t["h"]:
                    out.append(f"{p}: texts {t.get('s')!r} and {u.get('s')!r} overlap")
            if "model" not in t: out.append(f"{p}: text {t.get('s')!r} has no model")
            if t.get("size_mm", 0) < MIN_TEXT: out.append(f"{p}: text {t.get('s')!r} is {t.get('size_mm')} mm, minimum {MIN_TEXT}")
            if not (0 <= t["x"] and 0 <= t["y"] and t["x"] + t["w"] <= W and t["y"] + t["h"] <= H): out.append(f"{p}: text {t.get('s')!r} leaves the sheet")
    return out
