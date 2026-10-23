"""Tabular wire lists: read rows from CSV / XLSX / JSON, and export any project to the neutral CSV.

The neutral format has one row per conductor with the FIELDS below. Other column names are mapped in schemagen.yml:

    source:
      path: wires.xlsx            # .csv, .xlsx or .json (a list of row objects), relative to schemagen.yml
      sheet: Wires                # xlsx only (default: first sheet)
      header_row: 1               # row holding the column names (csv/xlsx)
      columns: {id: Wire ID, p1: From, p1c: From connector, p1p: From pin}   # field -> column; unmapped = same name
"""
import csv, json

FIELDS = ["id", "label", "name", "p1", "p1c", "p1p", "p2", "p2c", "p2p", "func", "bus", "awg", "amps", "st", "subsystem", "notes"]


def _rows_xlsx(path, sheet, header_row):
    from openpyxl import load_workbook  # optional dependency: pip install schemagen[xlsx]
    ws = load_workbook(path, read_only=True, data_only=True)
    ws = ws[sheet] if sheet else ws.worksheets[0]
    rows = list(ws.iter_rows(min_row=header_row, values_only=True))
    head = [str(h).strip() if h is not None else "" for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:]]


def read(cfg):
    """Rows (dicts with FIELDS keys) from the configured source table."""
    src = cfg.source
    path = cfg.root / src["path"]
    hr = int(src.get("header_row", 1))
    if path.suffix.lower() == ".xlsx":
        raw = _rows_xlsx(path, src.get("sheet"), hr)
    elif path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            lines = fh.readlines()[hr - 1:]
        raw = list(csv.DictReader(lines))
    cols = src.get("columns", {})
    out = []
    for r in raw:
        row = {f: r.get(cols.get(f, f)) for f in FIELDS}
        row = {k: ("" if v is None else str(v).strip()) for k, v in row.items()}
        if row["id"] and row["p1"] and row["p2"]: out.append(row)  # skip section headers and blank lines
    return out


def export(pr, path):
    """Write the project's wires in the neutral format (CSV, or JSON when path ends in .json)."""
    rows = [{f: w.get(f, "") for f in FIELDS} for w in pr.wires]
    if str(path).endswith(".json"):
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"); return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        cw = csv.DictWriter(fh, FIELDS); cw.writeheader(); cw.writerows(rows)
