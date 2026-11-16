"""Pinout view and reintegration checklist: one block per component (splices, buses and harness connectors included),
one line per conductor end (spare pins too when the part defines its pins) with signal, wire label, gauge, colour and
the far end by display name. A conductor appears once under each of its two ends and is still one object (same id).
XLSX (print-ready, with empty check columns) and HTML."""
from __future__ import annotations

import datetime as _dt
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
CHECKS = [("Connected", 10), ("Continuity", 10), ("initials", 9)]


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


CSS = ("@page{size:A4 portrait;margin:12mm 10mm}"
       "*{box-sizing:border-box}body{font:8pt/1.25 Arial,Helvetica,sans-serif;color:#000;background:#fff;margin:0}"
       "h1{font-size:13pt;margin:0 0 1mm}p.sub{margin:0 0 5mm;font-size:9pt}"
       "section{margin:0 0 5mm}h2{font-size:10pt;margin:0 0 1mm;break-after:avoid;page-break-after:avoid}h2 small{font-weight:normal}"
       "table{border-collapse:collapse;width:100%;table-layout:fixed;break-before:avoid;page-break-before:avoid}"
       "thead{display:table-header-group}tr{break-inside:avoid;page-break-inside:avoid}"
       "td,th{border:1px solid #000;padding:1mm 1.5mm;text-align:left;vertical-align:top;overflow-wrap:anywhere}"
       "th{font-weight:bold}td.tick,th.tick{width:17mm;text-align:center}"
       "span.box{display:inline-block;width:3.5mm;height:3.5mm;border:1px solid #000;vertical-align:middle}tr.spare td{font-style:italic}"
       "@media screen{body{margin:8mm}}")
WIDTHS = {"connector": 11, "pin": 5, "name": 11, "label": 7, "wire": 15, "gauge": 5, "colour": 6, "far": 28}


def write_html(m: Model, path: Path, ctx: Ctx | None = None, project: str = "") -> None:
    """The wiring checklist a technician takes to the aircraft: one table per component, two tick boxes per row, set up to
    print on A4 portrait (header repeats on each page, a heading stays with its table). No external resources."""
    e = html.escape
    cols = "".join(f"<col style=\"width:{WIDTHS[k]}%\">" for k, _, _ in COLS) + "<col style=\"width:17mm\"><col style=\"width:17mm\">"
    head = ("<thead><tr>" + "".join(f"<th>{e(h)}</th>" for _, h, _ in COLS) + "<th class=\"tick\">Connected</th><th class=\"tick\">Continuity</th></tr></thead>")
    parts = []
    for b in blocks(m, ctx):
        rows = "".join(("<tr>" if r["id"] else '<tr class="spare">')
                       + "".join(f"<td>{e('spare' if k == 'wire' and not r['id'] else str(r[k]))}</td>" for k, _, _ in COLS)
                       + "<td class=\"tick\"><span class=\"box\"></span></td>" * 2 + "</tr>" for r in b["rows"])
        parts.append(f"<section id=\"{e(b['id'])}\"><h2>{e(b['title'] or b['id'])} <small>{e(b['id'])}</small></h2>"
                     f"<table><colgroup>{cols}</colgroup>{head}<tbody>{rows}</tbody></table></section>")
    sub = " · ".join(x for x in (project, _dt.date.today().isoformat()) if x)
    path.write_text(f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Wiring checklist</title><style>{CSS}</style></head>"
                    f"<body><h1>Wiring checklist</h1><p class=\"sub\">{e(sub)}</p>{''.join(parts)}</body></html>", encoding="utf-8")
