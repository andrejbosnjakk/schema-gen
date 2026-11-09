"""Writes wires.xlsx for the Kestrel E2 demonstrator, a fictional two-seat electric aircraft (the 1.0 example project).

The sheet is in the readable layout (docs/readable.md): subsystem bars, component headers, one row per wire. It has
exactly three deliberate mistakes, listed in README.md; everything else should pass `schemagen check`. Run it again
after editing the rows below: the output is byte-for-byte the same for the same rows.

    python examples/aircraft/make_sheet.py
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

HEAD = ["Label", "Name", "From", "From connector / pin", "To", "To connector / pin", "Voltage", "Current (A)", "Gauge",
        "Length (m)", "Weight (g)"]
G_PER_M = {22: 3.0, 20: 4.5, 18: 6.5, 16: 9.0, 14: 13.5, 12: 21.0, 10: 33.0, 8: 52.0}  # tinned copper, approximate
FW, WR = "Firewall connector X-FW", "Wing root connector X-WR"
GB, MAIN, ESS, CABIN = "Ground bus", "Main bus", "Essential bus", "Cabin bus"
rows: list[list] = []


def sub(title: str) -> None: rows.append([title])


def head(title: str) -> None: rows.append([None, title])


def w(name: str, a: str, ap: str, b: str, bp: str, volt: str, amps: float, awg: int, ln: float) -> None:
    n = sum(1 for r in rows if len(r) > 2) + 1
    cur = None if volt in ("signal", "RF", "5 V") else amps  # a current only on power wires (the simulation reads it as a load)
    rows.append([f"W{n:03d}", name, a, ap, b, bp, volt, cur, awg, ln, round(ln * G_PER_M[awg], 1)])


def fed(what: str, bus: str, cb: str, awg: int, amps: float) -> None:
    """Bus to a breaker's line side."""
    w(f"{what} breaker feed", bus, "stud", cb, "line side", "14 V", amps, awg, 0.3)


# ---------------------------------------------------------------- power
sub("High voltage (stub)")
head("HV battery pack")
w("DC-DC HV supply", "HV battery pack", "positive terminal", "DC-DC converter", "HV, pin 1", "400 V", 1.6, 14, 0.8)
w("DC-DC HV return", "DC-DC converter", "HV, pin 2", "HV battery pack", "negative terminal", "400 V", 1.6, 14, 0.8)

sub("Power generation and storage")
head("DC-DC converter")
w("DC-DC output", "DC-DC converter", "LV, pin 1", FW, "motor side, pin 1", "14 V", 30.0, 10, 0.6)
w("DC-DC output", FW, "cockpit side, pin 1", "Breaker 'DCDC' 30 A", "line side", "14 V", 30.0, 10, 0.9)
w("DC-DC output to main bus", "Breaker 'DCDC' 30 A", "load side", MAIN, "stud", "14 V", 30.0, 10, 0.2)
w("DC-DC return", "DC-DC converter", "LV, pin 2", FW, "motor side, pin 2", "GND", 30.0, 10, 0.6)
w("DC-DC return", FW, "cockpit side, pin 2", GB, "stud", "GND", 30.0, 10, 0.9)
head("Main battery")
w("Main battery feed", "Main battery", "positive terminal (M8)", "Battery contactor", "terminal 30", "14 V", 30.0, 10, 0.4)
w("Main battery to breaker", "Battery contactor", "terminal 87 (NO)", "Breaker 'BATTERY' 30 A", "line side", "14 V", 30.0, 10, 0.6)
w("Main battery to main bus", "Breaker 'BATTERY' 30 A", "load side", MAIN, "stud", "14 V", 30.0, 10, 0.2)
w("Main battery return", "Main battery", "negative terminal (M8)", GB, "stud", "GND", 30.0, 10, 0.5)
w("Master fuse feed", "Main battery", "positive terminal (M8)", "Fuse 'MASTER' 3 A", "in", "14 V", 0.3, 22, 0.3)
w("Master switch feed", "Fuse 'MASTER' 3 A", "fuse output", "Switch 'MASTER'", "pin 1", "14 V", 0.3, 22, 1.2)
w("Battery contactor coil", "Switch 'MASTER'", "pin 2", "Battery contactor", "coil +", "14 V", 0.3, 22, 1.2)
w("Battery contactor coil return", "Battery contactor", "coil -", GB, "stud", "GND", 0.3, 22, 0.5)
head("Essential bus")
fed("Essential bus", MAIN, "Breaker 'ESS FEED' 20 A", 14, 12.0)
w("Avionics master feed", "Breaker 'ESS FEED' 20 A", "load side", "Switch 'AVIONICS MASTER'", "pin 1", "14 V", 12.0, 14, 0.4)
w("Essential bus feed", "Switch 'AVIONICS MASTER'", "pin 2", ESS, "stud", "14 V", 12.0, 14, 0.4)
head("Backup battery")
w("Backup battery feed", "Backup battery", "positive terminal", "Breaker 'BACKUP' 15 A", "line side", "14 V", 8.0, 16, 0.8)
w("Backup switch feed", "Breaker 'BACKUP' 15 A", "load side", "Switch 'BACKUP'", "pin 1", "14 V", 8.0, 16, 0.4)
w("Backup to essential bus", "Switch 'BACKUP'", "pin 2", ESS, "stud", "14 V", 8.0, 16, 0.4)
w("Backup battery return", "Backup battery", "negative terminal", GB, "stud", "GND", 8.0, 16, 0.8)
head("Ground bus")
w("Ground bus bond", GB, "stud", "Airframe ground stud", "stud", "GND", 30.0, 10, 0.3)

