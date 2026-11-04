"""Project configuration: one `schemagen.yml` per project, paths relative to that file."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Wire colour per function class (WireViz colour codes). Orange is avoided on purpose: it is the usual HV colour.
DEFAULT_COLOURS = {"14 V": "RD", "24 V": "YE", "5 V": "VT", "GND": "BK", "signal": "BU", "CAN_H": "GN", "CAN_L": "GNWH"}


@dataclass
class Config:
    root: Path
    wirelist: Path
    cards: Path
    out: Path
    default_harnesses: list[str] = field(default_factory=list)
    buses: list[str] = field(default_factory=list)             # device codes that are one electrical node (bus bars, ground bus)
    bus_prefixes: list[str] = field(default_factory=list)      # device code prefixes treated as buses (e.g. PNL-, TB-)
    breaker_prefixes: list[str] = field(default_factory=list)  # device code prefixes treated as breakers/fuses
    splice_prefix: str = "SP-"
    switch_prefixes: list[str] = field(default_factory=list)   # device code prefixes of switches (else from part data)
    relay_prefixes: list[str] = field(default_factory=list)
    near_words: list[str] = field(default_factory=list)        # fallback only: words that mark the near half
    sides: dict[str, dict[str, str]] = field(default_factory=dict)  # harness code -> {half name: near|far}
    colours: dict[str, str] = field(default_factory=dict)
    bus_class: dict[str, str] = field(default_factory=dict)    # bus name -> function class override
    label_class: dict[str, str] = field(default_factory=dict)  # wire-label regex -> function class
    harnesses: dict[str, list[str]] = field(default_factory=dict)  # default display only: prefix -> [name, code, far side]
    cardmap: list[dict[str, str]] = field(default_factory=list)
    split: dict[str, str] = field(default_factory=dict)
    split_default: str = "auto"
    split_threshold: int = 20
    source: dict[str, Any] = field(default_factory=dict)       # table / JSON / WireViz input instead of row modules
    lengths: Path | None = None                                # lengths.csv (label,length_m): measured lengths
    zones: dict[str, Any] = field(default_factory=dict)        # zone id -> {name, xy: [x, y]} (metres)
    rules: dict[str, Any] = field(default_factory=dict)        # rule id -> off | error | warning | info, plus rule options
    direction: dict[str, Any] = field(default_factory=dict)    # wire direction convention options
    sim: dict[str, Any] = field(default_factory=dict)          # simulation defaults (temperature, contact R, ...)
    tables: dict[str, Any] = field(default_factory=dict)       # overrides of cited tables (wire resistance, protection ...)
    raw: dict[str, Any] = field(default_factory=dict)          # the whole yml, for keys read by other modules

    @property
    def lengths_path(self) -> Path:
        """Measured lengths: `lengths` in schemagen.yml, else <out>/lengths.csv (0.2 place)."""
        return self.lengths if self.lengths else self.out / "lengths.csv"


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    if path.is_dir(): path = path / "schemagen.yml"
    d: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    root = path.parent
    return Config(
        root=root,
        wirelist=root / d.get("wirelist", "wirelist"),
        cards=root / d.get("cards", "cards"),
        out=root / d.get("out", "out"),
        default_harnesses=d.get("default_harnesses", []),
        buses=d.get("buses", ["GND", "GNDB"]),
        bus_prefixes=d.get("bus_prefixes", ["BB"]),
        breaker_prefixes=d.get("breaker_prefixes", ["CB-", "FU-"]),
        splice_prefix=d.get("splice_prefix", "SP-"),
        switch_prefixes=d.get("switch_prefixes", []),
        relay_prefixes=d.get("relay_prefixes", []),
        near_words=d.get("near_words", ["near", "half a", "side a"]),
        sides={str(k): {str(h): str(s) for h, s in (v or {}).items()} for k, v in (d.get("sides") or {}).items()},
        colours={**DEFAULT_COLOURS, **d.get("colours", {})},
        bus_class=d.get("bus_class", {}),
        label_class=d.get("label_class", {}),
        harnesses=d.get("harnesses", {}),
        cardmap=d.get("cardmap", []),
        split=d.get("split", {}),
        split_default=d.get("split_default", "auto"),
        split_threshold=d.get("split_threshold", 20),
        source=d.get("source", {}),
        lengths=root / d["lengths"] if d.get("lengths") else None,
        zones=d.get("zones", {}),
        rules=d.get("rules", {}),
        direction=d.get("direction", {}),
        sim=d.get("sim", {}),
        tables=d.get("tables", {}),
        raw=d,
    )
