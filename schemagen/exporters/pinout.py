"""Pinout view and reintegration checklist: one block per component (splices, buses and harness connectors included),
one line per conductor end (spare pins too when the part defines its pins) with signal, wire label, gauge, colour and
the far end by display name. A conductor appears once under each of its two ends and is still one object (same id).
XLSX (print-ready, with empty check columns) and HTML."""
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
    """A terminal by its display name (the code when there is none): name, connector, pin; splices and buses by name."""
    c = ctx.comp.get(t.device)
    nm = (c.name or c.id) if c else t.device
    if c and c.kind in ("splice", "bus"): return nm
    return " ".join(x for x in (nm, t.connector, t.pin) if x)


def far_text(ctx: Ctx, i: int, e: int) -> str:
    """The other end of conductor i; through a splice or harness pin, also where the wire finally lands (devices,
    breakers, buses), walking away from this end only, so a row never points back at itself."""
    net, conds = ctx.net, ctx.m.conductors
    t = conds[i].end(3 - e)
    s = where(ctx, t)
    if net.role(t.device) not in ("splice", "harness"): return s
    seen, todo, ends = {i}, [net.node(i, 3 - e)], []
    while todo:
        for j, k in net.at[todo.pop()]:
            if j in seen: continue
            seen.add(j)
            o = conds[j].end(3 - k)
            if net.role(o.device) in ("splice", "harness"): todo.append(net.node(j, 3 - k))
            else: ends.append(where(ctx, o))
    ends = sorted(set(ends))
    return s + (" → " + ", ".join(ends) if ends and len(ends) <= 8 else "")


def _row(ctx: Ctx, connector: str, pin: str, d: Any, ie: tuple[int, int] | None) -> dict[str, Any]:
    if ie is None:
        return dict(connector=connector, pin=pin, name=d.name if d else "", type=(d.type or "") if d else "", signal="spare",
                    id="", label="", wire="", gauge="", colour="", far="", here="")
    cd = ctx.m.conductors[ie[0]]
    return dict(connector=connector, pin=pin, name=d.name if d else "", type=(d.type or "") if d else "", signal=cd.name or cd.func,
                id=cd.id, label=cd.label, wire=cd.name, gauge=cd.gauge, colour=cd.colour_code or cd.colour, far=far_text(ctx, *ie),
                here=where(ctx, cd.end(ie[1])))


def blocks(m: Model, ctx: Ctx | None = None) -> list[dict[str, Any]]:
    """One block per component (splices, buses and harness connectors included), one row per conductor end, so every
    conductor is listed once under each of its two ends; spare pins from part data (or a harness pin count) too."""
    ctx = ctx or Ctx(m)
    out: list[dict[str, Any]] = []
    conds = m.conductors
    for comp in m.components:
        at: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
        for i, e in ctx.net.by_dev[comp.raw]: t = conds[i].end(e); at[(t.connector, t.pin)].append((i, e))
        keys = list(at)
        part = ctx.parts.get(comp.part) if comp.part else None
        if comp.kind == "harness":
            con = next((x for x in m.connectors if x.id == comp.id), None)
            wired = {p for _, p in at}
            for h in (con.halves if con else []):
                keys += [(h.name, str(k)) for k in range(1, (con.pin_count or 0) + 1) if str(k) not in wired]  # type: ignore[union-attr]
        elif part:
            for cd in part.connectors:
                used = [k for k in at if k[0] == cd.id or (cd.match and re.search(cd.match, k[0]))]
                cname = used[0][0] if used else cd.id
                keys += [(cname, pin.n) for pin in cd.pins if (cname, pin.n) not in at]
        order = (lambda k: (_pin_key(k[1]), k[0])) if comp.kind == "harness" else (lambda k: (k[0], _pin_key(k[1])))
        rows = []
        for k in sorted(set(keys), key=order):
            d = ctx.pin(Terminal(device=comp.raw, connector=k[0], pin=k[1]))
            rows += [_row(ctx, k[0], k[1], d, ie) for ie in at.get(k, [])] or [_row(ctx, k[0], k[1], d, None)]
        out.append(dict(id=comp.id, title=comp.name, kind=comp.kind, part=comp.part, rows=rows))
    return out


