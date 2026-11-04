"""Label ledger: printed labels are never reused. `schemagen labels <project> --update` records every label in use
and retires the ones that left the wire list, with a reason; the `label-reused` rule catches a retired label printed again."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .model import LabelEntry, LabelLedger, Model


def update(m: Model, reason: str = "", today: str | None = None) -> tuple[LabelLedger, list[str]]:
    """New ledger: active entries for labels in use, retired entries (with a reason) for labels no longer used."""
    today = today or _dt.date.today().isoformat()
    entries = [e.model_copy() for e in m.ledger.entries]
    by_label = {e.label: e for e in entries}
    in_use = {c.label: c.id for c in m.conductors}
    msgs = []
    for lab, cid in in_use.items():
        e = by_label.get(lab)
        if e is None:
            e = LabelEntry(label=lab, conductor=cid, status="active", date=today); entries.append(e); by_label[lab] = e
            msgs.append(f"added {lab} ({cid})")
        elif e.status == "active" and e.conductor != cid:
            msgs.append(f"{lab} moved from {e.conductor} to {cid}: a printed label belongs to one conductor (label-reused will not flag this)")
    for e in entries:
        if e.status == "active" and e.label not in in_use:
            e.status, e.reason, e.date = "retired", reason or f"no longer in the wire list (conductor {e.conductor})", today
            msgs.append(f"retired {e.label}: {e.reason}")
    return LabelLedger(entries=entries), msgs


def retire(led: LabelLedger, label: str, reason: str, today: str | None = None) -> LabelLedger:
    out = [e.model_copy() for e in led.entries]
    for e in out:
        if e.label == label: e.status, e.reason, e.date = "retired", reason, today or _dt.date.today().isoformat()
    if not any(e.label == label for e in out): out.append(LabelEntry(label=label, status="retired", reason=reason, date=today or ""))
    return LabelLedger(entries=out)


def save(led: LabelLedger, path: Path) -> None:
    path.write_text(json.dumps(led.model_dump(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
