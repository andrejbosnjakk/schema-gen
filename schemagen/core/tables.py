"""Cited reference tables (core/data/*.yml), each overridable in schemagen.yml (`tables:` and `sim:`)."""
from __future__ import annotations

import math
from functools import cache
from importlib.resources import files
from typing import Any

import yaml


@cache
def _data(name: str) -> dict[str, Any]:
    d: dict[str, Any] = yaml.safe_load(files("schemagen.core").joinpath(f"data/{name}.yml").read_text(encoding="utf-8"))
    return d


def table(name: str, cfg: Any = None) -> dict[str, Any]:
    """A data table merged with the project's overrides (tables.<name>, or sim: for the simulation defaults)."""
    d = dict(_data(name))
    over = (getattr(cfg, "sim", {}) if name == "sim" else (getattr(cfg, "tables", {}) or {}).get(name, {})) if cfg else {}
    for k, v in (over or {}).items():
        d[k] = {**d[k], **v} if isinstance(v, dict) and isinstance(d.get(k), dict) else v
    return d


def max_rating(awg: int, kind: str, cfg: Any = None) -> float | None:
    """Largest breaker/fuse rating allowed for a copper gauge (AC 43.13-1B Table 11-3), or None when not tabled."""
    t = table("protection", cfg).get("fuse" if kind == "fuse" else "breaker", {})
    t = {int(k): float(v) for k, v in t.items()}
    return t.get(awg)


def lightest(kind: str, cfg: Any = None) -> tuple[int, float] | None:
    """(gauge, rating) of the lightest wire in the protection table."""
    t = table("protection", cfg).get("fuse" if kind == "fuse" else "breaker", {})
    if not t: return None
    g = max(int(k) for k in t)
    return g, float(t[g] if g in t else t[str(g)])


def awg_diameter_mm(n: int) -> float:
    """Nominal diameter of AWG n (ASTM B258)."""
    return float(0.127 * 92.0 ** ((36 - n) / 39))


def awg_area_mm2(n: int) -> float:
    return math.pi * awg_diameter_mm(n) ** 2 / 4


def ohm_per_m(n: int, temp_c: float = 20.0, cfg: Any = None) -> float:
    """Copper resistance per metre of AWG n at temp_c (IEC 60028 resistivity and temperature coefficient)."""
    w = table("wire", cfg)
    over = (w.get("ohm_per_m") or {})
    r20: float = float(over[n]) if n in over else float(w["resistivity_ohm_m"]) / (awg_area_mm2(n) * 1e-6)
    return float(r20 * (1 + float(w["alpha_per_K"]) * (temp_c - float(w["reference_C"]))))


def i2t_limit(n: int, cfg: Any = None) -> float:
    """Adiabatic short-circuit limit (k A)^2 in A^2 s (IEC 60364-4-43 Table 43A)."""
    k = float(table("wire", cfg)["k_insulation"])
    return (k * awg_area_mm2(n)) ** 2
