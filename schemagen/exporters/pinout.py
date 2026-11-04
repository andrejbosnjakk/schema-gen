"""Pinout view: one block per component and harness connector, one line per pin (spares included when the part
defines its pins) with signal, wire label and the far end. A two-ended conductor appears on both pinouts and is
still one object (same id). XLSX and HTML."""
from __future__ import annotations

import html
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..core.context import Ctx
from ..core.model import Model, Terminal


def _pin_key(p: str) -> tuple[bool, int, str]:
    return (not p.isdigit(), int(p) if p.isdigit() else 0, p)


def where(ctx: Ctx, t: Terminal) -> str:
    c = ctx.comp.get(t.device)
    cid = c.id if c else t.device
    if c and c.kind in ("splice", "bus"): return cid
    return " ".join(x for x in (cid, t.connector, t.pin) if x)


def far_text(ctx: Ctx, i: int, e: int) -> str:
    """The other end of conductor i, and the net's real ends when that is a splice, bus or harness pin."""
    c = ctx.m.conductors[i]
    t = c.end(3 - e)
    s = where(ctx, t)
    comp = ctx.comp.get(t.device)
    if comp and comp.kind in ("splice", "bus", "harness", "breaker", "fuse"):
        me = c.end(e).key()
        ends = sorted({where(ctx, ctx.m.conductors[j].end(k)) for j, k in ctx.net.net_ends(i)
                       if ctx.m.conductors[j].end(k).key() != me and ctx.net.role(ctx.m.conductors[j].end(k).device) in ("device", "breaker", "bus")})
        if ends and len(ends) <= 8: s += " → " + ", ".join(ends)
    return s


def blocks(m: Model, ctx: Ctx | None = None) -> list[dict[str, Any]]:
    ctx = ctx or Ctx(m)
    out: list[dict[str, Any]] = []
    conds = m.conductors
    for comp in m.components:
        if comp.kind in ("splice", "bus"): continue
        ends = [(i, e) for i, e in ctx.net.by_dev[comp.raw]]
        rows: list[dict[str, Any]] = []
        if comp.kind == "harness":
            con = next((x for x in m.connectors if x.id == comp.id), None)
            by: dict[str, dict[str, list[tuple[int, int]]]] = defaultdict(lambda: {"near": [], "far": []})
            for i, e in ends: by[conds[i].end(e).pin][conds[i].end(e).side or "far"].append((i, e))
            pins = [str(k) for k in range(1, (con.pin_count or 0) + 1)] if con else []
            pins += sorted((p for p in by if p not in pins), key=_pin_key)
            for p in pins:
                sd = by.get(p, {"near": [], "far": []})
                allw = sd["near"] + sd["far"]
                rows.append(dict(connector="", pin=p, name="", type="", signal=" / ".join(sorted({conds[i].name or conds[i].func for i, _ in allw})) or "spare",
                                 labels=", ".join(conds[i].label for i, _ in allw), ids=[conds[i].id for i, _ in allw],
                                 near=", ".join(f"{conds[i].label}: {where(ctx, conds[i].end(3 - e))}" for i, e in sd["near"]),
                                 far=", ".join(f"{conds[i].label}: {where(ctx, conds[i].end(3 - e))}" for i, e in sd["far"])))
            out.append(dict(id=comp.id, title=comp.name, kind="harness", part="", rows=rows)); continue
        part = ctx.parts.get(comp.part) if comp.part else None
        at: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
        for i, e in ends: t = conds[i].end(e); at[(t.connector, t.pin)].append((i, e))
        keys = list(at)
        if part:
            for cd in part.connectors:
                used = [k for k in at if k[0] == cd.id or (cd.match and re.search(cd.match, k[0]))]
                cname = used[0][0] if used else cd.id
                for pin in cd.pins:
                    if (cname, pin.n) not in at: keys.append((cname, pin.n))
        for k in sorted(set(keys), key=lambda k: (k[0], _pin_key(k[1]))):
            d = ctx.pin(Terminal(device=comp.raw, connector=k[0], pin=k[1]))
            ws = at.get(k, [])
            rows.append(dict(connector=k[0], pin=k[1], name=d.name if d else "", type=(d.type or "") if d else "",
                             signal=" / ".join(sorted({conds[i].name or conds[i].func for i, _ in ws})) or "spare",
                             labels=", ".join(conds[i].label for i, _ in ws), ids=[conds[i].id for i, _ in ws],
                             far="; ".join(f"{conds[i].label}: {far_text(ctx, i, e)}" for i, e in ws), near=""))
        out.append(dict(id=comp.id, title=comp.name, kind=comp.kind, part=comp.part, rows=rows))
    return out