# ---------------------------------------------------------------- lights (wing harness through the wing root)
sub("Exterior lighting")
for lt, cb, amps, p in (("Nav light", "Breaker 'NAV LT' 5 A", 2.0, 1), ("Strobe light", "Breaker 'STROBE' 5 A", 3.0, 3)):
    sw, low = f"Switch '{cb.split(chr(39))[1]}'", lt.lower()
    head(f"{lt}s")
    fed(lt, MAIN, cb, 22, amps)
    w(f"{lt} switch feed", cb, "load side", sw, "pin 1", "14 V", amps, 22, 0.4)
    w(f"{lt} supply", sw, "pin 2", WR, f"cockpit side, pin {p}", "14 V", amps, 22, 1.6)
    w(f"{lt} supply", WR, f"wing side, pin {p}", f"{lt} supply splice", "splice", "14 V", amps, 22, 0.5)
    for side in ("left", "right"):
        w(f"{lt} {side} supply", f"{lt} supply splice", "splice", f"{lt} {side}", "pin 1", "14 V", amps / 2, 22, 4.6)
    for side in ("left", "right"):
        w(f"{lt} {side} return", f"{lt} {side}", "pin 2", f"{lt} return splice", "splice", "GND", amps / 2, 22, 4.6)
    w(f"{lt} return", f"{lt} return splice", "splice", WR, f"wing side, pin {p + 1}", "GND", amps, 22, 0.5)
    w(f"{lt} return", WR, f"cockpit side, pin {p + 1}", GB, "stud", "GND", amps, 22, 1.6)
head("Landing light")
fed("Landing light", MAIN, "Breaker 'LANDING LT' 10 A", 18, 6.0)
w("Landing light switch feed", "Breaker 'LANDING LT' 10 A", "load side", "Switch 'LANDING LT'", "pin 1", "14 V", 6.0, 22, 0.4)  # mistake 1
w("Landing light supply", "Switch 'LANDING LT'", "pin 2", WR, "cockpit side, pin 5", "14 V", 6.0, 18, 1.6)
w("Landing light supply", WR, "wing side, pin 5", "Landing light", "pin 1", "14 V", 6.0, 18, 2.4)
w("Landing light return", "Landing light", "pin 2", WR, "wing side, pin 6", "GND", 6.0, 18, 2.4)
w("Landing light return", WR, "cockpit side, pin 6", GB, "stud", "GND", 6.0, 18, 1.6)

