"""Records: one input row with its origin, in neutral field names. Column names and their aliases live here.

Neutral fields (0.2 names, still accepted everywhere) and the plain column names the exported table uses:
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# field -> plain column name (the exported table and the sheet template use the plain names)
COLUMNS: dict[str, str] = {
    "id": "id", "label": "label", "name": "name",
    "p1": "from", "p1c": "from connector", "p1p": "from pin", "p1side": "from side",
    "p2": "to", "p2c": "to connector", "p2p": "to pin", "p2side": "to side",
    "func": "function", "bus": "bus", "cls": "function class", "awg": "gauge", "colour": "colour",
    "amps": "current_A", "length": "length_m", "st": "status", "subsystem": "subsystem", "notes": "notes",
    "zone": "zone", "harn": "harness", "prot": "protection", "src": "sources",
}
FIELDS_02 = ["id", "label", "name", "p1", "p1c", "p1p", "p2", "p2c", "p2p", "func", "bus", "awg", "amps", "st", "subsystem", "notes"]
# other spellings found in row modules and sheets
_ALIASES = {"col": "colour", "color": "colour", "length_m": "length", "current": "amps", "current_a": "amps", "status": "st",
            "function": "func", "gauge": "awg", "class": "cls", "function class": "cls", "harness": "harn",
            "protection": "prot", "sources": "src", "source": "src"}
ALIAS: dict[str, str] = {**{f: f for f in COLUMNS}, **{v.lower(): f for f, v in COLUMNS.items()}, **_ALIASES}


def field_of(column: str) -> str | None:
    """Neutral field for a column name or row key, or None (then the value goes to `extra`)."""
    return ALIAS.get(str(column).strip().lower())


@dataclass
class Problem:
    file: str
    row: int | None
    column: str
    message: str

    def __str__(self) -> str:
        where = self.file + (f", row {self.row}" if self.row is not None else "") + (f", column '{self.column}'" if self.column else "")
        return f"{where}: {self.message}"


class ModelError(SystemExit):
    """Validation failed; every problem names file, row and column."""
    def __init__(self, problems: list[Problem]):
        self.problems = problems
        super().__init__("invalid project input:\n" + "\n".join(f"  {p}" for p in problems))


@dataclass
class Record:
    data: dict[str, Any]           # neutral field -> value; unknown keys stay under their own name
    file: str = ""
    row: int | None = None
    columns: dict[str, str] = field(default_factory=dict)  # neutral field -> column name in the file (for messages)

    def col(self, f: str) -> str:
        return self.columns.get(f, COLUMNS.get(f, f))


def normalise_keys(raw: dict[str, Any], mapping: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    """Row with neutral keys. mapping: field -> column (schemagen.yml `source.columns`). Returns (data, field->column)."""
    mapping = mapping or {}
    back = {str(v).strip().lower(): k for k, v in mapping.items()}
    data: dict[str, Any] = {}
    cols: dict[str, str] = {}
    for k, v in raw.items():
        if k is None: continue
        key = str(k).strip()
        if key.endswith(":json"):  # extra column written by the exporter for non-text values
            name = key[:-5]
            if v is None or v == "": continue
            data[name] = json.loads(v) if isinstance(v, str) else v
            cols[name] = key
            continue
        f = back.get(key.lower()) or field_of(key)
        f = f or key
        if f in data and (data[f] not in (None, "") or v in (None, "")): continue  # first non-empty spelling wins
        data[f] = v
        cols[f] = key
    return data, cols


def text(v: Any) -> str:
    return "" if v is None else str(v).strip() if isinstance(v, str) else str(v)


def number(v: Any) -> float | None | str:
    """float, None for empty, or the raw text when it is not a number."""
    if v is None or v == "": return None
    if isinstance(v, bool): return str(v)
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(",", ".")
    try: return float(s)
    except ValueError: return str(v)


def sources(v: Any) -> list[dict[str, str]]:
    """'EWD-02 p. 4; EWD-03 p. 7' (or dicts, or a list) -> [{doc, page}]."""
    if v is None or v == "": return []
    items = v if isinstance(v, list) else [v] if isinstance(v, dict) else [x for x in str(v).split(";")]
    out = []
    for it in items:
        if isinstance(it, dict):
            out.append({"doc": text(it.get("doc", it.get("document", ""))), "page": text(it.get("page", ""))}); continue
        s = str(it).strip()
        if not s: continue
        m = re.match(r"^(.*?)\s+p\.\s*(\S.*)$", s)
        out.append({"doc": m.group(1).strip(), "page": m.group(2).strip()} if m else {"doc": s, "page": ""})
    return out


def listof(v: Any) -> list[str]:
    if v is None or v == "": return []
    if isinstance(v, (list, tuple)): return [text(x) for x in v]
    return [x.strip() for x in str(v).split(",") if x.strip()]


def clean_extra(d: dict[str, Any]) -> dict[str, Any]:
    """Extras without empty values (an empty cell carries nothing, and a table cannot tell empty from missing)."""
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in d.items() if v is not None and (not isinstance(v, str) or v.strip())}
