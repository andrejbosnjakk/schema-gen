"""The entry point of the drawing engine: `draw(st, scope, size, meta)` turns a scope into finished geometry (scene -> layout -> routing
-> sheet furniture) and `export(geometry, path)` writes it as SVG (one file per sheet when there are several) or PDF."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import layout as L
from . import symbols as S
from . import table as T
from .geometry import SHEETS, Geometry
from .scope import scene
from .style import areas


def draw(st: Any, scope: Any, size: str = "A3", meta: dict[str, str] | None = None) -> Geometry:
    """The drawing of `scope` ("component:VCU", ...) on A3 or A4 landscape sheets. meta: revision, date, drawn_by, source (never the wall clock)."""
    sc = scene(st, scope)
    meta = dict(meta or {})
    pages = L.paginate(sc, size)  # type: ignore[arg-type]
    info: dict[str, str] = dict(title=sc["title"], scope=sc["scope"]["text"], project=sc["project"], revision=meta.get("revision", ""), date=meta.get("date", ""),
                drawn_by=meta.get("drawn_by", ""), source=meta.get("source", ""))
    ah = areas(size)["area"][3]
    placed: list[tuple[Any, Any, list[Any], bool]] = []     # (page, its layout, its table rows, whether the table fits under the drawing)
    for pg in pages:
        rs = T.rows(pg)
        th = T.height(len(rs))
        sh = L.place(pg, size, None, 1, th)      # the natural height `h` does not depend on the room kept for the table: one layout when the table fits
        fits = sh["h"] + th <= ah
        placed.append((pg, sh if fits else L.place(pg, size, None, 1, 0.0), rs, fits))
    tabs = T.pages([(n, rs) for n, (_, _, rs, fits) in enumerate(placed, 1) if not fits and rs], size)
    of = len(pages) + len(tabs)
    on = {n: len(pages) + 1 + next(k for k, t in enumerate(tabs) if n in t[2]) for n, (_, _, rs, fits) in enumerate(placed, 1) if not fits and rs}
    sheets: list[Any] = []
    for n, (pg, sh, rs, fits) in enumerate(placed, 1):
        kinds = list(dict.fromkeys([s["kind"] for s in sh["symbols"]] + (["spare"] if any(p["spare"] for it in pg["items"] for b in it["blocks"] for p in b["pins"]) else [])  # noqa: E501
                                   + [f["kind"] for f in sh["flags"]]))
        rules, texts = T.inline(rs, size) if fits and rs else ([], [])
        sheet: dict[str, Any] = dict(n=n, of=of, size=size, w_mm=SHEETS[size][0], h_mm=SHEETS[size][1], grid_mm=5.0, symbols=sh["symbols"], wires=sh["wires"],  # noqa: E501
                                     texts=sh["texts"] + texts, flags=sh["flags"], rules=rules, table=dict(sheet=n if fits else on.get(n), rows=T.row_data(rs)))
        where = "under the drawing" if fits else f"on sheet {on[n]}" if n in on else ""
        sheet.update(S.furniture(info, size, n, of, kinds, L.notes(pg, sh, where)))
        sheets.append(sheet)
    for k, (rules, texts, shown) in enumerate(tabs):
        n = len(pages) + 1 + k
        sheet = dict(n=n, of=of, size=size, w_mm=SHEETS[size][0], h_mm=SHEETS[size][1], grid_mm=5.0, symbols=[], wires=[], texts=texts, flags=[], rules=rules,
                     table=dict(sheet=n, rows=[]))
        sheet.update(S.furniture(info, size, n, of, [], ["Wire table of sheet " + ", ".join(map(str, shown)) + "."]))
        sheets.append(sheet)
    return dict(version=1, drawing=info, sheets=sheets)  # type: ignore[return-value,typeddict-item]


def stem(scope: str) -> str:
    """The file name (without extension) of the drawing of `scope`: `component:ECU` -> `component-ECU`."""
    return scope.replace(":", "-").replace("~", "_").replace(",", "+")


def meta(source: Any) -> dict[str, str]:
    """The title block data every drawing of the CLI and the app carries (today's date, drawn by schemagen). `source` is the project's Config: the title block
    then names the wire list's source file with the start of its sha256 (`#1a2b3c4d name.xlsx`); a plain string is shown as given."""
    import datetime
    if not isinstance(source, str):
        from ..core.load import source_digest
        name, sha = source_digest(source)
        source = f"#{sha[:8]} {name}"
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