# ---------------------------------------------------------------- avionics (instrument panel, essential bus)
sub("Avionics")
head("EFIS")
fed("EFIS", ESS, "Breaker 'EFIS' 5 A", 20, 2.5)
w("EFIS supply", "Breaker 'EFIS' 5 A", "load side", "EFIS", "J1, pin 1", "14 V", 2.5, 20, 0.6)
w("EFIS return", "EFIS", "J1, pin 2", GB, "stud", "GND", 2.5, 20, 0.8)
head("Com radio")
fed("Com radio", ESS, "Breaker 'COM' 7.5 A", 20, 4.0)
w("Com radio supply", "Breaker 'COM' 7.5 A", "load side", "Com radio", "J1, pin 1", "14 V", 4.0, 20, 0.6)
w("Com radio return", "Com radio", "J1, pin 2", GB, "stud", "GND", 4.0, 20, 0.8)
w("Com antenna coax", "Com antenna", "BNC", "Com radio", "J2, RF", "RF", 0.1, 22, 2.8)
head("Transponder")
fed("Transponder", ESS, "Breaker 'XPDR' 15 A", 20, 1.5)
w("Transponder supply", "Breaker 'XPDR' 15 A", "load side", "Transponder", "J1, pin 1", "14 V", 1.5, 20, 0.6)  # mistake 2
w("Transponder return", "Transponder", "J1, pin 2", GB, "stud", "GND", 1.5, 20, 0.8)
w("Transponder antenna coax", "Transponder antenna", "BNC", "Transponder", "J2, RF", "RF", 0.1, 22, 1.9)
w("Altitude data", "EFIS", "J2, pin 3", "Transponder", "J1, pin 5", "signal", 0.1, 22, 0.5)
head("GPS")
fed("GPS", ESS, "Breaker 'GPS' 3 A", 22, 0.8)
w("GPS supply", "Breaker 'GPS' 3 A", "load side", "GPS receiver", "J1, pin 1", "14 V", 0.8, 22, 0.6)
w("GPS return", "GPS receiver", "J1, pin 2", GB, "stud", "GND", 0.8, 22, 0.8)
w("GPS antenna coax", "GPS antenna", "TNC", "GPS receiver", "J2, RF", "RF", 0.1, 22, 1.4)
w("GPS position data", "GPS receiver", "J1, pin 4", "EFIS", "J2, pin 4", "signal", 0.1, 22, 0.5)
head("Outside air temperature probe")
w("OAT signal", "OAT probe", "pin 1", WR, "wing side, pin 7", "signal", 0.1, 22, 1.2)
w("OAT signal", WR, "cockpit side, pin 7", "EFIS", "J2, pin 7", "signal", 0.1, 22, 1.4)
w("OAT reference", "OAT probe", "pin 2", WR, "wing side, pin 8", "signal", 0.1, 22, 1.2)
w("OAT reference", WR, "cockpit side, pin 8", "EFIS", "J2, pin 8", "signal", 0.1, 22, 1.4)

# ---------------------------------------------------------------- propulsion, low-voltage side (behind the firewall)
sub("Propulsion control")
head("Motor controller")
fed("Motor controller", MAIN, "Breaker 'MCU' 5 A", 20, 2.0)
w("Motor controller supply", "Breaker 'MCU' 5 A", "load side", FW, "cockpit side, pin 3", "14 V", 2.0, 20, 1.1)
w("Motor controller supply", FW, "motor side, pin 3", "Motor controller", "J1, pin 1", "14 V", 2.0, 20, 0.7)
w("Motor controller return", "Motor controller", "J1, pin 2", FW, "motor side, pin 4", "GND", 2.0, 20, 0.7)
w("Motor controller return", FW, "cockpit side, pin 4", GB, "stud", "GND", 2.0, 20, 1.1)
w("Motor enable switch feed", "Breaker 'MCU' 5 A", "load side", "Switch 'MOTOR ENABLE'", "pin 1", "14 V", 0.1, 22, 0.4)
w("Motor enable", "Switch 'MOTOR ENABLE'", "pin 2", FW, "cockpit side, pin 5", "14 V", 0.1, 22, 1.1)
w("Motor enable", FW, "motor side, pin 5", "Motor controller", "J1, pin 3", "14 V", 0.1, 22, 0.7)
head("Throttle position sensor")
w("Throttle sensor supply", "Motor controller", "J2, pin 1", FW, "motor side, pin 6", "5 V", 0.02, 22, 0.7)
w("Throttle sensor supply", FW, "cockpit side, pin 6", "Throttle position sensor", "pin 1", "5 V", 0.02, 22, 1.0)
w("Throttle position", "Throttle position sensor", "pin 2", FW, "cockpit side, pin 7", "signal", 0.01, 22, 1.0)
w("Throttle position", FW, "motor side, pin 7", "Motor controller", "J2, pin 2", "signal", 0.01, 22, 0.7)
w("Throttle sensor reference", "Throttle position sensor", "pin 3", FW, "cockpit side, pin 8", "signal", 0.02, 22, 1.0)
w("Throttle sensor reference", FW, "motor side, pin 8", "Motor controller", "J2, pin 3", "signal", 0.02, 22, 0.7)
head("Motor temperature sensor")
w("Motor temperature", "Motor temperature sensor", "lead 1", "Motor controller", "J2, pin 4", "signal", 0.01, 22, 0.9)
w("Motor temperature reference", "Motor temperature sensor", "lead 2", "Motor controller", "J2, pin 5", "signal", 0.01, 22, 0.9)
head("Battery management system")
fed("BMS", MAIN, "Breaker 'BMS' 3 A", 22, 0.5)
w("BMS supply", "Breaker 'BMS' 3 A", "load side", FW, "cockpit side, pin 9", "14 V", 0.5, 22, 1.1)
w("BMS supply", FW, "motor side, pin 9", "Battery management system", "J1, pin 1", "14 V", 0.5, 22, 0.8)
w("BMS return", "Battery management system", "J1, pin 2", FW, "motor side, pin 10", "GND", 0.5, 22, 0.8)
w("BMS return", FW, "cockpit side, pin 10", GB, "stud", "GND", 0.5, 22, 1.1)
head("Coolant pump")
fed("Coolant pump", MAIN, "Breaker 'COOLANT PUMP' 7.5 A", 20, 4.0)
w("Coolant pump supply", "Breaker 'COOLANT PUMP' 7.5 A", "load side", FW, "cockpit side, pin 13", "14 V", 4.0, 20, 1.1)
w("Coolant pump supply", FW, "motor side, pin 13", "Coolant pump", "pin 1", "14 V", 4.0, 20, 0.9)
w("Coolant pump return", "Coolant pump", "pin 2", FW, "motor side, pin 14", "GND", 4.0, 20, 0.9)
w("Coolant pump return", FW, "cockpit side, pin 14", GB, "stud", "GND", 4.0, 20, 1.1)
head("Coolant temperature sensor")
w("Coolant temperature", "Coolant temperature sensor", "lead 1", "Motor controller", "J2, pin 6", "signal", 0.01, 22, 0.6)
w("Coolant temperature reference", "Coolant temperature sensor", "lead 2", "Motor controller", "J2, pin 7", "signal", 0.01, 22, 0.6)

