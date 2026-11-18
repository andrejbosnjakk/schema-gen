"""Speed guard: an ordinary component's drawing (layout, routing, PDF) on the fictional large project stays far from the minutes it once took.
The bounds are about ten times what an idle laptop needs, so only a real regression (a quadratic scan, a cache lost) trips them; the figures
to compare live in benchmarks/drawings.py."""
import subprocess
import sys
import time
from pathlib import Path

import pytest

from schemagen.app.server import State
from schemagen.drawing.engine import draw, export, meta

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def st(tmp_path_factory):
    d = tmp_path_factory.mktemp("speed") / "p"
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_large_fixture.py"), str(d), "--light"], check=True)
    return State(d)


def test_ordinary_components_draw_fast(st, tmp_path):
    ids = ["EC1", "S101", "S212", "S424", "CB-C3", "SP-05"]
    assert all(any(c.id == i for c in st.m.components) for i in ids)
    for i in ids:
        best = 1e9
        for _ in range(2):  # the faster of two runs: another process on the machine only adds time
            t = time.perf_counter()
            export(draw(st, f"component:{i}", "A3", meta(st.cfg)), tmp_path / "x.pdf")
            best = min(best, time.perf_counter() - t)
        assert best < 3.0, f"{i}: {best:.1f} s"
