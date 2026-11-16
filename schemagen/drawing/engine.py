"""The entry point of the drawing engine: `draw(st, scope, size, meta)` turns a scope into finished geometry (scene -> layout -> routing
-> sheet furniture) and `export(geometry, path)` writes it as SVG (one file per sheet when there are several) or PDF."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import layout as L
from . import symbols as S
from .geometry import SHEETS, Geometry
from .scope import scene


def draw(st: Any, scope: Any, size: str = "A3", meta: dict[str, str] | None = None) -> Geometry:
    """The drawing of `scope` ("component:VCU", ...) on A3 or A4 landscape sheets. meta: revision, date, drawn_by, source (never the wall clock)."""
    sc = scene(st, scope)
    meta = dict(meta or {})
    pages = L.paginate(sc, size)  # type: ignore[arg-type]
    info: dict[str, str] = dict(title=sc["title"], scope=sc["scope"]["text"], project=sc["project"], revision=meta.get("revision", ""), date=meta.get("date", ""),
                drawn_by=meta.get("drawn_by", ""), source=meta.get("source", ""))
    sheets: list[Any] = []
    for n, pg in enumerate(pages, 1):
        sh = L.place(pg, size)
        kinds = list(dict.fromkeys([s["kind"] for s in sh["symbols"]] + (["spare"] if any(p["spare"] for it in pg["items"] for b in it["blocks"] for p in b["pins"]) else [])  # noqa: E501
                                   + [f["kind"] for f in sh["flags"]]))
        sheet: dict[str, Any] = dict(n=n, of=len(pages), size=size, w_mm=SHEETS[size][0], h_mm=SHEETS[size][1], grid_mm=5.0, symbols=sh["symbols"], wires=sh["wires"],  # noqa: E501
                                     texts=sh["texts"], flags=sh["flags"])
        sheet.update(S.furniture(info, size, n, len(pages), kinds, L.notes(pg, sh)))
        sheets.append(sheet)
    return dict(version=1, drawing=info, sheets=sheets)  # type: ignore[return-value,typeddict-item]


def stem(scope: str) -> str:
    """The file name (without extension) of the drawing of `scope`: `component:ECU` -> `component-ECU`."""
    return scope.replace(":", "-").replace("~", "_").replace(",", "+")


def meta(source: str) -> dict[str, str]:
    """The title block data every drawing of the CLI and the app carries (today's date, drawn by schemagen, `source` the project's name)."""
    import datetime
    return dict(date=datetime.date.today().isoformat(), drawn_by="schemagen", source=source)


def export(geometry: Geometry, path: str | Path) -> list[Path]:
    """Writes the drawing: .pdf (one file, a page per sheet) or .svg (`name.svg`, or `name-1.svg`, `name-2.svg` ... for several sheets)."""
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        from .render_pdf import pdf
        pdf(geometry, p)
        return [p]
    if p.suffix.lower() != ".svg": raise ValueError(f"unknown drawing format {p.suffix!r}: use .svg or .pdf")
    from .render_svg import svg
    n = len(geometry["sheets"])
    out = [p if n == 1 else p.with_name(f"{p.stem}-{i}{p.suffix}") for i in range(1, n + 1)]
    for i, q in enumerate(out): q.write_text(svg(geometry, i, embed_font=True), encoding="utf8", newline="\n")
    return out
