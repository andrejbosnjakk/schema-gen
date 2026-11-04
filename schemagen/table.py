"""0.2 interface for tabular wire lists (importers.table, exporters.table hold the code).

The neutral format has one row per conductor. Columns may use the plain names the exporter writes (from, from
connector, ...) or the 0.2 field names (p1, p1c, ...); other names are mapped in schemagen.yml:

    source:
      path: wires.xlsx            # .csv, .xlsx, .json, or a folder of CSV files, relative to schemagen.yml
      sheet: Wires                # xlsx only (default: Wires, else the first sheet)
      header_row: 1               # row holding the column names (csv/xlsx)
      columns: {id: Wire ID, p1: From, p1c: From connector, p1p: From pin}   # field -> column
"""
from pathlib import Path

from .exporters import json_model
from .exporters import table as table_out
from .importers import table as table_in
from .importers.records import FIELDS_02 as FIELDS  # noqa: F401  (0.2 name)


def read(cfg):
    """Rows (dicts with neutral field keys) from the configured source table."""
    return [r.data for r in table_in.read(cfg.root, cfg.source).rows]


def export(pr, path):
    """Write the project: .xlsx workbook, folder of CSVs, .csv (wires only) or .json (whole model). Returns warnings."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        json_model.export(pr.model, path); return []
    return table_out.export(pr.model, path)
