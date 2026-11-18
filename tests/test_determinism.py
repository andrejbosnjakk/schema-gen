"""The same project draws the same bytes: geometry JSON and PDFs are identical run to run, and the PDF's dates are the source's, not the clock's."""
from __future__ import annotations

import json
from pathlib import Path

from schemagen.app import diagrams as dg
from schemagen.app.server import State
from schemagen.drawing.engine import draw, meta

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"


def test_geometry_json_is_identical():
    st = State(DEMO)
    a, b = (json.dumps(draw(st, "component:ECU", "A3", meta(st.cfg)), sort_keys=True) for _ in range(2))
    assert a == b


def test_export_all_is_byte_identical(tmp_path):
    st = State(DEMO)
    for n in ("one", "two"): dg.export_all(st, tmp_path / n)
    one = sorted((tmp_path / "one").rglob("*.pdf"))
    assert one
    for p in one:
        q = tmp_path / "two" / p.relative_to(tmp_path / "one")
        assert p.read_bytes() == q.read_bytes(), p.name
    day = meta(st.cfg)["date"].replace("-", "")
    assert f"D:{day}000000Z".encode() in one[0].read_bytes()
    assert meta(st.cfg)["revision"]
