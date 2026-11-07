"""A fictional project in the readable layout (`schemagen synth --readable`), for tests and benchmarks.

Subsystem bars, one component header per load, wires written the way people write them (plain names, "pin 3",
"X1.A", "cockpit side, pin 7", "terminal 87 (NO)", "line side" ...). Unless `clean`, it is seeded with near-duplicate
device names (case, spacing, punctuation, one-letter typos) and connector / pin cells that do not parse; the seeds
are listed in seeds.json next to the sheet.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import yaml

from .importers.readable import HEAD

SUBSYSTEMS = {
    "Exterior lighting": ["Nav light left", "Nav light right", "Strobe light left", "Strobe light right", "Landing light", "Taxi light",
                          "Beacon upper", "Beacon lower", "Logo light", "Wing inspection light"],
    "Interior lighting": ["Panel flood light", "Cabin dome light", "Map light", "Instrument backlight", "Baggage light", "Entry light"],
    "Fuel": ["Fuel pump forward", "Fuel pump aft", "Fuel transfer valve", "Fuel quantity sensor", "Fuel flow sensor"],
    "Engine": ["Oil pressure sensor", "Oil temperature sensor", "Coolant temperature sensor", "Starter solenoid", "Cooling fan",
               "Glow controller", "Exhaust temperature probe"],
    "Avionics": ["Primary display", "Secondary display", "Radio", "Transponder", "Intercom", "Autopilot servo pitch",
                 "Autopilot servo roll", "Air data computer", "Attitude reference unit", "Emergency locator"],
    "Environmental": ["Heater blower", "Pitot heater", "Windshield heater", "Avionics cooling fan", "Cabin fan"],
    "Flight controls": ["Trim motor pitch", "Trim motor roll", "Flap motor", "Stall warning horn", "Gear warning horn"],
}
SENSORS = ("sensor", "probe")
PUMPS = ("pump", "fan", "motor", "blower", "heater", "solenoid", "servo")
MAX_A = {22: 5, 20: 7.5, 18: 10, 16: 15, 14: 20, 12: 30}  # FAA AC 43.13-1B Table 11-3 (breakers), as in core/data
G_PER_M = {22: 3.0, 20: 4.5, 18: 6.5, 16: 9.0, 14: 13.5, 12: 21.0}
# harness halves per subsystem (default sides of the readable importer, plus engine / tail side set in schemagen.yml)
HALVES = {"Engine": ("cockpit side", "engine side"), "Fuel": ("cabin side", "tank side"), "Avionics": ("fuselage side", "nose side"),
          "Environmental": ("cabin side", "side-wall sensor side"), "Interior lighting": ("cabin side", "back cabin side")}
PLACE = {"engine side": "Firewall", "wing side": "Wing root", "tail side": "Tail cone", "tank side": "Tank bay", "nose side": "Nose bay",
         "side-wall sensor side": "Side-wall", "back cabin side": "Rear cabin"}
BAD_CELLS = ["see drawing", "pin ?", "TBD", "J?", "pin 3 or 4", "—", "spare?", "X1-A3?"]


class Sheet:
    def __init__(self, rng: random.Random):
        self.rng, self.n = rng, 0
        self.rows: list[list[Any]] = []
        self.conns: list[list[Any]] = []  # [name, near half, far half, next pin]

    def wire(self, name: str, a: str, ap: str, b: str, bp: str, volt: str, amps: float, awg: int, ln: float | None = None) -> None:
        self.n += 1
        ln = ln or round(self.rng.uniform(0.3, 6.0), 2)
        self.rows.append(["wire", f"L{self.n:03d}", name, a, ap, b, bp, volt, amps, awg, ln, round(ln * G_PER_M[awg], 1)])

    def harness(self, zone: str) -> tuple[str, str, str, int]:
        """A harness connector with a free pin pair: (name, near half, far half, pin)."""
        near, far = HALVES.get(zone, ("cockpit side", "wing side" if "light" in zone.lower() else "tail side"))
        for c in self.conns:
            if (c[1], c[2]) == (near, far) and c[3] + 1 <= 19:
                c[3] += 2
                return c[0], c[1], c[2], c[3] - 2
        k = len(self.conns) + 1
        self.conns.append([f"{PLACE[far]} connector P{k}", near, far, 3])
        return self.conns[-1][0], near, far, 1


def build(n: int, seed: int) -> list[list[Any]]:
    rng = random.Random(seed)
    s = Sheet(rng)
    s.rows.append(["sub", "Power distribution"])
    s.rows.append(["head", "Battery"])
    s.wire("Battery feed", "Battery", "positive terminal (M6)", "Battery relay", "terminal 30", "14 V", 40.0, 12)
    s.wire("Main bus feed", "Battery relay", "terminal 87 (NO)", "Main bus", "stud", "14 V", 40.0, 12)
    s.wire("Battery relay coil", "Master switch", "pin 2", "Battery relay", "coil +", "14 V", 0.5, 22)
    s.wire("Battery relay coil return", "Battery relay", "coil - (black lead)", "Ground bus", "stud", "GND", 0.5, 22)
    s.wire("Master switch feed", "Battery", "positive terminal (M6)", "Master switch", "pin 1", "14 V", 0.5, 22)
    s.wire("Battery return", "Battery", "negative terminal (M6)", "Ground bus", "stud", "GND", 40.0, 12)
    s.wire("Ground bus bond", "Ground bus", "stud", "Airframe bond point", "stud", "GND", 40.0, 12)
    forms(s)
    loads = [(sub, ld) for sub, lst in SUBSYSTEMS.items() for ld in lst]
    k, cur = 0, "Power distribution"
    while s.n < n:
        sub, ld = loads[k % len(loads)]
        if k >= len(loads): ld = f"{ld} {k // len(loads) + 1}"  # more loads than names: numbered copies (never near-duplicates)
        k += 1
        if sub != cur: s.rows.append(["sub", sub]); cur = sub
        s.rows.append(["head", ld])
        low = ld.lower()
        amps = round(rng.choice([0.5, 1.2, 2.0, 3.5, 4.5]) if not any(p in low for p in PUMPS) else rng.choice([6.0, 8.0, 12.0]), 1)
        awg = next(g for g in (22, 20, 18, 16, 14, 12) if MAX_A[g] >= amps * 1.25)
        cb = f"Breaker '{ld.upper()}' {MAX_A[awg]:g} A"
        s.wire(f"{ld} breaker feed", "Main bus", "stud", cb, "line side", "14 V", amps, awg)
        src, srcp = cb, "load side"
        if any(p in low for p in SENSORS):  # sensors: supply and signal through the engine computer
            hn, hc, hf, p = s.harness(sub)
            s.wire(f"{ld} signal", ld, "lead 1", hn, f"{hf}, pin {p}", "signal", 0.1, 22)
            s.wire(f"{ld} signal", hn, f"{hc}, pin {p}", "Engine computer", f"X1.{chr(65 + (k % 20))}", "signal", 0.1, 22)
            s.wire(f"{ld} return", ld, "lead 2", hn, f"{hf}, pin {p + 1}", "GND", 0.1, 22)
            s.wire(f"{ld} return", hn, f"{hc}, pin {p + 1}", "Ground bus", "stud", "GND", 0.1, 22)
            s.wire(f"{ld} computer supply", cb, "load side", "Engine computer", f"X2, pin {k % 30 + 1}", "14 V", amps, awg)
            continue
        if any(p in low for p in PUMPS):  # motors: through a relay
            rl = f"{ld} relay"
            s.wire(f"{ld} relay feed", cb, "load side", rl, "terminal 30", "14 V", amps, awg)
            s.wire(f"{ld} relay coil", "Master switch", "pin 3", rl, "coil +", "14 V", 0.2, 22)
            s.wire(f"{ld} relay coil return", rl, "coil -", "Ground bus", "stud", "GND", 0.2, 22)
            src, srcp = rl, "terminal 87 (NO)"
        else:  # lights and avionics: through a switch
            sw = f"Switch '{ld.upper()}'"
            s.wire(f"{ld} switch feed", cb, "load side", sw, "pin 1", "14 V", amps, awg)
            src, srcp = sw, "pin 2"
        hn, hc, hf, p = s.harness(sub)
        sp = f"{ld} return splice"
        s.wire(f"{ld} supply", src, srcp, hn, f"{hc}, pin {p}", "14 V", amps, awg)
        s.wire(f"{ld} supply", hn, f"{hf}, pin {p}", ld, "pin 1", "14 V", amps, awg)
        s.wire(f"{ld} return", ld, "pin 2", sp, "splice", "GND", amps, awg)
        s.wire(f"{ld} return", sp, "splice", hn, f"{hf}, pin {p + 1}", "GND", amps, awg)
        s.wire(f"{ld} return", hn, f"{hc}, pin {p + 1}", "Ground bus", "stud", "GND", amps, awg)
    return s.rows


def forms(s: Sheet) -> None:
    """Wires written in the other forms people use: named terminals (studs, leads, in / out, coax ends, jack
    contacts, loops), T-piece ports and "Connector, name" cells."""
    s.rows.append(["head", "Main contactor"])
    s.wire("Starter contactor feed", "Starter battery", "positive terminal (M8)", "Main contactor", "line stud", "14 V", 40.0, 12)
    s.wire("Starter motor feed", "Main contactor", "load stud", "Starter motor", "feed stud", "14 V", 40.0, 12)
    s.wire("Starter motor return", "Starter motor", "negative terminal", "Ground bus", "stud", "GND", 40.0, 12)
    s.wire("Starter battery return", "Starter battery", "negative terminal (M8)", "Ground bus", "stud", "GND", 40.0, 12)
    s.wire("Main contactor coil", "Master switch", "pin 4", "Main contactor", "A1 (+) M8 stud (battery side)", "14 V", 0.5, 22)
    s.wire("Main contactor coil return", "Main contactor", "A2 (-) M8 stud", "Ground bus", "stud", "GND", 0.5, 22)
    s.rows.append(["head", "Auxiliary outlets"])
    s.wire("Aux fuse feed", "Main bus", "stud", "Fuse 'AUX' 5 A", "in", "14 V", 3.0, 20)
    s.wire("Aux outlet supply", "Fuse 'AUX' 5 A", "fuse output", "Aux outlet", "Connector, V_in 5 V", "14 V", 3.0, 20)
    s.wire("Aux outlet return", "Aux outlet", "Connector, GND", "Ground bus", "stud", "GND", 3.0, 20)
    s.wire("Charger fuse feed", "Main bus", "stud", "Fuse 'CHARGER' 3 A", "in", "14 V", 2.0, 22)
    s.wire("Charger T-tap feed", "Fuse 'CHARGER' 3 A", "fuse holder lead", "Power T-tap", "3, in", "14 V", 2.0, 22)
    s.wire("USB charger supply", "Power T-tap", "3, out", "USB charger", "red lead", "14 V", 1.0, 22)
    s.wire("Hour meter supply", "Power T-tap", "2, drop", "Hour meter", "brown lead (control)", "14 V", 0.1, 22)
    s.wire("USB charger return", "USB charger", "black lead", "Ground bus", "stud", "GND", 1.0, 22)
    s.wire("Hour meter return", "Hour meter", "lead to ground bus", "Ground bus", "stud", "GND", 0.1, 22)
    s.rows.append(["head", "DC-DC converter"])
    s.wire("Converter fuse feed", "Main bus", "stud", "Fuse 'CONVERTER' 7.5 A", "in", "14 V", 4.0, 18)
    s.wire("Converter feed", "Fuse 'CONVERTER' 7.5 A", "output", "DC-DC converter", "in", "14 V", 4.0, 18)
    s.wire("Converter output", "DC-DC converter", "LV1 output (SurLok plug)", "Avionics bus", "stud", "14 V", 4.0, 18)
    s.wire("Converter return", "DC-DC converter", "lead", "Ground bus", "stud", "GND", 4.0, 18)
    s.rows.append(["head", "Antennas and headset"])
    s.wire("Com antenna coax", "Com antenna", "TNC", "Com radio", "BNC", "RF", 0.1, 22)
    s.wire("GPS antenna coax", "GPS antenna", "QMA", "GPS receiver", "QMA", "RF", 0.1, 22)
    s.wire("Headset mic", "Headset jack", "tip", "Audio panel", "pin 5", "signal", 0.1, 22)
    s.wire("Headset audio", "Audio panel", "pin 6", "Headset jack", "tip + ring", "signal", 0.1, 22)
    s.wire("Headset shield", "Headset jack", "sleeve", "Ground bus", "stud", "GND", 0.1, 22)
    s.rows.append(["head", "Safety loop"])
    s.wire("Safety loop", "Emergency stop", "loop out", "Engine computer", "safety loop in", "signal", 0.1, 22)
    s.wire("Safety loop return", "Engine computer", "loop out", "Emergency stop", "loop in", "signal", 0.1, 22)
    s.wire("Oil level sender", "Oil level sensor", "yellow lead (sensor)", "Engine computer", "X3, pin 1", "signal", 0.1, 22)
    s.wire("Oil level switch", "Oil level switch", "output", "Engine computer", "X3, pin 2", "signal", 0.1, 22)
    s.wire("Aux outlet sense", "Aux outlet", "Connector, Signal", "Engine computer", "X3, pin 3", "signal", 0.1, 22)
    s.wire("Hour meter pulse", "Hour meter", "out", "Engine computer", "X3, pin 4", "signal", 0.1, 22)
    s.rows.append(["head", "Spare outlet"])  # values not known yet: text in the number columns
    s.wire("Spare outlet feed", "Main bus", "stud", "Fuse 'SPARE' 5 A", "in", "14 V", 3.0, 20)
    s.rows[-1][8], s.rows[-1][10], s.rows[-1][11] = "TBD", "TBD", "TBD"
    s.wire("Spare outlet supply", "Fuse 'SPARE' 5 A", "output", "Spare outlet", "pin 1", "14 V", 3.0, 20)
    s.rows[-1][8] = "TBC"
    s.wire("Spare outlet return", "Spare outlet", "pin 2", "Ground bus", "stud", "GND", 3.0, 20)
    s.rows[-1][10:12] = ["TBD", "n/a"]
    s.rows.append(["head", "CAN bus"])  # trunk and stubs: no direction, never one-way signals
    for pol, p in (("H", 1), ("L", 2)):
        s.wire(f"CAN1 {pol} trunk", f"CAN1 {pol} splice front", "splice", "Engine computer", f"X4, pin {p}", "signal", 0.1, 22, 0.4)
        s.wire("Bus link", f"CAN1 {pol} splice front", "splice", f"CAN1 {pol} splice aft", "splice", "signal", 0.1, 22, 0.4)
        s.wire(f"Display CAN_{pol} stub", f"CAN1 {pol} splice front", "splice", "Primary display", f"J3, pin {p}", "signal", 0.1, 22, 0.4)
        s.wire(f"GCAN {pol} stub", f"CAN1 {pol} splice aft", "splice", "Air data computer", f"J2, pin {p}", "signal", 0.1, 22, 0.4)
        s.wire(f"CAN1 {pol} end", f"CAN1 {pol} splice aft", "splice", "CAN terminator aft", f"pin {p}", "signal", 0.1, 22, 0.4)
        s.wire(f"CAN1 {pol} start", "CAN terminator front", f"pin {p}", f"CAN1 {pol} splice front", "splice", "signal", 0.1, 22, 0.4)


def _typo(name: str, rng: random.Random, kind: int) -> str:
    if kind == 0: return name.lower() if name != name.lower() else name.upper()
    if kind == 1: return name.replace(" ", "  ", 1)
    if kind == 2: return name.replace(" ", "-", 1)
    w = max(name.split(), key=len)  # one letter dropped from the longest word
    i = rng.randrange(1, len(w) - 1)
    return name.replace(w, w[:i] + w[i + 1:], 1)


def seed_faults(rows: list[list[Any]], rng: random.Random) -> dict[str, Any]:
    """Replace some device names with near-duplicates and some connector / pin cells with unparseable text."""
    wires = [i for i, r in enumerate(rows) if r[0] == "wire"]
    names = sorted({r[c] for r in rows if r[0] == "wire" for c in (3, 5)})
    typos: dict[str, str] = {}
    for kind, name in enumerate(rng.sample([x for x in names if len(x) > 8 and "connector" not in x], 12)):
        v = _typo(name, rng, kind % 4)
        if v in names or v in typos: continue
        uses = [(i, c) for i in wires for c in (3, 5) if rows[i][c] == name]
        if len(uses) < 2: continue
        i, c = uses[-1]
        rows[i][c] = v
        typos[v] = name
    bad = []
    for i in rng.sample(wires, max(1, len(wires) // 100)):
        c = rng.choice((4, 6))
        rows[i][c] = rng.choice(BAD_CELLS)
        bad.append([i, HEAD[3 if c == 4 else 5], rows[i][c]])
    return {"typos": typos, "unparseable": bad}


def write(rows: list[list[Any]], out: Path, seeds: dict[str, Any] | None) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    out.mkdir(parents=True, exist_ok=True)
    wb = Workbook(); ws = wb.active; ws.title = "Wires"  # type: ignore[union-attr]
    ws.append(HEAD)  # type: ignore[union-attr]
    excel_row: dict[int, int] = {}
    for i, r in enumerate(rows):
        if r[0] == "sub":
            ws.append([r[1]])  # type: ignore[union-attr]
            n = ws.max_row  # type: ignore[union-attr]
            ws.merge_cells(start_row=n, start_column=1, end_row=n, end_column=len(HEAD))  # type: ignore[union-attr]
            ws.cell(n, 1).fill, ws.cell(n, 1).font = PatternFill("solid", fgColor="D9E2F3"), Font(bold=True)  # type: ignore[union-attr]
        elif r[0] == "head": ws.append([None, r[1]])  # type: ignore[union-attr]
        else: ws.append(r[1:])  # type: ignore[union-attr]
        excel_row[i] = ws.max_row  # type: ignore[union-attr]
    wb.save(out / "wires.xlsx")
    cfg = {"source": {"path": "wires.xlsx", "format": "readable"},
           "readable": {"sides": {"engine side": "far", "tail side": "far"}}}
    (out / "schemagen.yml").write_text("# Synthetic readable-sheet project (fictional), generated by schemagen synth --readable.\n"
                                       + yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    if seeds is not None:
        seeds = dict(seeds, unparseable=[[excel_row[i], col, txt] for i, col, txt in seeds["unparseable"]])
        (out / "seeds.json").write_text(json.dumps(seeds, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(n: int, seed: int, out: str, clean: bool = False) -> int:
    rng = random.Random(seed + 1000)
    rows = build(n, seed)
    seeds = None if clean else seed_faults(rows, rng)
    write(rows, Path(out), seeds)
    print(f"{sum(r[0] == 'wire' for r in rows)} wires (readable layout{'' if clean else ', seeded'}) -> {out}")
    return 0