COLS = [("connector", "connector / half", 16), ("pin", "pin", 6), ("name", "pin name", 16), ("label", "wire label", 10),
        ("wire", "wire name", 26), ("gauge", "gauge", 7), ("colour", "colour", 8), ("far", "far end", 52)]
CHECKS = [("connected", 10), ("continuity", 10), ("initials", 9)]


def write_xlsx(m: Model, path: Path, ctx: Ctx | None = None, page_breaks: bool = False) -> None:
    """A printable reintegration checklist: one block per component (title, header, one row per conductor end, empty
    check columns), A4 landscape fitted to the page width; `page_breaks` starts every component on a new page."""
    from openpyxl import Workbook
    from openpyxl.styles import Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.pagebreak import Break
    wb = Workbook(); ws = wb.active; ws.title = "Pinout"  # type: ignore[union-attr]
    bold, head = Font(bold=True), PatternFill("solid", fgColor="DDDDDD")
    thin = Side(style="thin", color="999999"); box = Border(left=thin, right=thin, top=thin, bottom=thin)
    n = len(COLS) + len(CHECKS)
    for b in blocks(m, ctx):
        ws.append([f"{b['title'] or b['id']}" + (f"  ({b['id']})" if b["title"] and b["id"] not in b["title"] else "")  # type: ignore[union-attr]
                   + (f"  part {b['part']}" if b["part"] else "")])
        ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)  # type: ignore[union-attr]
        ws.append([h for _, h, _ in COLS] + [h for h, _ in CHECKS])  # type: ignore[union-attr]
        for c in ws[ws.max_row]: c.font, c.fill, c.border = bold, head, box  # type: ignore[union-attr]
        for r in b["rows"]:
            ws.append([r[k] for k, _, _ in COLS] + [""] * len(CHECKS))  # type: ignore[union-attr]
            for c in ws[ws.max_row]: c.border = box  # type: ignore[union-attr]
        ws.append([])  # type: ignore[union-attr]
        if page_breaks: ws.row_breaks.append(Break(id=ws.max_row))  # type: ignore[union-attr]
    for j, w in enumerate([w for _, _, w in COLS] + [w for _, w in CHECKS], 1): ws.column_dimensions[get_column_letter(j)].width = w  # type: ignore[union-attr]
    ps = ws.page_setup  # type: ignore[union-attr]
    ps.paperSize, ps.orientation, ps.fitToWidth, ps.fitToHeight = ws.PAPERSIZE_A4, ws.ORIENTATION_LANDSCAPE, 1, 0  # type: ignore[union-attr]
    ws.sheet_properties.pageSetUpPr.fitToPage = True  # type: ignore[union-attr]
    ws.print_area = f"A1:{get_column_letter(n)}{ws.max_row}"  # type: ignore[union-attr]
    ws.print_options.gridLines = False  # type: ignore[union-attr]
    wb.save(path)


def write_html(m: Model, path: Path, ctx: Ctx | None = None) -> None:
    e = html.escape
    head = "<tr>" + "".join(f"<th>{h}</th>" for _, h, _ in COLS) + "</tr>"
    parts = []
    for b in blocks(m, ctx):
        rows = "".join(f"<tr class=\"{'spare' if not r['id'] else ''}\">" + "".join(f"<td>{e(str(r[k]))}</td>" for k, _, _ in COLS)
                       + ("<td>spare</td>" if not r["id"] else "<td></td>") + "</tr>" for r in b["rows"])
        parts.append(f"<section id=\"{e(b['id'])}\"><h2>{e(b['title'] or b['id'])} <small>{e(b['id'])}</small></h2>"
                     f"<table>{head.replace('</tr>', '<th></th></tr>')}{rows}</table></section>")
    css = ("body{font:14px system-ui,sans-serif;margin:16px;color:#111;background:#fff}table{border-collapse:collapse;margin-bottom:8px}"
           "td,th{border:1px solid #bbb;padding:2px 6px;text-align:left}th{background:#eee}tr.spare td{color:#777}"
           "@media (prefers-color-scheme: dark){body{background:#111;color:#eee}th{background:#333}td,th{border-color:#555}}")
    path.write_text(f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Pinout</title><style>{css}</style></head>"
                    f"<body><h1>Pinout</h1>{''.join(parts)}</body></html>", encoding="utf-8")
