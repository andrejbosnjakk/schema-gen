"""WireViz YAML (connectors, cables, connections) to wire rows. Reads the YAML only; WireViz itself is never imported.

Each connection set [{A: [pins]}, {W: [wires]}, {B: [pins]}] gives one conductor per wire; simple connectors
(splices, `style: simple`) become splice ends. Cable wire labels or colours become labels, the cable gauge the gauge.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .records import Record
from .rows import Tables


def _ends(item: Any) -> tuple[str, list[Any]]:
    if isinstance(item, str): return item, [None]
    (k, v), = item.items()
    return str(k), v if isinstance(v, list) else [v]


def read(path: Path) -> Tables:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    conns, cables = doc.get("connectors", {}) or {}, doc.get("cables", {}) or {}
    t = Tables()
    n = 0
    for i, cset in enumerate(doc.get("connections", []) or [], 1):
        if len(cset) < 3: continue
        (a, ap), (w, wp), (b, bp) = _ends(cset[0]), _ends(cset[1]), _ends(cset[2])
        cab = cables.get(w, {}) or {}
        labels, colours = cab.get("wirelabels") or [], cab.get("colors") or []
        for k, wi in enumerate(wp):
            idx = int(wi) - 1 if str(wi).isdigit() else k
            pa = ap[k] if k < len(ap) else ap[-1]
            pb = bp[k] if k < len(bp) else bp[-1]
            n += 1
            lab = str(labels[idx]) if idx < len(labels) else ""
            row: dict[str, Any] = dict(id=f"{w}-{wi}", label=lab.split(" · ")[0] if lab else f"{w}-{wi}",
                                       p1=f"{a} {conns.get(a, {}).get('type', '')}".strip(), p1c="", p1p="" if pa is None else str(pa),
                                       p2=f"{b} {conns.get(b, {}).get('type', '')}".strip(), p2c="", p2p="" if pb is None else str(pb),
                                       awg=str(cab.get("gauge", "")).split()[0] if cab.get("gauge") else "", harn=w)
            if idx < len(colours): row["colour"] = str(colours[idx])
            if cab.get("length"): row["length"] = cab["length"]
            t.rows.append(Record(row, path.name, i))
    return t
