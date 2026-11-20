"""Does each produced drawing PDF say exactly what the wire list says? `schemagen check-drawings <project> <pdf folder>`.

    from schemagen.verify import check_drawings
    report = check_drawings(project, pdf_dir, source=None, only=None, book=True)   # -> dict (JSON-ready), see check_drawings

Reads the project through schemagen.core and the PDFs with pdfplumber; imports nothing of the drawing engine, the renderers or the app (tests/test_verify.py
enforces that), so the engine and the verifier cannot share a bug."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import expect as X
from .check import Drawing, check_drawing, summary  # noqa: F401
from .overview import check_overview
from .toc import check_toc
from .pdfread import read

HARD = ("missing", "extra", "ends", "gauge", "colour", "label", "net", "table", "junction", "book", "toc", "unread", "flag", "title")   # the PDF disagrees with the wire list
SOFT_FLAG = ("flag_no_target", "flag_no_drawing", "flag_no_sheet")
LEGIBILITY = ("text_truncated", "text_overlaps_text", "text_on_line", "text_outside_frame", "text_too_small", "graphics_in_furniture", "graphics_outside_frame")
FILES = "*.pdf"
OVERVIEW = "overview.pdf"       # the three-page overview (power distribution, CAN network, all wires): checked by verify/overview.py


def pdfs(pdf_dir: Path) -> tuple[list[Path], Path | None]:
    """The per-drawing PDFs of a folder (`<dir>/drawings/*.pdf`, else `<dir>/*.pdf`) and the book (`wiring-diagrams.pdf`) if there is one."""
    d = pdf_dir / "drawings" if (pdf_dir / "drawings").is_dir() else pdf_dir
    book = next((p for p in (pdf_dir / "wiring-diagrams.pdf", d / "wiring-diagrams.pdf") if p.exists()), None)
    return sorted(p for p in d.glob(FILES) if p != book and "wiring-diagrams" not in p.name and p.name != OVERVIEW), book


def check_pdf(path: str | Path, project: Any, source: dict[str, str] | None = None) -> Drawing:
    """One drawing PDF against the project (a path, or an `expect.Expected`); returns the Drawing with its `findings` (list of dicts: kind, drawing, sheet, msg)."""
    ex = project if isinstance(project, X.Expected) else X.read(project)
    d = Drawing(Path(path), ex)
    check_drawing(d, source or ex.source)
    return d


def _sig(sheet: Any) -> str: return hashlib.sha1("\n".join(sorted(f"{r.s}@{r.x0:.0f},{r.top:.0f}" for r in sheet.runs)).encode()).hexdigest()


def check_drawings(project: str | Path, pdf_dir: str | Path, source: str | Path | None = None, only: list[str] | None = None, book: bool = True) -> dict[str, Any]:
    """Checks every drawing PDF in `pdf_dir` against the wire list of `project`.

    source: the spreadsheet the title block hash is checked against (default: the project's own source file or wirelist folder). only: PDF stems to check.
    Returns {"project", "pdf_dir", "source": {name, sha256}, "ok": bool, "totals": {...}, "drawings": {stem: {scope, sheets, wires, crossings, per_sheet, by_kind}},
    "findings": [{kind, drawing, sheet, msg, ...}]}. Finding kinds: missing extra ends gauge colour label net table junction (the PDF differs from the wire list),
    book (completeness), flag (a flag leads nowhere), flag_no_target flag_no_drawing flag_no_sheet (a flag does not say where it goes), title (wrong),
    title_revision_missing title_date_missing title_hash_missing, and the legibility kinds text_overlaps_text text_on_line text_outside_frame text_too_small
    graphics_in_furniture. `ok` is true when no finding of the first group (HARD) exists."""
    ex = X.read(project)
    src = X.source_digest_of(Path(source)) if source else ex.source
    files, bookpdf = pdfs(Path(pdf_dir))
    if only: files = [p for p in files if p.stem in only]
    ds: dict[str, Drawing] = {}
    for p in files:
        try: ds[p.stem] = Drawing(p, ex)
        except Exception as e:  # noqa: BLE001  (a PDF the reader cannot read is a finding, not a crash)
            bad = Drawing.__new__(Drawing); bad.name, bad.findings, bad.sheets, bad.recs, bad.table_labels = p.stem, [dict(kind="unread", drawing=p.stem, sheet=None, msg=f"cannot read: {e}")], [], {}, set()
            bad.scope = ""; bad.path = p; ds[p.stem] = bad
    for d in ds.values():
        if d.sheets: check_drawing(d, src, ds)
    findings = [f for d in ds.values() for f in d.findings]
    ov = next((p for p in (Path(pdf_dir) / OVERVIEW, Path(pdf_dir) / "drawings" / OVERVIEW) if p.exists()), None)
    if ds or ov is None: findings += _book(ex, ds, bookpdf if book else None)      # a folder with only the overview has no drawings to complete
    if book and bookpdf is not None and ds: findings += check_toc(ex, ds, read(bookpdf))
    if ov is not None and not only:
        pages, more = check_overview(ex, ov, src)
        ds.update({d.name: d for d in pages})
        findings += more
    return _report(project, pdf_dir, ex, src, ds, findings)


def _book(ex: X.Expected, ds: dict[str, Drawing], bookpdf: Path | None) -> list[dict[str, Any]]:
    """Completeness: every source wire is in the drawings of both of its end components, and every drawing page is in the book."""
    out: list[dict[str, Any]] = []
    drawn: dict[str, set[str]] = {d.scope.removeprefix("component:"): set(d.recs) | d.table_labels for d in ds.values() if d.scope.startswith("component:")}
    everything = set().union(*drawn.values()) if drawn else set()
    for c in ex.conds:
        if c.label not in everything: out.append(dict(kind="book", drawing="", sheet=None, msg=f"wire {c.label} is in no drawing", conductor=c.id)); continue
        for t in (c.a, c.b):
            comp = t[0]
            if ex.kind.get(comp) == "splice": continue
            if comp not in drawn: out.append(dict(kind="book", drawing="", sheet=None, msg=f"wire {c.label}: no drawing of {comp}", conductor=c.id))
            elif c.label not in drawn[comp]: out.append(dict(kind="book", drawing=f"component-{comp}", sheet=None, msg=f"wire {c.label} is not in the drawing of {comp}", conductor=c.id))
    if bookpdf is not None and ds:
        have = Counter(_sig(s) for s in read(bookpdf))
        for d in ds.values():
            for s in d.pages:
                k = _sig(s)
                if have[k] <= 0: out.append(dict(kind="book", drawing=d.name, sheet=s.n, msg=f"sheet {s.n} of {d.name} is not in the book"))
                else: have[k] -= 1
    return out


def _report(project: Any, pdf_dir: Any, ex: X.Expected, src: dict[str, str], ds: dict[str, Drawing], findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_d: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in findings: by_d[f["drawing"]].append(f)
    per: dict[str, Any] = {}
    for n, d in ds.items():
        fs = by_d.get(n, [])
        per[n] = dict(scope=d.scope, sheets=len(d.sheets), wires=sum(len(s.wires) for s in d.sheets), crossings=sum(s.crossings for s in d.sheets), by_kind=dict(Counter(f["kind"] for f in fs)),
                      per_sheet=[dict(n=s.n, wires=len(s.wires), flags=len(s.flags), table_rows=len(s.rows), crossings=s.crossings,
                                      by_kind=dict(Counter(f["kind"] for f in fs if f["sheet"] == s.n))) for s in d.sheets],
                      table_only=getattr(d, "table_only", 0))
    kinds = Counter(f["kind"] for f in findings)
    hard = sum(v for k, v in kinds.items() if k in HARD)
    checks = sum(len(d.ex.scope(d.scope) or ()) for d in ds.values() if d.sheets)
    t = dict(drawings=len(ds), sheets=sum(len(d.sheets) for d in ds.values()), wire_pieces=sum(p["wires"] for p in per.values()), conductors=len(ex.conds), conductor_checks=checks,
             connectivity=hard, flags=sum(v for k, v in kinds.items() if k in SOFT_FLAG or k == "flag"), title=sum(v for k, v in kinds.items() if k.startswith("title")),
             crossings=sum(p["crossings"] for p in per.values()), by_kind=dict(kinds), legibility={k: kinds[k] for k in LEGIBILITY if kinds[k]})
    return dict(project=str(project), pdf_dir=str(pdf_dir), source=src, ok=hard == 0, totals=t, drawings=per, findings=findings)


def main(project: str, pdf_dir: str, output: str | None = None, source: str | None = None, quiet: bool = False) -> int:
    """The CLI: writes the JSON report (default `<pdf_dir>/check-drawings.json`), prints the summary; exit 0 when no HARD finding."""
    rep = check_drawings(project, pdf_dir, source)
    out = Path(output) if output else Path(pdf_dir) / "check-drawings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    if not quiet: print(summary(rep) + f"\nreport: {out}")
    return 0 if rep["ok"] else 1