# ---------------------------------------------------------------- CAN (panel to motor bay, terminated at both ends)
sub("CAN bus")
head("CAN1")
for pol, p, ep, mp, bp in (("H", 1, 7, 7, 3), ("L", 2, 8, 8, 4)):
    sp, sm = f"CAN1 {pol} splice panel", f"CAN1 {pol} splice motor bay"
    w(f"CAN1 {pol} start", "CAN terminator panel", f"pin {p}", sp, "splice", "signal", 0.01, 22, 0.1)
    w(f"CAN1 {pol} EFIS stub", sp, "splice", "EFIS", f"J1, pin {ep}", "signal", 0.01, 22, 0.3)
    w(f"CAN1 {pol} trunk", sp, "splice", FW, f"cockpit side, pin {10 + p}", "signal", 0.01, 22, 1.2)
    w(f"CAN1 {pol} trunk", FW, f"motor side, pin {10 + p}", sm, "splice", "signal", 0.01, 22, 0.5)
    w(f"CAN1 {pol} motor controller stub", sm, "splice", "Motor controller", f"J1, pin {mp}", "signal", 0.01, 22, 0.3)
    w(f"CAN1 {pol} BMS stub", sm, "splice", "Battery management system", f"J1, pin {bp}", "signal", 0.01, 22, 0.4)
    w(f"CAN1 {pol} end", "CAN terminator motor bay", f"pin {p}", sm, "splice", "signal", 0.01, 22, 0.1)

# ---------------------------------------------------------------- cabin (mistake 3: nothing feeds the cabin bus)
sub("Cabin")
for ld, cb, amps in (("Cabin light", "Breaker 'CABIN LT' 3 A", 1.0), ("USB charger", "Breaker 'USB' 5 A", 3.0),
                     ("Cabin fan", "Breaker 'CABIN FAN' 5 A", 2.5)):
    head(ld)
    fed(ld, CABIN, cb, 22, amps)
    w(f"{ld} supply", cb, "load side", ld, "pin 1", "14 V", amps, 22, 1.5)
    w(f"{ld} return", ld, "pin 2", GB, "stud", "GND", amps, 22, 1.7)


def write(out: Path) -> None:
    wb = Workbook(); ws = wb.active; ws.title = "Wires"
    ws.append(HEAD)
    for c in ws[1]: c.font = Font(bold=True)
    for r in rows:
        ws.append(r)
        n = ws.max_row
        if len(r) == 1:
            ws.merge_cells(start_row=n, start_column=1, end_row=n, end_column=len(HEAD))
            ws.cell(n, 1).fill, ws.cell(n, 1).font = PatternFill("solid", fgColor="D9E2F3"), Font(bold=True)
        elif len(r) == 2: ws.cell(n, 2).font = Font(bold=True, italic=True)
    for j, wd in enumerate((8, 30, 30, 22, 30, 22, 9, 11, 7, 10, 10), 1):
        ws.column_dimensions[ws.cell(1, j).column_letter].width = wd
    wb.properties.creator = "schemagen examples/aircraft/make_sheet.py"
    wb.properties.created = wb.properties.modified = datetime(2026, 1, 1)
    buf = io.BytesIO(); wb.save(buf)
    src = zipfile.ZipFile(buf)  # fixed zip timestamps: the same rows give the same bytes
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":  # openpyxl stamps the save time here
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2026-01-01T00:00:00Z", data)
            z.writestr(zipfile.ZipInfo(info.filename, (2026, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)


if __name__ == "__main__":
    out = Path(__file__).with_name("wires.xlsx")
    write(out)
    print(f"{sum(1 for r in rows if len(r) > 2)} wires -> {out}")