COLS = ["connector", "pin", "name", "type", "signal", "labels", "near", "far"]


def write_xlsx(m: Model, path: Path, ctx: Ctx | None = None) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(); ws = wb.active; ws.title = "Pinout"  # type: ignore[union-attr]
    bold, head = Font(bold=True), PatternFill("solid", fgColor="DDDDDD")
    for b in blocks(m, ctx):
        ws.append([f"{b['id']}  {b['title']}" + (f"  (part {b['part']})" if b["part"] else "")])  # type: ignore[union-attr]
        ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)  # type: ignore[union-attr]
        cols = ["pin", "signal", "labels", "near (left half)", "far (right half)"] if b["kind"] == "harness" else \
            ["connector", "pin", "pin name", "type", "signal", "wire label", "far end"]
        ws.append(cols)  # type: ignore[union-attr]
        for c in ws[ws.max_row]: c.font, c.fill = bold, head  # type: ignore[union-attr]
        for r in b["rows"]:
            ws.append([r["pin"], r["signal"], r["labels"], r["near"], r["far"]] if b["kind"] == "harness" else  # type: ignore[union-attr]
                      [r["connector"], r["pin"], r["name"], r["type"], r["signal"], r["labels"], r["far"]])
        ws.append([])  # type: ignore[union-attr]
    for col, w in zip("ABCDEFG", (14, 8, 22, 12, 30, 14, 60)): ws.column_dimensions[col].width = w  # type: ignore[union-attr]
    wb.save(path)


def write_html(m: Model, path: Path, ctx: Ctx | None = None) -> None:
    e = html.escape
    parts = []
    for b in blocks(m, ctx):
        if b["kind"] == "harness":
            head = "<tr><th>pin</th><th>signal</th><th>labels</th><th>near (left half)</th><th>far (right half)</th></tr>"
            rows = "".join(f"<tr class=\"{'spare' if not r['labels'] else ''}\"><td>{e(r['pin'])}</td><td>{e(r['signal'])}</td><td>{e(r['labels'])}</td>"
                           f"<td>{e(r['near'])}</td><td>{e(r['far'])}</td></tr>" for r in b["rows"])
        else:
            head = "<tr><th>connector</th><th>pin</th><th>pin name</th><th>type</th><th>signal</th><th>wire</th><th>far end</th></tr>"
            rows = "".join(f"<tr class=\"{'spare' if not r['labels'] else ''}\"><td>{e(r['connector'])}</td><td>{e(r['pin'])}</td><td>{e(r['name'])}</td>"
                           f"<td>{e(r['type'])}</td><td>{e(r['signal'])}</td><td>{e(r['labels'])}</td><td>{e(r['far'])}</td></tr>" for r in b["rows"])
        parts.append(f"<section id=\"{e(b['id'])}\"><h2>{e(b['id'])} <small>{e(b['title'])}</small></h2><table>{head}{rows}</table></section>")
    css = ("body{font:14px system-ui,sans-serif;margin:16px;color:#111;background:#fff}table{border-collapse:collapse;margin-bottom:8px}"
           "td,th{border:1px solid #bbb;padding:2px 6px;text-align:left}th{background:#eee}tr.spare td{color:#777}"
           "@media (prefers-color-scheme: dark){body{background:#111;color:#eee}th{background:#333}td,th{border-color:#555}}")
    path.write_text(f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Pinout</title><style>{css}</style></head>"
                    f"<body><h1>Pinout</h1>{''.join(parts)}</body></html>", encoding="utf-8")
