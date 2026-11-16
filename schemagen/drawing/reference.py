"""The six reference drawings of docs/screens/drawings/ (fictional projects only), also the golden files of tests/test_drawing_reference.py.
`python -m schemagen.drawing.reference [outdir]` writes name.pdf and name.svg (name-1.svg, ... for several sheets)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .engine import draw
from .geometry import Geometry
from .render_pdf import pdf
from .render_svg import svg

ROOT = Path(__file__).resolve().parents[2]
META = dict(revision="A", date="2026-11-16", drawn_by="schemagen")
CASES = {  # name: (project folder, scope)
    "01-contactor-circuit": ("examples/aircraft", "component:K-BATTERY-CONTACTOR"),     # fuse, switch, relay coil and contacts, battery, load
    "02-harness-25-pin": ("tests/data/drawing_fixture", "harness:X-25"),                  # both halves of a 25-pin connector
    "03-controller-40-pin": ("tests/data/drawing_fixture", "component:FCU"),             # 40 pins, spares grey, two sheets
    "04-can-bus": ("examples/aircraft", "connection:BATTERY-MANAGEMENT-SYSTEM~MOTOR-CONTROLLER"),   # splices and terminators
    "05-can-pair": ("examples/aircraft", "connection:EFIS~MOTOR-CONTROLLER"),            # a twisted pair in practice; the data has no pair or shield
    "06-multi-sheet": ("examples/aircraft", "component:EFIS"),                           # continuation flags, summary flag
}


def build(name: str) -> Geometry:
    from ..app.server import State
    folder, scope = CASES[name]
    return draw(State(ROOT / folder), scope, "A3", dict(META, source=Path(folder).name))


def svgs(name: str, g: Geometry) -> dict[str, str]:
    """File name -> SVG text of every sheet."""
    n = len(g["sheets"])
    return {(f"{name}.svg" if n == 1 else f"{name}-{i + 1}.svg"): svg(g, i, embed_font=True) for i in range(n)}


def main(argv: list[str]) -> int:
    out = Path(argv[0] if argv else ROOT / "docs" / "screens" / "drawings")
    out.mkdir(parents=True, exist_ok=True)
    for name in CASES:
        g: Any = build(name)
        for f, t in svgs(name, g).items(): (out / f).write_text(t, encoding="utf8", newline="\n")
        pdf(g, out / f"{name}.pdf")
        print(name, len(g["sheets"]), "sheet(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
