"""Part library: ```yaml schemagen blocks in datasheet cards, and the Parts sheet of a workbook.

Card block (0.2 keys still work; everything else is optional):

    device: '^ECU-\\d+$'            # regex on device codes that are instances of this part
    part: SV-ECU-8                  # part id (default: the card file name)
    kind: controller                # load | sensor | controller | switch | relay | battery | dcdc | breaker | fuse | terminator | device
    load: {model: constant_power, p_w: 6, v_min: 9}
    source: {v_oc: 13.2, r_int: 0.01}            # battery; DC/DC: {v_out, i_limit, r_out, efficiency}
    supply_out: {v: 5.0, i_limit: 0.2}           # regulated outputs on the part's power_out pins
    coil: {a1: COIL.A1, a2: COIL.A2, r: 85, v_pickup: 8.4}
    contacts: [{com: C.COM, no: C.NO}]
    trip_curve: [[1.15, 3600], [2, 12], [10, 0.02]]   # (multiple of rating, seconds)
    connectors:
      - id: J1
        match: '^J1$'
        pins:
          - {n: 1, name: VBAT, type: power_in, v_max: 16, i_max: 5, awg: [18, 24], required: true}
      - {id: LINE, match: '^LINE$', type: power_in}    # a connector without pins: one terminal
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..core.model import KINDS, PIN_TYPES, Part
from .records import Problem, Record

BLOCK = re.compile(r"^```ya?ml schemagen\s*\n(.*?)^```", re.M | re.S)
PIN_KEYS = {"n", "name", "type", "v_max", "i_max", "awg", "awg_min", "awg_max", "required", "term", "r_contact"}
PART_KEYS = {"device", "part", "id", "kind", "connectors", "load", "source", "supply_out", "coil", "contacts", "trip_curve",
             "i_interrupt", "r_closed", "controller", "term"}


def _pin(p: dict[str, Any], warn: list[str], where: str) -> dict[str, Any]:
    out: dict[str, Any] = {"n": str(p.get("n", "")), "name": str(p.get("name", "") or "")}
    t = p.get("type")
    if t is not None:
        t = str(t).strip().lower()
        if t == "can": t = "can_l" if re.search(r"(^|_)L$|LOW", out["name"].upper()) else "can_h"  # 0.2 cards
        if t in PIN_TYPES: out["type"] = t
        else: warn.append(f"{where}: pin {out['n']} has unknown type '{t}' (kept in extra)")
    for k in ("v_max", "i_max", "r_contact", "awg_min", "awg_max", "required", "term"):
        if p.get(k) is not None: out[k] = p[k]
    if isinstance(p.get("awg"), (list, tuple)) and p["awg"]:
        out["awg_min"], out["awg_max"] = min(p["awg"]), max(p["awg"])
    ex = {k: v for k, v in p.items() if k not in PIN_KEYS}
    if t is not None and "type" not in out: ex["type"] = p["type"]
    if ex: out["extra"] = ex
    return out


def from_block(b: dict[str, Any], card: str, warn: list[str]) -> dict[str, Any]:
    """Part dict from one card block."""
    where = f"card {card}"
    conns = []
    for c in b.get("connectors", []) or []:
        pins = [_pin(p, warn, where) for p in c.get("pins", []) or []]
        if not pins and c.get("type"): pins = [_pin({k: v for k, v in c.items() if k in PIN_KEYS - {"n"}} | {"n": ""}, warn, where)]
        ck = {"id", "match", "part", "pins", "type", "i_max", "v_max", "awg", "required", "term", "r_contact"}
        conns.append(dict(id=str(c.get("id", "")), match=str(c.get("match", "") or ""), part=str(c.get("part", "") or ""),
                          pins=pins, extra={k: v for k, v in c.items() if k not in ck}))
    d: dict[str, Any] = dict(id=str(b.get("part") or b.get("id") or Path(card).stem), device=str(b.get("device", "") or ""),
                             card=card, connectors=conns)
    kind = str(b.get("kind", "device"))
    if kind in KINDS: d["kind"] = kind
    else: warn.append(f"{where}: unknown kind '{kind}' (kept in extra)")
    for k in ("load", "source", "coil", "contacts", "trip_curve", "i_interrupt", "r_closed", "controller", "term"):
        if b.get(k) is not None: d[k] = b[k]
    if b.get("supply_out"):
        so = dict(b["supply_out"]); so["v_out"] = so.pop("v", so.get("v_out")); d["supply_out"] = so
    for c in d.get("contacts", []) or []:
        for k in list(c): c[k] = str(c[k])
    ex = {k: v for k, v in b.items() if k not in PART_KEYS}
    if kind not in KINDS: ex["kind"] = kind
    if ex: d["extra"] = ex
    return d


def from_cards(folder: Path, warn: list[str], problems: list[Problem]) -> list[Part]:
    out: list[Part] = []
    seen: set[str] = set()
    for path in sorted(folder.glob("*.md")) if folder.exists() else []:
        for m in BLOCK.finditer(path.read_text(encoding="utf-8")):
            b = yaml.safe_load(m.group(1)) or {}
            d = from_block(b, path.name, warn)
            if d["id"] in seen:
                d["id"] = f"{d['id']}~{path.stem}"
            try: out.append(Part.model_validate(d))
            except ValidationError as e:
                for er in e.errors(): problems.append(Problem(path.name, None, ".".join(map(str, er["loc"])), er["msg"]))
                continue
            seen.add(d["id"])
    return out


SHEET_COLS = ["part", "device", "kind", "connector", "match", "pin", "name", "type", "v_max", "i_max", "awg_min", "awg_max",
              "required", "term", "r_contact", "part data"]


def from_sheet(recs: list[Record], problems: list[Problem]) -> list[Part]:
    """Parts sheet: one row per pin; part-level data (load, source, ...) as JSON in 'part data' on the part's first row."""
    parts: dict[str, dict[str, Any]] = {}
    for r in recs:
        d = r.data
        pid = str(d.get("part", "") or "")
        if not pid: problems.append(Problem(r.file, r.row, "part", "part id missing")); continue
        p = parts.setdefault(pid, dict(id=pid, device=str(d.get("device") or ""), kind=str(d.get("kind") or "device"), connectors=[]))
        if d.get("part data"):
            try: p.update(json.loads(str(d["part data"])))
            except json.JSONDecodeError as e: problems.append(Problem(r.file, r.row, "part data", f"not JSON: {e}"))
        cid = str(d.get("connector") or "")
        if not cid and d.get("pin") in (None, ""): continue
        conn = next((c for c in p["connectors"] if c["id"] == cid), None)
        if conn is None:
            conn = dict(id=cid, match=str(d.get("match") or ""), pins=[]); p["connectors"].append(conn)
        pin: dict[str, Any] = {"n": str(d.get("pin") if d.get("pin") is not None else ""), "name": str(d.get("name") or "")}
        for k in ("type", "v_max", "i_max", "awg_min", "awg_max", "r_contact"):
            if d.get(k) not in (None, ""): pin[k] = d[k]
        for k in ("required", "term"):
            if d.get(k) not in (None, ""): pin[k] = str(d[k]).strip().lower() in ("1", "true", "yes", "x")
        if "pin extra" in d and d["pin extra"]: pin["extra"] = json.loads(str(d["pin extra"]))
        conn["pins"].append(pin)
    out = []
    for d in parts.values():
        try: out.append(Part.model_validate(d))
        except ValidationError as e:
            for er in e.errors(): problems.append(Problem("Parts", None, ".".join(map(str, er["loc"])), f"{d['id']}: {er['msg']}"))
    return out
