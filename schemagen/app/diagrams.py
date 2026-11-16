"""The app's wiring diagrams, drawn by schemagen's own engine (docs/drawing-model.md): one scope as SVG sheets, one scope as a PDF, the whole set
(a PDF per component plus one book with the symbol sheet first)."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from ..drawing.engine import draw, export, meta, stem
from ..drawing.render_pdf import pdf
from ..drawing.render_svg import svg
from ..drawing.sheet import symbol_sheet
from . import userdata
from .errors import AppError
from .workspace import _natural


def geometry(st: Any, scope: str) -> Any:
    """The A3 drawing of `scope`; a scope the engine does not know becomes a plain message."""
    try: return draw(st, scope, "A3", meta(st.cfg.root.name))
    except ValueError as e: raise AppError("bad-request", f"{str(e).rstrip('.').capitalize()}.") from None


def sheets(st: Any, scope: str) -> dict[str, Any]:
    """`{title, scope, sheets: [svg, ...]}` for the viewer."""
    g = geometry(st, scope)
    return dict(title=g["drawing"]["title"], scope=g["drawing"]["scope"], sheets=[svg(g, i) for i in range(len(g["sheets"]))])


def export_one(st: Any, scope: str, out: Path) -> list[str]:
    """Writes `scope` as `<out>/drawings/<name>.pdf`; returns the file's path relative to `out`."""
    g = geometry(st, scope)
    (out / "drawings").mkdir(parents=True, exist_ok=True)
    export(g, out / "drawings" / f"{stem(g['drawing']['scope'])}.pdf")
    return [f"drawings/{stem(g['drawing']['scope'])}.pdf"]


def export_all(st: Any, out: Path) -> tuple[list[str], list[str]]:
    """A PDF per component and harness connector that has wires (`<out>/drawings/`) and `<out>/wiring-diagrams.pdf`, all of them with the symbol
    sheet first. Rendered aside and moved on success: a failure leaves nothing in `out`. A drawing that cannot be drawn is logged and left out; returns
    (files, ids of the components that failed). Only when none could be drawn is it an error."""
    stage = Path(tempfile.mkdtemp(prefix="schemagen-drawings-"))
    try:
        (stage / "drawings").mkdir()
        gs, failed = [], []
        for c in sorted(st.m.components, key=lambda c: _natural(c.id)):
            if c.kind == "splice": continue  # a splice is drawn inside the runs that pass through it
            try:
                g = draw(st, f"component:{c.id}", "A3", meta(st.cfg.root.name))
                if not any(sh["wires"] or sh["flags"] for sh in g["sheets"]): continue
                export(g, stage / "drawings" / f"{stem(g['drawing']['scope'])}.pdf")
            except Exception:
                userdata.log().exception("wiring diagram of %s could not be drawn", c.id)
                failed.append(c.id)
                continue
            gs.append(g)
        if not gs: raise AppError("bad-request", "No component has wires to draw." if not failed else f"None of the {len(failed)} wiring diagrams could be drawn.")
        pdf([symbol_sheet(), *gs], stage / "wiring-diagrams.pdf")
        files = sorted(str(p.relative_to(stage)).replace("\\", "/") for p in stage.rglob("*") if p.is_file())
        for f in files:
            (out / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(stage / f), str(out / f))
        return files, failed
    finally: shutil.rmtree(stage, ignore_errors=True)
