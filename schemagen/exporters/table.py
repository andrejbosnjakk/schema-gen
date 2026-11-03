"""Neutral table: the lossless spreadsheet form of the model (and the workbook a team edits).

    .xlsx   one workbook: Wires, Protection, Decisions, Open items, Parts, Components, Connectors, Labels
    folder  the same tables as CSV files (wires.csv, protection.csv, ...)
    .csv    the Wires table only (0.2 behaviour); a warning names the tables left out

Extra input keys get a column of their own; when a key holds non-text values its column is named `key:json` and
holds JSON. Importing the export gives the same model (tests/test_model.py).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..core.model import Model, Part
from ..importers.parts import SHEET_COLS
from ..importers.records import COLUMNS
from ..importers.table import SHEETS, csv_name


def _extras(objs: list[dict[str, Any]]) -> tuple[list[str], dict[str, bool]]:
    keys: list[str] = []
    is_json: dict[str, bool] = {}
    for x in objs:
        for k, v in x.items():
            if k not in is_json: keys.append(k); is_json[k] = False
            if not isinstance(v, str): is_json[k] = True
    return keys, is_json


def _table(base: list[str], rows: list[dict[str, Any]], extras: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    keys, js = _extras(extras)
    head = base + [f"{k}:json" if js[k] else k for k in keys]
    out = []
    for r, ex in zip(rows, extras):
        out.append([r.get(b, "") for b in base] + [("" if k not in ex else json.dumps(ex[k], ensure_ascii=False) if js[k] else ex[k]) for k in keys])
    return head, out


def _num(v: float | None) -> Any:
    return "" if v is None else int(v) if float(v).is_integer() and abs(v) < 1e15 else v


def wires(m: Model) -> tuple[list[str], list[list[Any]]]:
    gset = {(c.id, h.name) for c in m.connectors for h in c.halves if h.guessed}
    rows, extras = [], []
    for c in m.conductors:
        r: dict[str, Any] = {"id": c.id, "label": c.label, "name": c.name, "func": c.func, "bus": c.bus, "cls": c.cls, "awg": c.gauge,
                             "colour": c.colour, "amps": _num(c.current_a), "length": _num(c.length_m), "st": c.status,
                             "subsystem": c.subsystem, "notes": c.notes, "zone": c.zone, "harn": c.harness, "prot": c.protection,
                             "src": "; ".join(s.text() for s in c.sources)}
        for e, t in ((1, c.from_), (2, c.to)):
            r[f"p{e}"], r[f"p{e}c"], r[f"p{e}p"] = t.device, t.connector, t.pin
            comp = m.component(t.device)
            g = comp is not None and (comp.id, t.connector) in gset
            r[f"p{e}side"] = "" if g else t.side
        rows.append({COLUMNS[k]: v for k, v in r.items()}); extras.append(c.extra)
    return _table(list(COLUMNS.values()), rows, extras)


def protection(m: Model) -> tuple[list[str], list[list[Any]]]:
    rows = [{"id": p.id, "kind": p.kind, "rating_A": _num(p.rating_a), "panel": p.panel, "loads": ", ".join(p.loads),
             "trip_curve": p.trip_curve, "i_interrupt_A": _num(p.i_interrupt), "sources": "; ".join(s.text() for s in p.sources)}
            for p in m.protective_devices]
    return _table(["id", "kind", "rating_A", "panel", "loads", "trip_curve", "i_interrupt_A", "sources"], rows,
                  [p.extra for p in m.protective_devices])


def decisions(m: Model) -> tuple[list[str], list[list[Any]]]:
    return _table(["id", "date", "text", "by"], [d.model_dump() for d in m.decisions], [d.extra for d in m.decisions])


def open_items(m: Model) -> tuple[list[str], list[list[Any]]]:
    rows = [dict(o.model_dump(), objects=", ".join(o.objects)) for o in m.open_items]
    return _table(["id", "text", "status", "owner", "objects"], rows, [o.extra for o in m.open_items])


def part_rows(p: Part) -> list[dict[str, Any]]:
    data = p.model_dump(exclude={"id", "device", "kind"}, exclude_defaults=True)
    data["connectors"] = [dict(c.model_dump(exclude={"pins"}), pins=[]) for c in p.connectors]
    out: list[dict[str, Any]] = []
    for c in p.connectors:
        for pin in c.pins:
            out.append({"part": p.id, "device": p.device, "kind": p.kind, "connector": c.id, "match": c.match, "pin": pin.n, "name": pin.name,
                        "type": pin.type or "", "v_max": _num(pin.v_max), "i_max": _num(pin.i_max), "awg_min": _num(pin.awg_min),
                        "awg_max": _num(pin.awg_max), "required": "yes" if pin.required else "", "term": "yes" if pin.term else "",
                        "r_contact": _num(pin.r_contact), "pin extra": json.dumps(pin.extra, ensure_ascii=False) if pin.extra else ""})
    if not out: out.append({"part": p.id, "device": p.device, "kind": p.kind})
    out[0]["part data"] = json.dumps(data, ensure_ascii=False)
    return out


def parts(m: Model) -> tuple[list[str], list[list[Any]]]:
    rows = [r for p in m.parts for r in part_rows(p)]
    return _table(SHEET_COLS + ["pin extra"], rows, [{} for _ in rows])


def components(m: Model) -> tuple[list[str], list[list[Any]]]:
    rows = [{"device": c.raw, "id": c.id, "name": c.name, "kind": c.kind, "part": c.part, "zone": c.zone} for c in m.components]
    return _table(["device", "id", "name", "kind", "part", "zone"], rows, [c.extra for c in m.components])


def connectors(m: Model) -> tuple[list[str], list[list[Any]]]:
    rows = [{"connector": c.id, "name": c.name, "half": h.name, "side": "" if h.guessed else h.side} for c in m.connectors for h in c.halves]
    return _table(["connector", "name", "half", "side"], rows, [{} for _ in rows])


def labels(m: Model) -> tuple[list[str], list[list[Any]]]:
    rows = [e.model_dump() for e in m.ledger.entries]
    return _table(["label", "conductor", "status", "reason", "date"], rows, [{} for _ in rows])


TABLES = {"rows": wires, "protection": protection, "decisions": decisions, "open_items": open_items, "parts": parts,
          "components": components, "connectors": connectors, "labels": labels}


def _csv(path: Path, head: list[str], rows: list[list[Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        cw = csv.writer(fh); cw.writerow(head); cw.writerows(rows)


def export(m: Model, path: Path) -> list[str]:
    """Write the model; returns warnings (tables a single CSV cannot hold)."""
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        from openpyxl import Workbook
        wb = Workbook(); wb.remove(wb.active)  # type: ignore[arg-type]
        for key, fn in TABLES.items():
            head, rows = fn(m)
            ws = wb.create_sheet(SHEETS[key]); ws.append(head)
            for r in rows: ws.append(r)
            ws.freeze_panes = "A2"
        wb.save(path)
        return []
    if path.suffix.lower() == ".csv":
        _csv(path, *wires(m))
        left = [SHEETS[k] for k in TABLES if k != "rows" and TABLES[k](m)[1]]
        return [f"{path.name} holds the wires only; left out: {', '.join(left)} (export to .xlsx or a folder to keep them)"] if left else []
    path.mkdir(parents=True, exist_ok=True)
    for key, fn in TABLES.items(): _csv(path / csv_name(SHEETS[key]), *fn(m))
    return []
