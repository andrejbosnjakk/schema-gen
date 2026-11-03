"""Function class and wire colour of a conductor (0.2 interface; the logic lives in schemagen.core.classes)."""
from .core.classes import function_class, gauge


def kind(w, cfg):
    return function_class(w["id"], str(w.get("bus", "")), str(w.get("func", "")), w["label"], cfg)


def classify(w, cfg):
    k = kind(w, cfg)
    return ("CAN" if k.startswith("CAN") else k), cfg.colours[k]


__all__ = ["kind", "classify", "gauge"]
