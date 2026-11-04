"""Differences between two versions of a project: conductors, pins, labels, protection and open items.
`schemagen diff A B` takes project folders or git revisions (the project path is then taken inside each revision)."""
from __future__ import annotations

import html
import json
import subprocess
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from .model import Conductor, Model

FIELDS = ["label", "name", "from", "to", "func", "bus", "cls", "gauge", "colour", "length_m", "current_a", "status", "protection",
          "harness", "zone", "notes", "sources", "extra"]


def _val(c: Conductor, f: str) -> Any:
    if f in ("from", "to"):
        t = c.from_ if f == "from" else c.to
        return " ".join(x for x in (t.device, t.connector, t.pin) if x)
    if f == "sources": return "; ".join(s.text() for s in c.sources)
    return getattr(c, f)


def _keyed(a: dict[str, Any], b: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)), "changed": {}}
    for k in sorted(set(a) & set(b)):
        ch = {f: [a[k][f], b[k][f]] for f in fields if a[k][f] != b[k][f]}
        if ch: out["changed"][k] = ch
    return out


def pins(m: Model) -> dict[str, list[str]]:
    comp = {c.raw: c.id for c in m.components}
    out: dict[str, list[str]] = {}
    for c in m.conductors:
        for t in (c.from_, c.to):
            k = f"{comp.get(t.device, t.device)}/{t.connector}/{t.pin}" + (f" ({t.side})" if t.side else "")
            out.setdefault(k, []).append(c.id)
    return {k: sorted(v) for k, v in out.items()}


def diff(a: Model, b: Model) -> dict[str, Any]:
    ca = {c.id: {f: _val(c, f) for f in FIELDS} for c in a.conductors}
    cb = {c.id: {f: _val(c, f) for f in FIELDS} for c in b.conductors}
    pa, pb = pins(a), pins(b)
    pin = {"added": sorted(set(pb) - set(pa)), "removed": sorted(set(pa) - set(pb)),
           "changed": {k: [pa[k], pb[k]] for k in sorted(set(pa) & set(pb)) if pa[k] != pb[k]}}
    la, lb = {c.label for c in a.conductors}, {c.label for c in b.conductors}
    pf = ["kind", "rating_a", "panel", "loads", "trip_curve", "i_interrupt"]
    prot = _keyed({p.id: p.model_dump() for p in a.protective_devices}, {p.id: p.model_dump() for p in b.protective_devices}, pf)
    of = ["text", "status", "owner", "objects"]
    oi = _keyed({o.id: o.model_dump() for o in a.open_items}, {o.id: o.model_dump() for o in b.open_items}, of)
    out = {"conductors": _keyed(ca, cb, FIELDS), "pins": pin, "labels": {"added": sorted(lb - la), "removed": sorted(la - lb)},
           "protection": prot, "open_items": oi}
    out["summary"] = {k: {kk: len(vv) for kk, vv in v.items()} for k, v in out.items()}
    return out


def text(d: dict[str, Any]) -> str:
    lines = []
    for sec in ("conductors", "pins", "labels", "protection", "open_items"):
        v = d[sec]
        for k in v.get("added", []): lines.append(f"+ {sec[:-1] if sec.endswith('s') else sec} {k}")
        for k in v.get("removed", []): lines.append(f"- {sec[:-1] if sec.endswith('s') else sec} {k}")
        for k, ch in v.get("changed", {}).items():
            if isinstance(ch, dict): lines += [f"~ {sec[:-1]} {k} {f}: {o!r} -> {n!r}" for f, (o, n) in ch.items()]
            else: lines.append(f"~ {sec[:-1]} {k}: {ch[0]} -> {ch[1]}")
    s = d["summary"]
    lines.append("summary: " + "; ".join(f"{k} " + ", ".join(f"{n} {kk}" for kk, n in v.items()) for k, v in s.items()))
    return "\n".join(lines) + "\n"


def to_html(d: dict[str, Any], title: str = "schemagen diff") -> str:
    e = html.escape
    rows = []
    for line in text(d).splitlines()[:-1]:
        cls = {"+": "add", "-": "del", "~": "chg"}.get(line[:1], "")
        rows.append(f"<tr class=\"{cls}\"><td>{e(line[:1])}</td><td>{e(line[2:])}</td></tr>")
    css = ("body{font:14px system-ui,sans-serif;margin:16px}td{padding:1px 6px;font-family:monospace}.add{background:#e6ffed}"
           ".del{background:#ffeef0}.chg{background:#fff8c5}@media (prefers-color-scheme: dark){body{background:#111;color:#eee}"
           ".add{background:#12361e}.del{background:#3c1618}.chg{background:#3a3412}}")
    summ = e(text(d).splitlines()[-1])
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{e(title)}</title><style>{css}</style></head><body>"
            f"<h1>{e(title)}</h1><p>{summ}</p><table>{''.join(rows)}</table></body></html>")


def checkout(rev: str, project: Path) -> Path:
    """Extract the project folder as it is at a git revision into a temporary folder; returns the project path there."""
    project = project.resolve()
    top = Path(subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
    rel = project.relative_to(top)
    data = subprocess.run(["git", "-C", str(top), "archive", "--format=tar", rev, str(rel) if str(rel) != "." else "."],
                          capture_output=True, check=True).stdout
    tmp = Path(tempfile.mkdtemp(prefix="schemagen-diff-"))
    with tarfile.open(fileobj=BytesIO(data)) as tf:
        try: tf.extractall(tmp, filter="data")
        except TypeError: tf.extractall(tmp)  # Python without extraction filters
    return tmp / rel


def dumps(d: dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False, indent=1, default=str)
