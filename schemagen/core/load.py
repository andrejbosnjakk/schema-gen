"""Load a project folder into the typed Model: pick the importer, read parts, labels and names, build, validate."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..display_default import DefaultDisplay
from ..importers import parts as parts_in
from ..importers import rows as rows_in
from ..importers import table as table_in
from ..importers import wireviz as wireviz_in
from ..importers.records import ModelError, Problem
from .build import Inputs, build
from .config import Config, load_config
from .model import Model


@dataclass
class Loaded:
    cfg: Config
    model: Model
    naming: Any                      # the project's display module (or the default display)
    display: dict[str, str] = field(default_factory=dict)
    protection_raw: list[dict[str, Any]] = field(default_factory=list)  # P rows as given, for display.set_protection
    warnings: list[str] = field(default_factory=list)
    records: list[Any] = field(default_factory=list)  # wire Records (input order, same as model.conductors)


def naming_for(cfg: Config) -> Any:
    wl = cfg.wirelist
    if (wl / "display.py").exists():
        import sys
        if str(wl) not in sys.path: sys.path.insert(0, str(wl))
        return rows_in.module(wl / "display.py", "display")
    return DefaultDisplay(cfg)


def ledger_path(cfg: Config) -> Path:
    return cfg.root / str(cfg.raw.get("ledger", "label_ledger.json"))


def load(cfg: Config | str | Path) -> Loaded:
    """Read and validate a project. Raises ModelError (file, row, column for every problem)."""
    if not isinstance(cfg, Config): cfg = load_config(cfg)
    naming = naming_for(cfg)
    wl = cfg.wirelist
    names_mod = rows_in.module(wl / "names.py", "names") if (wl / "names.py").exists() else None
    names: dict[str, str] = dict(getattr(names_mod, "NAMES", {}))
    src = cfg.source
    if src and str(src.get("path", "")).lower().endswith(".json"):
        doc = json.loads((cfg.root / src["path"]).read_text(encoding="utf-8"))
        if isinstance(doc, dict) and "conductors" in doc:  # a full model export: lossless by construction
            m = Model.model_validate(doc)
            naming.set_protection([])
            return Loaded(cfg, m, naming, {c.raw: c.name for c in m.components})
    if src and str(src.get("path", "")).lower().endswith((".yml", ".yaml")): t = wireviz_in.read(cfg.root / src["path"])
    elif src: t = table_in.read(cfg.root, src)
    else: t = rows_in.read(wl)
    warnings: list[str] = []
    problems: list[Problem] = []
    parts = parts_in.from_cards(cfg.cards, warnings, problems)
    sheet = parts_in.from_sheet(t.parts, problems) if t.parts else []
    if sheet:
        ids = {p.id for p in sheet}
        parts = [p for p in parts if p.id not in ids] + sheet
    lf = wl / "labels.json"
    labels = json.loads(lf.read_text(encoding="utf-8")) if lf.exists() else {}
    lp = ledger_path(cfg)
    ledger = json.loads(lp.read_text(encoding="utf-8")).get("entries", []) if lp.exists() else []
    display = dict(t.display)
    for r in t.components:  # Components sheet names stand in for DISPLAY when the source is a table
        if r.data.get("device") and r.data.get("name"): display.setdefault(str(r.data["device"]), str(r.data["name"]))
    prot_raw = [dict(r.data) for r in t.protection]
    naming.set_protection(prot_raw)
    inp = Inputs(rows=t.rows, protection=t.protection, decisions=t.decisions, open_items=t.open_items, components=t.components,
                 connectors=t.connectors, labels_sheet=t.labels, parts=parts, labels=labels, names=names, display=display, ledger=ledger)
    m, w, p = build(cfg, naming, inp)
    problems += p
    if problems: raise ModelError(problems)
    return Loaded(cfg, m, naming, display, prot_raw, warnings + w, t.rows)
