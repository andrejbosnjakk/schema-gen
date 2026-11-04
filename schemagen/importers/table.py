"""Tables: a workbook (XLSX), a folder of CSV files, one CSV, or a JSON list of rows.

    source:
      path: wires.xlsx            # .xlsx, .csv, .json, or a folder of CSV files; relative to schemagen.yml
      sheet: Wires                # xlsx: the wire sheet (default: 'Wires', else the first sheet)
      header_row: 1               # row holding the column names (csv/xlsx)
      columns: {id: Wire ID, p1: From}   # field -> column name; unmapped fields use their plain or 0.2 name

A workbook or folder may also hold the other tables, found by name: Protection, Decisions, Open items, Parts,
Components, Connectors, Labels (CSV files: protection.csv, decisions.csv, open_items.csv, ...).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .records import Record, normalise_keys
from .rows import Tables

SHEETS = {"rows": "Wires", "protection": "Protection", "decisions": "Decisions", "open_items": "Open items",
          "parts": "Parts", "components": "Components", "connectors": "Connectors", "labels": "Labels"}


def csv_name(sheet: str) -> str:
    return sheet.lower().replace(" ", "_") + ".csv"


def _csv(path: Path, header_row: int = 1) -> list[tuple[int, dict[str, Any]]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        lines = fh.readlines()[header_row - 1:]
    return [(header_row + i, r) for i, r in enumerate(csv.DictReader(lines), 1)]


def _xlsx(path: Path) -> Any:
    from openpyxl import load_workbook  # a core dependency since 0.3
    return load_workbook(path, read_only=True, data_only=True)


def _sheet(ws: Any, header_row: int = 1) -> list[tuple[int, dict[str, Any]]]:
    rows = list(ws.iter_rows(min_row=header_row, values_only=True))
    if not rows: return []
    head = [str(h).strip() if h is not None else "" for h in rows[0]]
    return [(header_row + i, {h: v for h, v in zip(head, r) if h}) for i, r in enumerate(rows[1:], 1)]


def _wires(raw: list[tuple[int, dict[str, Any]]], file: str, mapping: dict[str, str]) -> list[Record]:
    out = []
    for n, r in raw:
        data, cols = normalise_keys(r, mapping)
        data = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()}
        have = [data.get(k) not in (None, "") for k in ("id", "p1", "p2")]
        if not have[0] and not all(have[1:]): continue  # section headers and blank lines (no id, not both ends)
        out.append(Record(data, file, n, cols))
    return out


def _plain(raw: list[tuple[int, dict[str, Any]]], file: str) -> list[Record]:
    out = []
    for n, r in raw:
        d: dict[str, Any] = {}
        for k, v in r.items():
            if not k: continue
            k = str(k).strip()
            if k.endswith(":json"):
                if v not in (None, ""): d[k[:-5]] = json.loads(v) if isinstance(v, str) else v
            else: d[k] = v.strip() if isinstance(v, str) else v
        if all(v in (None, "") for v in d.values()): continue
        out.append(Record(d, file, n))
    return out


def read(root: Path, src: dict[str, Any]) -> Tables:
    """The configured source table(s)."""
    path = root / src["path"]
    hr = int(src.get("header_row", 1))
    mapping = src.get("columns", {}) or {}
    t = Tables()
    if path.is_dir():
        for key, sheet in SHEETS.items():
            f = path / csv_name(sheet)
            if not f.exists(): continue
            raw = _csv(f, hr if key == "rows" else 1)
            setattr(t, key, _wires(raw, f.name, mapping) if key == "rows" else _plain(raw, f.name))
    elif path.suffix.lower() == ".xlsx":
        wb = _xlsx(path)
        names = {ws.title: ws for ws in wb.worksheets}
        wsheet = src.get("sheet") or ("Wires" if "Wires" in names else wb.worksheets[0].title)
        t.rows = _wires(_sheet(names[wsheet], hr), f"{path.name} [{wsheet}]", mapping)
        for key, sheet in SHEETS.items():
            if key != "rows" and sheet in names:
                setattr(t, key, _plain(_sheet(names[sheet]), f"{path.name} [{sheet}]"))
    elif path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        t.rows = _wires(list(enumerate(raw, 1)), path.name, mapping)
    else:
        t.rows = _wires(_csv(path, hr), path.name, mapping)
    return t
