"""Python row modules: wirelist/ss??_*.py with R (rows), and optional P (protection), D (decisions), O (open items),
DISPLAY (device display names) and SUBSYSTEM = (code, title)."""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from .records import Record, normalise_keys


def module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


@dataclass
class Tables:
    """Everything an importer reads besides the wire rows."""
    rows: list[Record] = field(default_factory=list)
    protection: list[Record] = field(default_factory=list)
    decisions: list[Record] = field(default_factory=list)
    open_items: list[Record] = field(default_factory=list)
    parts: list[Record] = field(default_factory=list)
    components: list[Record] = field(default_factory=list)
    connectors: list[Record] = field(default_factory=list)
    labels: list[Record] = field(default_factory=list)
    display: dict[str, str] = field(default_factory=dict)


def _recs(items: list[Any], file: str) -> list[Record]:
    return [Record(dict(x), file, i) for i, x in enumerate(items, 1) if isinstance(x, dict)]


def read(wl: Path) -> Tables:
    """Rows (with 'subsystem' filled in) and the module-level tables from the ss??_*.py modules."""
    paths = sorted(wl.glob("ss[0-9][0-9]_*.py"))
    if not paths: raise SystemExit(f"no ss??_*.py row modules in {wl} (or set 'source' in schemagen.yml)")
    sys.dont_write_bytecode = True  # the wire list folder is input only
    if str(wl) not in sys.path: sys.path.insert(0, str(wl))  # row modules import their helpers (_lib.py)
    t = Tables()
    for p in paths:
        m = module(p, p.stem)
        f = p.name
        t.display.update(getattr(m, "DISPLAY", {}))
        t.protection += _recs(list(getattr(m, "P", [])), f)
        t.decisions += _recs(list(getattr(m, "D", [])), f)
        t.open_items += _recs(list(getattr(m, "O", [])), f)
        sub = getattr(m, "SUBSYSTEM", (m.__name__,))[0]
        for i, r in enumerate(getattr(m, "R", []), 1):
            if "_hdr" in r: continue
            data, cols = normalise_keys(dict(r))
            data["subsystem"] = data.get("subsystem") or sub
            t.rows.append(Record(data, f, i, cols))
    return t
