"""The six reference drawings (docs/screens/drawings/) are golden files: the engine must reproduce every SVG byte for byte.
Regenerate with `python -m schemagen.drawing.reference` or UPDATE_GOLDEN=1 (and list the reason in docs/golden-changes.md)."""
import os

import pytest

from schemagen.drawing import checks
from schemagen.drawing.geometry import validate
from schemagen.drawing.reference import CASES, ROOT, build, svgs

GOLD = ROOT / "docs" / "screens" / "drawings"


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_drawing(name):
    g = build(name)
    assert validate(g) == [] and checks.report(g)["ok"]
    for f, text in svgs(name, g).items():
        if os.environ.get("UPDATE_GOLDEN"): (GOLD / f).write_text(text, encoding="utf8", newline="\n")
        assert (GOLD / f).read_text(encoding="utf8") == text, f
