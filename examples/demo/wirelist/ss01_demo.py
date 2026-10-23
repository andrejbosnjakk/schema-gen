"""Demo wire list: one row = one physical conductor. Fictional aircraft, for tests and examples."""
SUBSYSTEM = ("SS-01", "Demo power, sensors and CAN through the firewall")
R = []


def row(id, p1, p1c, p1p, p2, p2c, p2p, func, bus, awg, st="Proposed", name=""):
    R.append(dict(id=id, name=name, p1=p1, p1c=p1c, p1p=p1p, p2=p2, p2c=p2c, p2p=p2p, func=func, bus=bus, awg=awg, st=st))


FW = "X-FW firewall D-SUB 9"
row("PWR-BAT-1", "BAT battery 14 V", "+", "", "CB-MAIN 30 A", "LINE", "", "Battery feed", "14 V", "8")
row("PWR-BUS-1", "CB-MAIN 30 A", "LOAD", "", "BB1 14 V bus bar", "Stud", "", "Bus feed", "14 V", "8")
row("GND-BAT-1", "BAT battery 14 V", "−", "", "GNDB ground bus", "Stud", "", "Battery return", "GND", "8")
# ECU supply, split over two D-SUB contacts with a splice on each side
row("PWR-ECU-A", "CB-ECU 5 A", "LOAD", "", "SP-ECU-C ECU supply splice (cabin)", "Splice", "", "ECU supply", "14 V", "20")
row("PWR-ECU-C1", "SP-ECU-C ECU supply splice (cabin)", "Splice", "", FW, "Cabin half", "1", "ECU supply", "14 V", "22")
row("PWR-ECU-C2", "SP-ECU-C ECU supply splice (cabin)", "Splice", "", FW, "Cabin half", "2", "ECU supply", "14 V", "22")
row("PWR-ECU-N1", FW, "Engine half", "1", "SP-ECU-N ECU supply splice (engine)", "Splice", "", "ECU supply", "14 V", "22")
row("PWR-ECU-N2", FW, "Engine half", "2", "SP-ECU-N ECU supply splice (engine)", "Splice", "", "ECU supply", "14 V", "22")
row("PWR-ECU-B", "SP-ECU-N ECU supply splice (engine)", "Splice", "", "ECU engine control unit", "J1", "1", "ECU supply", "14 V", "20")
row("PWR-CB-ECU", "BB1 14 V bus bar", "Stud", "", "CB-ECU 5 A", "LINE", "", "ECU breaker feed", "14 V", "20")
# ECU ground
row("GND-ECU-C", "GNDB ground bus", "Stud", "", FW, "Cabin half", "3", "ECU ground", "GND", "20")
row("GND-ECU-N", FW, "Engine half", "3", "ECU engine control unit", "J1", "2", "ECU ground", "GND", "20")
# CAN between the ECU and the cockpit display
row("CAN-H-C", "DSP cockpit display", "CAN", "H", FW, "Cabin half", "4", "CAN_H", "—", "22")
row("CAN-H-N", FW, "Engine half", "4", "ECU engine control unit", "J1", "3", "CAN_H", "—", "22")
row("CAN-L-C", "DSP cockpit display", "CAN", "L", FW, "Cabin half", "5", "CAN_L", "—", "22")
row("CAN-L-N", FW, "Engine half", "5", "ECU engine control unit", "J1", "4", "CAN_L", "—", "22")
# 5 V oil temperature sensor read by the display
row("PWR-OTS-C", "DSP cockpit display", "Sensor", "5V", FW, "Cabin half", "6", "Sensor supply", "5 V", "22")
row("PWR-OTS-N", FW, "Engine half", "6", "OTS oil temperature sensor", "Lead", "1", "Sensor supply", "5 V", "22")
row("SIG-OTS-N", "OTS oil temperature sensor", "Lead", "2", FW, "Engine half", "7", "Oil temperature signal", "—", "22")
row("SIG-OTS-C", FW, "Cabin half", "7", "DSP cockpit display", "Sensor", "AI1", "Oil temperature signal", "—", "22")
# 24 V starter-generator field, pin not yet decided at the generator
row("PWR-GEN-C", "CB-GEN 10 A", "LOAD", "", FW, "Cabin half", "8", "Generator field", "24 V", "20")
row("PWR-GEN-N", FW, "Engine half", "8", "GEN starter-generator", "Field", "TBD", "Generator field", "24 V", "20", st="Open")
row("PWR-CB-GEN", "BB24 24 V bus bar", "Stud", "", "CB-GEN 10 A", "LINE", "", "Generator breaker feed", "24 V", "20")
