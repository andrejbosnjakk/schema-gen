"""Consistency checks for one harness connector (things WireViz would draw without complaint)."""
import re


def harness_checks(pr, hcode, raw, pins, halves, ends):
    """pins: {pin: {'near': [wires], 'far': [wires]}}, halves: {'near': {names}, 'far': {names}}, ends: [(w, e, f, side)]."""
    out = []
    dsub = re.search(r"D-SUB (\d+)", raw)
    for p, sides in pins.items():
        ws = sides["near"] + sides["far"]
        for sd in ("near", "far"):
            if len(sides[sd]) > 1: out.append(f"PIN CLASH {hcode} pin {p} {sd} side: " + ", ".join(w["label"] for w in sides[sd]))
        if ws and (not sides["near"] or not sides["far"]):
            out.append(f"OPEN END {hcode} pin {p}: only the {'near' if sides['near'] else 'far'} side is wired ({ws[0]['label']})")
        if sides["near"] and sides["far"]:
            if len({w["gauge"] for w in ws}) > 1: out.append(f"GAUGE CHANGE {hcode} pin {p}: " + ", ".join(f"{w['label']} {w['awg']}" for w in ws))
            if len({w["kind"] for w in ws}) > 1:
                out.append(f"FUNCTION CLASS DIFFERS {hcode} pin {p}: " + ", ".join(f"{w['label']} {w['kind']}" for w in ws))
    for w, e, f, sd in ends:
        g = w["gauge"]
        if g == "TBD": out.append(f"GAUGE TBD {w['label']} ({w['awg']})")
        elif dsub and int(g.split()[0]) < 20: out.append(f"GAUGE {w['label']} {g} is heavier than a standard D-SUB crimp contact (20-24 AWG)")
        c, p = w[f"p{f}c"], w[f"p{f}p"]
        if "TBD" in f"{c} {p}": out.append(f"PIN TBD {w['label']} at {pr.short(w[f'p{f}'])} ({c} {p})".strip())
    for sd in ("near", "far"):
        if len(halves[sd]) > 1: out.append(f"HALF NAMING {hcode} {sd} side uses several names: " + " / ".join(sorted(halves[sd])))
    return sorted(set(out))
