"""Change sets: reviewable edits to the wire list, stored as JSON files in <project>/changes/ and applied on load.

    {"id": "0001-direction", "title": "...", "author": "...", "created": "2026-11-03T12:00:00",
     "ops": [{"op": "set", "id": "W12", "field": "p1", "old": "...", "new": "..."},
             {"op": "add", "id": "W99", "row": {...}}, {"op": "delete", "id": "W7"}]}

Fields are neutral field names (p1, p1c, awg, st, ...). A `set` whose value is already `new` is skipped (applying
twice is harmless); one whose current value is neither `old` nor `new` is a conflict and is reported, not applied.
The app saves every edit this way and undo removes the last change set, so project files stay git-friendly.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from ..importers.records import Record, text
from .model import Base

FLIP_FIELDS = [("p1", "p2"), ("p1c", "p2c"), ("p1p", "p2p"), ("p1side", "p2side")]


class Op(Base):
    op: Literal["set", "add", "delete"]
    id: str
    field: str = ""
    old: Any = None
    new: Any = None
    row: dict[str, Any] = Field(default_factory=dict)


class ChangeSet(Base):
    id: str
    title: str = ""
    author: str = ""
    created: str = ""
    ops: list[Op] = Field(default_factory=list)


def folder(root: Path) -> Path:
    return root / "changes"


def load_all(root: Path) -> list[ChangeSet]:
    d = folder(root)
    return [ChangeSet.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d.exists() else []


def apply(recs: list[Record], sets: list[ChangeSet]) -> list[str]:
    """Apply change sets to wire records in place; returns conflict messages."""
    msgs: list[str] = []
    for cs in sets:
        by_id = {text(r.data.get("id")): r for r in recs}
        for op in cs.ops:
            r = by_id.get(op.id)
            if op.op == "add":
                if r is None:
                    nr = Record(dict(op.row, id=op.id), f"changes/{cs.id}.json", None); recs.append(nr); by_id[op.id] = nr
                continue
            if r is None: msgs.append(f"change set {cs.id}: no conductor {op.id}"); continue
            if op.op == "delete": recs.remove(r); by_id.pop(op.id); continue
            cur = text(r.data.get(op.field))
            if cur == text(op.new): continue
            if cur != text(op.old):
                msgs.append(f"change set {cs.id}: {op.id}.{op.field} is '{cur}', expected '{text(op.old)}' (not applied)"); continue
            r.data[op.field] = op.new
    return msgs


def flip_ops(rec: Record) -> list[Op]:
    """Swap the two ends of a conductor (labels and everything else stay)."""
    ops = []
    d = rec.data
    for a, b in FLIP_FIELDS:
        va, vb = text(d.get(a)), text(d.get(b))
        if va != vb:
            ops += [Op(op="set", id=text(d["id"]), field=a, old=va, new=vb), Op(op="set", id=text(d["id"]), field=b, old=vb, new=va)]
    return ops


def new_set(title: str, ops: list[Op], author: str = "", slug: str = "") -> ChangeSet:
    now = _dt.datetime.now().replace(microsecond=0).isoformat()
    return ChangeSet(id=slug or re.sub(r"\W+", "-", title.lower()).strip("-")[:40], title=title, author=author, created=now, ops=ops)


def save(root: Path, cs: ChangeSet) -> Path:
    """Store a change set as the next numbered file in <project>/changes/."""
    d = folder(root); d.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(m.group(1)) for p in d.glob("*.json") if (m := re.match(r"(\d+)-", p.name))] or [0])
    cs = cs.model_copy(update={"id": f"{n:04d}-{cs.id}"})
    p = d / f"{cs.id}.json"
    p.write_text(json.dumps(cs.model_dump(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def undo(root: Path) -> Path | None:
    """Remove the last change set (it stays in git history)."""
    d = folder(root)
    files = sorted(d.glob("*.json")) if d.exists() else []
    if not files: return None
    files[-1].unlink()
    return files[-1]
