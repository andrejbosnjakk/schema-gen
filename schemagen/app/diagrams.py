"""The app's wiring diagrams, drawn by schemagen's own engine (docs/drawing-model.md): one scope as SVG sheets, one scope as a PDF, the whole set
(a PDF per component plus one book with the symbol sheet first)."""
from __future__ import annotations

import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from ..drawing.engine import draw, export, meta, stem
from ..drawing.render_pdf import Book
from ..drawing.render_svg import svg
from ..drawing.scope import members, parse
from ..drawing.sheet import symbol_sheet
from . import userdata
from .errors import AppError
from .workspace import _natural

VIEW_MAX = 25  # components in one viewer scope


def geometry(st: Any, scope: str) -> Any:
    """The A3 drawing of `scope`; a scope the engine does not know becomes a plain message."""
    try: return draw(st, scope, "A3", meta(st.cfg))
    except ValueError as e: raise AppError("bad-request", f"{str(e).rstrip('.').capitalize()}.") from None


def sheets(st: Any, scope: str) -> dict[str, Any]:
    """`{title, scope, sheets: [svg, ...]}` for the viewer. A scope of more than VIEW_MAX components is not drawn here (it runs minutes inside one
    request, and every sheet's SVG would be held at once): it is saved as PDF, which is a background job."""
    try: n = len(members(st, parse(scope))[0])
    except ValueError as e: raise AppError("bad-request", f"{str(e).rstrip('.').capitalize()}.") from None
    if n > VIEW_MAX: raise AppError("bad-request", f"That is {n} components, too many to show at once. Save it as PDF: the export runs in the background.")
    g = geometry(st, scope)
    return dict(title=g["drawing"]["title"], scope=g["drawing"]["scope"], sheets=[svg(g, i) for i in range(len(g["sheets"]))])


def export_one(st: Any, scope: str, out: Path) -> list[str]:
    """Writes `scope` as `<out>/drawings/<name>.pdf`; returns the file's path relative to `out`."""
    g = geometry(st, scope)
    (out / "drawings").mkdir(parents=True, exist_ok=True)
    export(g, out / "drawings" / f"{stem(g['drawing']['scope'])}.pdf")
    return [f"drawings/{stem(g['drawing']['scope'])}.pdf"]


class Cancelled(BaseException):
    """Raised inside an export job's thread to stop it (not an Exception: a drawing's `except Exception` must not swallow it)."""


def export_all(st: Any, out: Path, progress: Callable[[int, int, str], None] = lambda n, N, cur: None) -> tuple[list[str], list[str]]:
    """A PDF per component and harness connector that has wires (`<out>/drawings/`) and `<out>/wiring-diagrams.pdf`, all of them with the symbol
    sheet first. Each drawing is written to disk and added to the book as soon as it is drawn, then dropped: memory stays at one drawing.
    Rendered aside and moved on success: a failure or a cancel leaves nothing in `out`. A drawing that cannot be drawn is logged and left out; returns
    (files, ids of the components that failed). Only when none could be drawn is it an error. progress(n, N, id) is called before each drawing."""
    stage = Path(tempfile.mkdtemp(prefix="schemagen-drawings-"))
    try:
        (stage / "drawings").mkdir()
        cs = [c for c in sorted(st.m.components, key=lambda c: _natural(c.id)) if c.kind != "splice"]  # a splice is drawn inside the runs through it
        book = Book(stage / "wiring-diagrams.pdf", symbol_sheet()["drawing"].get("title", ""))
        book.add(symbol_sheet())
        done, failed = 0, []
        for n, c in enumerate(cs):
            g = None  # the previous drawing is dropped before the next one is built
            progress(n, len(cs), c.id)
            try:
                g = draw(st, f"component:{c.id}", "A3", meta(st.cfg))
                if not any(sh["wires"] or sh["flags"] for sh in g["sheets"]): continue
                export(g, stage / "drawings" / f"{stem(g['drawing']['scope'])}.pdf")
                book.add(g)
                done += 1
            except Exception:
                userdata.log().exception("wiring diagram of %s could not be drawn", c.id)
                failed.append(c.id)
        progress(len(cs), len(cs), "")
        if not done: raise AppError("bad-request", "No component has wires to draw." if not failed else f"None of the {len(failed)} wiring diagrams could be drawn.")
        book.close()
        files = sorted(str(p.relative_to(stage)).replace("\\", "/") for p in stage.rglob("*") if p.is_file())
        for f in files:
            (out / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(stage / f), str(out / f))
        return files, failed
    finally: shutil.rmtree(stage, ignore_errors=True)


class Job:
    """One export running in its own thread, so the request that starts it answers at once and the app stays usable. `status()` is what GET shows
    (n of N drawings done, the one being drawn, state running|done|failed|cancelled, the ids that failed); `cancel()` stops the thread within
    a moment, wherever it is (the engine is not asked to cooperate), and the staging folder is removed by the export's own `finally`."""

    def __init__(self, work: Callable[[Job], tuple[list[str], list[str]]], folder: Path):
        self.id, self.folder, self.state = uuid.uuid4().hex[:8], folder, "running"
        self.n, self.N, self.current, self.error = 0, 0, "", ""
        self.files: list[str] = []
        self.failed: list[str] = []
        self.stop = False
        self.thread = threading.Thread(target=self._run, args=(work,), daemon=True)
        self.thread.start()

    def progress(self, n: int, N: int, cur: str) -> None:
        if self.stop: raise Cancelled()
        self.n, self.N, self.current = n, N, cur

    def _run(self, work: Callable[[Job], tuple[list[str], list[str]]]) -> None:
        try: self.files, self.failed = work(self); self.state = "done"
        except Cancelled: self.state = "cancelled"
        except BaseException as e:  # noqa: BLE001  (the user gets a plain sentence, the log the cause)
            from .errors import convert
            self.error, self.state = convert(e, "export").message, "failed"
        finally: self.stop = True

    def cancel(self) -> None:
        if self.state != "running": return
        self.stop = True
        if self.thread.is_alive() and self.thread.ident:
            import ctypes
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(self.thread.ident), ctypes.py_object(Cancelled))

    def status(self) -> dict[str, Any]:
        return dict(job=self.id, state=self.state, n=self.n, N=self.N, current=self.current, failed=list(self.failed),
                    **(dict(folder=str(self.folder), files=self.files) if self.state == "done" else dict(error=self.error) if self.state == "failed" else {}))
