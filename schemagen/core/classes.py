"""Function class and wire colour of a conductor, and gauge normalisation."""
from __future__ import annotations

import re
from typing import Any


def function_class(cid: str, bus: str, func: str, label: str, cfg: Any) -> str:
    """CAN_H, CAN_L, GND, 5 V, 24 V, 14 V, signal, or a class from bus_class / label_class in schemagen.yml."""
    if cid.startswith("CAN") or re.search(r"CAN_[HL]\b", func):
        return "CAN_L" if re.search(r"(^CAN\d-L-|CAN_L)", cid + " " + func) else "CAN_H"
    if bus in cfg.bus_class: return str(cfg.bus_class[bus])
    if bus.startswith("GND") or bus == "Chassis": return "GND"
    if bus.startswith("5 V"): return "5 V"
    if bus.startswith("24"): return "24 V"
    if bus not in ("—", ""):  # powered wire whose bus name says nothing about the voltage: try the label series
        for pat, cls in cfg.label_class.items():
            if re.search(pat, label): return str(cls)
    if bus.startswith(("14", "12")): return "14 V"
    return "signal"


def classify(cid: str, bus: str, func: str, label: str, cfg: Any, explicit: str = "") -> tuple[str, str, str]:
    """(function class, CAN_H/CAN_L or '', palette colour). CAN_H and CAN_L both report class 'CAN'."""
    k = explicit or function_class(cid, bus, func, label, cfg)
    if k == "CAN": k = "CAN_L" if "CAN_L" in func else "CAN_H"
    colour = cfg.colours.get(k, cfg.colours.get("signal", "BU"))
    return ("CAN" if k.startswith("CAN") else k), (k if k.startswith("CAN") else ""), colour


_SIZE = re.compile(r"\bD-?sub[ -]?(\d+)\b|\bD[A-E]-?(\d+)\b|\b(\d+)[ -]?(?:pin|way|pole)s?\b", re.I)


def connector_size(*texts: str) -> int | None:
    """Pin count written in a connector or device name ("D-sub 25", "DB25", "DE-9", "12-pin", "4 way"), else None."""
    for t in texts:
        m = _SIZE.search(t or "")
        if m: return int(next(g for g in m.groups() if g))
    return None


def gauge(a: Any) -> str:
    m = re.match(r"\s*(\d+)", str(a))
    return f"{m.group(1)} AWG" if m else "TBD"
