"""The symbol sheet: every symbol kind of the engine on one A3 sheet with fictional data, with frame, title block and legend.
`python -m schemagen.drawing.sheet <outdir>` writes symbol-sheet.svg and symbol-sheet.pdf."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import symbols as S
from .geometry import SHEETS, Geometry, Text, validate
from .style import areas

META = dict(title="Symbol sheet", scope="symbols", project="Fictional example (not a project)", revision="A", date="2026-11", drawn_by="schemagen",
            source="symbols.py")


def _pin(c: str, conn: str, n: str, name: str = "", spare: bool = False, typ: str = "") -> dict[str, Any]:
    return dict(n=n, name=name, type=typ, anchor=f"pin:{c}/{conn}/{n}", spare=spare)


def _blk(id: str, pins: list[dict[str, Any]], part: str = "", mate: str = "", side: str = "") -> dict[str, Any]:
    return dict(id=id, part=part, mate=mate, side=side, pins=pins)


def _item(code: str, symbol: str, blocks: list[dict[str, Any]], role: str = "in_scope", name: str = "", part: str = "", loc: str = "", partial: bool = False,
          **attrs: Any) -> dict[str, Any]:
    return dict(id=f"component:{code}", model=f"component:{code}", role=role, symbol=symbol, kind=symbol, code=code, name=name or code, part=part, location=loc,
                partial=partial, column=0, blocks=blocks, attrs=attrs)


def _items() -> dict[str, dict[str, Any]]:
    names = ["PWR 12 V", "GND", "CAN H", "CAN L", "Spare input", "Fuel pump", "Injector 1", "Injector 2", "Coil 1", "Coil 2", "Spare output", "Tacho"]
    j1 = [_pin("ECU", "J1", str(i), nm, i in (5, 11)) for i, nm in enumerate(names, 1)]
    j2 = [_pin("ECU", "J2", str(i), nm) for i, nm in enumerate(["TX", "RX", "5 V", "GND"], 1)]
    ecu = _item("ECU", "block", [_blk("J1", j1, "MS27-12", "P1"), _blk("J2", j2, "MS27-4")], name="Engine control unit", part="ECU-3000", loc="Bay 2")
    far = _item("SNS1", "block", [_blk("P1", [_pin("SNS1", "P1", "1", "Signal"), _pin("SNS1", "P1", "2", "5 V"), _pin("SNS1", "P1", "3", "GND")])],
                role="far_end", name="Oil pressure sensor", part="OPS-7", partial=True)
    har = _item("X-BH", "harness", [_blk("Cabin half", [_pin("X-BH", "Cabin half", str(i), spare=i == 6) for i in range(1, 7)], side="near"),
                                    _blk("Wing half", [_pin("X-BH", "Wing half", str(i), spare=i == 6) for i in range(1, 7)], side="far")], role="harness")
    single = lambda c, conn: [_blk(conn, [_pin(c, conn, "")])]  # noqa: E731
    t = lambda c, *ns: [_blk(n, [_pin(c, n, "")]) for n in ns]  # noqa: E731
    return {
        "block": ecu, "far": far, "harness": har,
        "splice": _item("SP-1", "splice", single("SP-1", "Splice"), role="part"),
        "ground": _item("GNDB", "ground", single("GNDB", "Stud"), role="part", function_class="GND"),
        "bus": _item("BB1", "bus", [_blk("Stud", [_pin("BB1", "Stud", str(i)) for i in (1, 2, 3)])], role="part", function_class="14 V"),
        "breaker": _item("CB-1", "breaker", t("CB-1", "LINE", "LOAD"), role="part", rating_a=5.0, panel="ECU"),
        "fuse": _item("F-1", "fuse", t("F-1", "IN", "OUT"), role="part", rating_a=10.0, panel=""),
        "switch": _item("SW-1", "switch", t("SW-1", "A", "B"), role="part", state="normal", contacts=[dict(a="pin:SW-1/A/", b="pin:SW-1/B/")], coil=None,
                        name="Master switch"),
        "relay": _item("K-1", "relay", t("K-1", "30", "87", "87a", "85", "86"), role="part", state="normal",
                       contacts=[dict(com="pin:K-1/30/", no="pin:K-1/87/", nc="pin:K-1/87a/")], coil=dict(a1="pin:K-1/85/", a2="pin:K-1/86/")),
        "terminator": _item("R-1", "terminator", t("R-1", "1", "2"), role="part", value="120 Ω"),
        "battery": _item("BAT", "battery", [_blk("+", [_pin("BAT", "+", "", "", typ="power")]), _blk("-", [_pin("BAT", "-", "", "", typ="gnd")])], role="part",
                         voltage=12.0),
        "dcdc": _item("DC-1", "dcdc", t("DC-1", "IN+", "IN-", "OUT+", "OUT-"), role="part", voltage=5.0, name="Converter"),
    }


def symbol_sheet() -> Geometry:
    """Every symbol kind on one A3 sheet with fictional data, a few wires, both flag kinds, frame, title block and legend."""
    it = _items()
    ax, ay, aw, ah = areas("A3")["area"]
    syms: list[Any] = []; texts: list[Text] = []; wires: list[Any] = []; flags: list[Any] = []

    def put(key: str, cap: str, x: float, y: float, sides: dict[str, str] | None = None) -> Any:
        sy, tx = S.build(it[key], x, y + 10, sides)
        syms.append(sy); texts.extend(tx)
        texts.append(S.text(cap, x, y + 2.5, "left", "caption", model=sy["model"]))
        return sy

    def anchor(sy: Any, n: str) -> Any:
        return next(a for a in sy["anchors"] if a["id"].endswith(n))

    def wire(i: str, a: str, b: str, pts: list[list[float]], weight: str, label: str, lx: float, ly: float) -> None:
        wires.append(dict(id=i, model=f"conductor:{i}", label=label, gauge="", colour="", hex="#888", weight=weight, points=pts, a=a, b=b, pair="", shield="",
                          fault=None))
        texts.append(S.text(f"{i}  {label}", lx, ly, "left", "wire"))
    put("block", "block: component, two connectors, spares", ax + 5, ay)
    put("far", "block: partial far end", ax + 100, ay)
    put("harness", "harness connector", ax + 100, ay + 50)
    put("splice", "splice", ax + 100, ay + 115)
    put("ground", "ground", ax + 130, ay + 115)
    put("terminator", "terminator", ax + 250, ay + 60)
    put("switch", "switch (drawn open)", ax + 165, ay)
    put("relay", "relay (de-energised)", ax + 165, ay + 45)
    put("fuse", "fuse", ax + 165, ay + 125)
    put("dcdc", "dc/dc converter", ax + 250, ay)
    # the power chain: battery, breaker, bus bar, flags; wires of different weights
    yw = ay + 195
    bat = put("battery", "battery", ax + 5, yw - 15)
    cb = put("breaker", "circuit breaker", ax + 50, yw - 15)
    bus = put("bus", "bus bar", ax + 95, yw - 25, {"pin:BB1/Stud/1": "L", "pin:BB1/Stud/2": "R", "pin:BB1/Stud/3": "R"})
    ya = cb["anchors"][0]["y"]
    p, m = anchor(bat, "/+/"), anchor(cb, "LINE/")
    wire("W001", p["id"], m["id"], [[p["x"], p["y"]], [m["x"], m["y"]]], "heavy", "4 RD", p["x"] + 2.5, ya - 3)
    q, b1 = anchor(cb, "LOAD/"), anchor(bus, "Stud/1")
    wire("W002", q["id"], b1["id"], [[q["x"], q["y"]], [b1["x"], b1["y"]]], "medium", "12 RD", q["x"] + 2.5, ya - 3)
    b2, b3 = anchor(bus, "Stud/2"), anchor(bus, "Stud/3")
    f1 = S.flag("flag:W003", "conductor:W003", "off_sheet", "→ CB-MAIN 30 A LOAD", "pin:CB-MAIN/LOAD/", None, b2["x"] + 30, b2["y"] - 5)
    wire("W003", b2["id"], f1["id"], [[b2["x"], b2["y"]], [f1["x"], b2["y"]]], "light", "20 RD", b2["x"] + 2.5, b2["y"] - 3)
    f2 = S.flag("flag:W004", "conductor:W004", "continuation", "pin:ECU/J1/1", "pin:ECU/J1/1", 2, b3["x"] + 30, b3["y"] + 5)
    wire("W004", b3["id"], f2["id"], [[b3["x"], b3["y"]], [b3["x"] + 5, b3["y"]], [b3["x"] + 5, b3["y"] + 10], [f2["x"], b3["y"] + 10]], "fine", "24 RD",
         b3["x"] + 7.5, b3["y"] + 7)
    flags += [f1, f2]
    kinds = ["block", "harness", "splice", "bus", "ground", "breaker", "fuse", "switch", "relay", "terminator", "battery", "dcdc", "spare", "off_sheet",
             "continuation"]
    notes = ["Fictional data: not a real project.", "Contacts are drawn unpowered.", "Spare pins are grey and have no anchor."]

    def sheet(n: str, syms: list[Any], wires: list[Any], texts: list[Any], flags: list[Any], k: list[str]) -> dict[str, Any]:
        sh: dict[str, Any] = dict(n=int(n), of=3, size="A3", w_mm=SHEETS["A3"][0], h_mm=SHEETS["A3"][1], grid_mm=5.0,
                                symbols=syms, wires=wires, texts=texts, flags=flags)
        sh.update(S.furniture(META, "A3", int(n), 3, k, notes if n == "1" else ["Continuation target of W004 on sheet 1."]))
        return sh
    # sheet 2: where W004 continues
    far2 = dict(it["far"], id="component:ECU", model="component:ECU", code="ECU", name="Engine control unit",
                blocks=[_blk("J1", [_pin("ECU", "J1", "1", "PWR 12 V")], "MS27-12")])
    s2, t2 = S.build(far2, ax + 110, ay + 20)
    a1 = s2["anchors"][0]
    g2 = S.flag("flag:W004", "conductor:W004", "continuation", "pin:BB1/Stud/3", "pin:BB1/Stud/3", 1, ax + 20, a1["y"] - 5, "R")
    w2 = dict(id="W004", model="conductor:W004", label="24 RD", gauge="", colour="", hex="#888", weight="fine",
              points=[[g2["x"] + g2["w"], a1["y"]], [a1["x"], a1["y"]]],
              a=g2["id"], b=a1["id"], pair="", shield="", fault=None)
    t2.append(S.text("W004  24 RD", g2["x"] + g2["w"] + 2.5, a1["y"] - 3, "left", "wire"))
    info = dict(title=META["title"], scope=META["scope"], project=META["project"], revision=META["revision"], date=META["date"], drawn_by=META["drawn_by"],
                source=META["source"])
    return dict(version=1, drawing=info, sheets=[sheet("1", syms, wires, texts, flags, kinds), sheet("2", [s2], [w2], t2, [g2], ["block", "continuation"]),  # type: ignore
                                                 reading_sheet(info)])  # type: ignore


READING = [  # (picture, what it is and what it means for the person wiring it)
    ("block", "Component: a box, one row per pin with its number and name. Wires leave on the side of the row."),
    ("splice", "Splice: several wires permanently joined at one point; everything on the dot is electrically one wire."),
    ("relay", "Relay or contactor: a heavy switch operated by a small current; the thin wires go to the coil, the thick ones to the contact."),
    ("breaker", "Breaker: a resettable fuse; power goes in one side and out the other."),
    ("switch", "Switch: opens or closes one wire; drawn open."),
    ("ground", "Ground bus: the common bar where all return wires end."),
    ("bus", "Bus: a bar that feeds several wires from one supply."),
    ("harness", "Harness connector: a plug pair; pin 11 on one half continues as pin 11 on the other."),
    ("terminator", "Terminator: a resistor that closes each end of the CAN bus."),
    ("battery", "Battery: the long plate is plus."),
    ("off_sheet", "Pointed flag: the wire leaves this drawing; the text says where it goes."),
    ("continuation", "Box flag with a number: the wire continues on that sheet."),
    ("partial", "Jagged edge: the component has more pins than this sheet shows."),
    ("spare", "Grey pin: spare, no wire."),
    ("fault", "Dashed wire: the simulation found a fault on it."),
    ("stub", "Dashed stub on a part: that terminal has no wire on this drawing."),
    ("text", "Wire text, for example W052 20 AWG BK: the label to put on the wire, its size and its colour code. The wire table spells them out."),
]
STEPS = ["1. Find the wire in the wire table (under the drawing or on the table sheet after it).",
         "2. Cut it and put its label on both ends.",
         "3. Connect the From end and the To end as the table says, then tick the box.",
         "The drawings are proven to match the wire list; whether the wire list matches the aircraft is checked at the plane with the wire-table tick boxes and a continuity test."]  # noqa: E501


def reading_sheet(info: dict[str, str]) -> dict[str, Any]:
    """The page `How to read these drawings`: one plain sentence for every symbol, then how to work from a sheet."""
    ax, ay, aw, ah = areas("A3")["area"]
    B = S._B({"model": ""}, 0, 0)
    B.text("How to read these drawings", ax, ay + 2.5, "left", "title", S.SIZE_TITLE)
    col, pitch = aw / 2, 17.0
    for i, (k, t) in enumerate(READING):
        x, y = ax + col * (i // 9), ay + 14 + pitch * (i % 9)
        C = S._B({"model": ""}, x, y)
        if k == "partial": C.poly([(1, 0.5), (9, 0.5), (9, 1.5), (8, 2), (9, 2.5), (8, 3), (9, 3.5), (9, 4.5), (1, 4.5)], True)
        elif k == "fault": C.line(0, 2.5, 10, 2.5, S.N, True)
        elif k == "stub": C.line(0, 2.5, 10, 2.5, S.N, True); C.circle(10, 2.5, 0.9, S.N, "black")
        elif k == "text": C.text("W052", 0, 2.5, "left", "wire")
        else: S._mini(k, C)
        B.prims += C.prims
        B.texts += C.texts
        for j, line in enumerate(S.wrap(t, col - 40, S.SIZE, False, 3)): B.text(line, x + 20, y + 2.5 + 4.5 * j, "left", "pin")
    y = ay + 14 + pitch * 9 + 5
    B.text("Working from a sheet", ax, y, "left", "name")
    for i, t in enumerate(STEPS): B.text(t, ax, y + 6 + 4.5 * i, "left", "pin")
    sh: dict[str, Any] = dict(n=3, of=3, size="A3", w_mm=SHEETS["A3"][0], h_mm=SHEETS["A3"][1], grid_mm=5.0,
                           symbols=[], wires=[], texts=B.texts, flags=[], rules=B.prims)
    sh.update(S.furniture(dict(info, title="How to read these drawings"), "A3", 3, 3, [], ["Fictional example: not a project."]))
    return sh


def main(argv: list[str]) -> int:
    from .render_pdf import pdf
    from .render_svg import svg
    out = Path(argv[0] if argv else "docs/screens/drawings")
    out.mkdir(parents=True, exist_ok=True)
    g = symbol_sheet()
    for p in validate(g): print("problem:", p)
    for i in range(len(g["sheets"])):
        name = "symbol-sheet.svg" if not i else f"symbol-sheet-{i + 1}.svg"
        (out / name).write_text(svg(g, i, embed_font=True), encoding="utf8", newline="\n")
    pdf(g, out / "symbol-sheet.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
