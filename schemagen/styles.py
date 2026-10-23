"""Function class and wire colour of a conductor, and gauge normalisation."""
import re


def kind(w, cfg):
    """Function class: CAN_H, CAN_L, GND, 5 V, 24 V, 14 V or signal."""
    bus, func, i = str(w.get("bus", "")), str(w.get("func", "")), w["id"]
    if i.startswith("CAN") or re.search(r"CAN_[HL]\b", func):
        return "CAN_L" if re.search(r"(^CAN\d-L-|CAN_L)", i + " " + func) else "CAN_H"
    if bus in cfg.bus_class: return cfg.bus_class[bus]
    if bus.startswith("GND") or bus == "Chassis": return "GND"
    if bus.startswith("5 V"): return "5 V"
    if bus.startswith("24"): return "24 V"
    if bus not in ("—", "") and w.get("dom") in cfg.domain_class: return cfg.domain_class[w["dom"]]
    if bus.startswith(("14", "12")): return "14 V"
    return "signal"


def classify(w, cfg):
    """(function class, WireViz colour code). CAN_H and CAN_L both report class 'CAN'."""
    k = kind(w, cfg)
    return ("CAN" if k.startswith("CAN") else k), cfg.colours[k]


def gauge(a):
    m = re.match(r"\s*(\d+)", str(a))
    return f"{m.group(1)} AWG" if m else "TBD"
