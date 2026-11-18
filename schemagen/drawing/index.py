"""Where a flag leads: the drawing and the sheet of its far end (docs/drawing-model.md, Flags). A drawing does not know how the others are paginated,
so `export_all` draws every drawing twice: the first time with a placeholder sheet number (the layout measures every flag as if it said `sheet 44`, so
the second time, with the real numbers, lays out the same), `index_of` reads where each conductor ended up, and `annotate` writes the far end's drawing
and sheet into the scene's flags (and into the conductors a summary flag stands for)."""
from __future__ import annotations

from typing import Any, Callable

Where = Callable[[str, str], list[int]]   # (drawing id, conductor id) -> the sheets of that drawing that show the conductor
GUESS = 44                                # the sheet number of the first pass: the widest two digits


def guess(drawing: str, cid: str) -> list[int]:
    return [GUESS]


def suffix(drawing: str, sheets: list[int]) -> str:
    """` (drawing VCU, sheet 3)`, a range for several sheets (`sheet 2-5`), or just the drawing when the sheet is not known."""
    if not drawing: return ""
    return f" (drawing {drawing}" + (f", sheet {min(sheets)}" + (f"-{max(sheets)}" if max(sheets) != min(sheets) else "") if sheets else "") + ")"


def annotate(sc: dict[str, Any], where: Where) -> None:
    """Appends the suffix to the text of every flag of the scene (in place). A summary flag points at the drawing of the bus it speaks of, with the
    sheets that show its conductors; every conductor it covers keeps its own far end's drawing."""
    for f in sc["flags"]:
        cid = f["model"].removeprefix("conductor:")
        if f.get("covers"):
            for c in f["covers"]: c["text"] += suffix(c.get("drawing", ""), where(c.get("drawing", ""), c["id"]))
            f["text"] += suffix(f.get("drawing", ""), sorted({n for c in f["covers"] for n in where(f.get("drawing", ""), c["id"])}))
        else: f["text"] += suffix(f.get("drawing", ""), where(f.get("drawing", ""), cid))


def index_of(geometry: Any) -> dict[tuple[str, str], list[int]]:
    """(drawing id, conductor id) -> the sheets of this drawing that draw the conductor."""
    d = geometry["drawing"]["scope"].partition(":")[2]
    out: dict[tuple[str, str], list[int]] = {}
    for sh in geometry["sheets"]:
        for w in sh["wires"]:
            n = out.setdefault((d, w["model"].removeprefix("conductor:")), [])
            if sh["n"] not in n: n.append(sh["n"])
    return out
