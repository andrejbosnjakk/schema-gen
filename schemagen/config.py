"""Project configuration: one `schemagen.yml` per project, paths relative to that file."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Wire colour per function class (WireViz colour codes). Orange is avoided on purpose: it is the usual HV colour.
DEFAULT_COLOURS = {"14 V": "RD", "24 V": "YE", "5 V": "VT", "GND": "BK", "signal": "BU", "CAN_H": "GN", "CAN_L": "GNWH"}


@dataclass
class Config:
    root: Path
    wirelist: Path
    cards: Path
    out: Path
    default_harnesses: list = field(default_factory=list)
    buses: list = field(default_factory=list)              # device codes that are one electrical node (bus bars, ground bus)
    bus_prefixes: list = field(default_factory=list)       # device code prefixes treated as buses (e.g. PNL-, TB-)
    breaker_prefixes: list = field(default_factory=list)   # device code prefixes treated as breakers/fuses
    splice_prefix: str = "SP-"
    near_words: list = field(default_factory=list)         # words that mark the near (left) half of a harness connector
    colours: dict = field(default_factory=dict)
    bus_class: dict = field(default_factory=dict)          # bus name -> function class override, e.g. {"Switched out": "14 V"}
    label_class: dict = field(default_factory=dict)        # wire-label regex -> function class, e.g. {"^T\\d": "24 V"}
    harnesses: dict = field(default_factory=dict)          # only used by the default display: prefix -> [name, code, far side]
    cardmap: list = field(default_factory=list)            # [{device, connector, card, table}] regexes, see README


def load_config(path):
    path = Path(path).resolve()
    if path.is_dir(): path = path / "schemagen.yml"
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
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
        near_words=d.get("near_words", ["near", "half a", "side a"]),
        colours={**DEFAULT_COLOURS, **d.get("colours", {})},
        bus_class=d.get("bus_class", {}),
        label_class=d.get("label_class", {}),
        harnesses=d.get("harnesses", {}),
        cardmap=d.get("cardmap", []),
    )
