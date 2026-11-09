"""Python row modules: wirelist/ss??_*.py with R (rows), and optional P (protection), D (decisions), O (open items),
DISPLAY (device display names) and SUBSYSTEM = (code, title). Table entries are dicts, or tuples in the field order of
`tables: {<table>: {fields: [...]}}` in schemagen.yml (defaults in FIELDS)."""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from .records import Record, normalise_keys

FIELDS = {"decisions": ["id", "title", "decision", "rationale", "reference"], "open_items": ["id", "text", "owner"],
          "protection": ["id", "rating", "panel", "loads"]}


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
    warnings: list[str] = field(default_factory=list)  # table entries that could not be read (file, table, index)
    protection_raw: list[Any] | None = None             # row modules: P entries as written (tuples stay tuples), for display.py


def _recs(items: list[Any], file: str, table: str, fields: list[str], warnings: list[str]) -> list[Record]:
    """Dict entries as given, tuples/lists zipped with the field order; anything else is a warning, never dropped silently."""
    out = []
    for i, x in enumerate(items, 1):
        if isinstance(x, dict): out.append(Record(dict(x), file, i))
        elif isinstance(x, (tuple, list)) and len(x) <= len(fields): out.append(Record(dict(zip(fields, x)), file, i))
        elif isinstance(x, (tuple, list)):
            warnings.append(f"{file}: {table}[{i}] skipped: {len(x)} values but {len(fields)} fields {fields} (set tables.{table}.fields)")
        else: warnings.append(f"{file}: {table}[{i}] skipped: a {type(x).__name__}, not a dict or tuple")
    return out


def read(wl: Path, tables: dict[str, Any] | None = None) -> Tables:
    """Rows (with 'subsystem' filled in) and the module-level tables from the ss??_*.py modules.
    `tables` is schemagen.yml's tables: section (field orders for tuple entries)."""
    fields = {k: list(((tables or {}).get(k) or {}).get("fields") or v) for k, v in FIELDS.items()}
    paths = sorted(wl.glob("ss[0-9][0-9]_*.py"))
    if not paths: raise SystemExit(f"no ss??_*.py row modules in {wl} (or set 'source' in schemagen.yml)")
    sys.dont_write_bytecode = True  # the wire list folder is input only
    if str(wl) not in sys.path: sys.path.insert(0, str(wl))  # row modules import their helpers (_lib.py)
    t = Tables(protection_raw=[])
    for p in paths:
        m = module(p, p.stem)
        f = p.name
        t.display.update(getattr(m, "DISPLAY", {}))
        t.protection_raw += list(getattr(m, "P", []))  # type: ignore[operator]
        for key, name in (("protection", "P"), ("decisions", "D"), ("open_items", "O")):
            getattr(t, key).extend(_recs(list(getattr(m, name, [])), f, key, fields[key], t.warnings))
        sub = getattr(m, "SUBSYSTEM", (m.__name__,))[0]
        for i, r in enumerate(getattr(m, "R", []), 1):
            if "_hdr" in r: continue
            data, cols = normalise_keys(dict(r))
            data["subsystem"] = data.get("subsystem") or sub
            t.rows.append(Record(data, f, i, cols))
    return t
