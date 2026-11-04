"""Spreadsheet views: the readable wire list (the project's display naming) and the editable sheet template
(the neutral workbook with data-validation dropdowns that survive an upload to Google Sheets)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.model import Model
from ..importers.records import COLUMNS
from . import table as table_out

GAUGES = ["4", "6", "8", "10", "12", "14", "16", "18", "20", "22", "24", "26", "TBD"]
STATUSES = ["Proposed", "Released", "Open", "Changed", "Retired"]


def wirelist_xlsx(pr: Any, path: Path) -> None:
    """Readable wire list: display names (display.py) for devices and terminals, one row per conductor."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook(); ws = wb.active; ws.title = "Wire list"
    head = ["label", "name", "from", "from terminal", "to", "to terminal", "gauge", "colour", "function class", "length_m", "status", "subsystem"]
    ws.append(head)
    for c in ws[1]: c.font = Font(bold=True)
    for w, c in zip(pr.wires, pr.model.conductors):
        ws.append([w["label"], w["name"], pr.device(w["p1"]), pr.terminal(w["p1"], w["p1c"], w["p1p"]), pr.device(w["p2"]),
                   pr.terminal(w["p2"], w["p2c"], w["p2p"]), w["gauge"], w["color"], w["kind"], c.length_m if c.length_m is not None else "",
                   w.get("st", ""), w.get("subsystem", "")])
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    for col, wd in zip("ABCDEFGHIJKL", (8, 28, 30, 18, 30, 18, 8, 8, 12, 9, 10, 10)): ws.column_dimensions[col].width = wd
    wb.save(path)


def lists(m: Model | None, cfg: Any = None) -> dict[str, list[str]]:
    """Dropdown values from the model and the palette."""
    classes = list((cfg.colours if cfg else {}).keys()) or ["14 V", "24 V", "5 V", "GND", "signal", "CAN_H", "CAN_L"]
    st = list(dict.fromkeys(STATUSES + ([c.status for c in m.conductors if c.status] if m else [])))
    comps = sorted({c.raw for c in m.components}) if m else []
    halves = sorted({h.name for c in m.connectors for h in c.halves}) if m else []
    conns = sorted({t.connector for c in m.conductors for t in (c.from_, c.to) if t.connector} | set(halves)) if m else []
    return {"function class": classes, "gauge": GAUGES, "status": st, "device": comps, "connector": conns, "side": ["near", "far"],
            "colour": sorted((cfg.colours if cfg else {}).values()) or ["RD", "BK", "BU"]}


def template_xlsx(m: Model | None, path: Path, cfg: Any = None) -> None:
    """The neutral workbook (empty, or prefilled from the model) plus a Lists sheet; dropdowns on the Wires columns.
    Validation ranges point at plain cell ranges on the Lists sheet, which Google Sheets keeps on upload."""
    from openpyxl import Workbook, load_workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    if m is not None: table_out.export(m, path)
    else:
        wb0 = Workbook(); wb0.active.title = "Wires"; wb0.active.append(list(COLUMNS.values())); wb0.save(path)
    wb = load_workbook(path)
    ls = wb.create_sheet("Lists")
    L = lists(m, cfg)
    for j, (k, vals) in enumerate(L.items(), 1):
        ls.cell(1, j, k)
        for i, v in enumerate(vals, 2): ls.cell(i, j, v)
    ws = wb["Wires"]
    head = [c.value for c in ws[1]]
    nrows = max(ws.max_row + 500, 1000)
    use = {"function class": "function class", "gauge": "gauge", "status": "status", "from": "device", "to": "device",
           "from connector": "connector", "to connector": "connector", "from side": "side", "to side": "side", "colour": "colour"}
    keys = list(L)
    for col, lst in use.items():
        if col not in head or not L[lst]: continue
        j = keys.index(lst) + 1
        ref = f"Lists!${get_column_letter(j)}$2:${get_column_letter(j)}${len(L[lst]) + 1}"
        strict = lst in ("gauge", "side")
        dv = DataValidation(type="list", formula1=ref, allow_blank=True, showErrorMessage=strict, errorStyle="stop" if strict else "warning")
        dv.error, dv.prompt = f"pick a {lst} from the list", f"{lst}: pick from the list (Lists sheet)"
        letter = get_column_letter(head.index(col) + 1)
        dv.add(f"{letter}2:{letter}{nrows}")
        ws.add_data_validation(dv)
    for j, h in enumerate(head, 1): ws.column_dimensions[get_column_letter(j)].width = max(10, min(30, len(str(h)) + 4))
    wb.save(path)
