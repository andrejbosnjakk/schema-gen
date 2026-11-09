"""Drawings: a missing Graphviz is one plain error, WireViz's real error is surfaced, no .tmp files are left behind."""
import shutil
import sys
from pathlib import Path

import pytest

from schemagen.cli import main
from schemagen.renderers import wireviz as wv

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


@pytest.fixture
def demo(tmp_path):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("out"))
    return d


def test_missing_graphviz_is_plain(demo, monkeypatch, capsys):
    monkeypatch.setattr(wv, "find_dot", lambda: None)
    assert wv.graphviz() == dict(found=False, version="", message=wv.GRAPHVIZ_MISSING)
    with pytest.raises(wv.RenderError) as e: wv.render_many([demo / "x.yml"], demo)
    assert e.value.code == "graphviz-missing"
    assert main(["draw", str(demo)]) == 1
    err = capsys.readouterr().err
    assert "Graphviz is not installed" in err and "Traceback" not in err
    assert not list((demo / "out").glob("*.tmp*"))


def test_wireviz_failure_surfaces_stderr_and_cleans_tmp(tmp_path, monkeypatch):
    fake = tmp_path / "fake_wireviz.py"  # writes WireViz's temp files, then fails like WireViz does
    fake.write_text("import sys, pathlib\nout = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
                    "for y in sys.argv[sys.argv.index('-o') + 2:]:\n    (out / (pathlib.Path(y).stem + '.tmp')).write_text('graph')\n"
                    "sys.stderr.write('Traceback (most recent call last):\\n  File x\\nValueError: Unknown color: PK2\\n'); sys.exit(1)\n",
                    encoding="utf-8")
    monkeypatch.setattr(wv, "find_dot", lambda: sys.executable)
    monkeypatch.setattr(wv, "wireviz_cmd", lambda: [sys.executable, str(fake)])
    y = tmp_path / "X-BH.yml"; y.write_text("connectors: {}\n", encoding="utf-8")
    with pytest.raises(wv.RenderError) as e: wv.render_many([y], tmp_path)
    assert e.value.code == "render-failed" and "Unknown color: PK2" in e.value.message and "X-BH" in e.value.message
    assert "Traceback" in e.value.detail and not list(tmp_path.glob("*.tmp*"))


def test_graphviz_missing_when_wireviz_cannot_run_dot(tmp_path, monkeypatch):
    fake = tmp_path / "fake_wireviz.py"
    fake.write_text("import sys\nsys.stderr.write(\"graphviz.backend.execute.ExecutableNotFound: failed to execute WindowsPath('dot')\\n\")\n"
                    "sys.exit(1)\n", encoding="utf-8")
    monkeypatch.setattr(wv, "find_dot", lambda: sys.executable)
    monkeypatch.setattr(wv, "wireviz_cmd", lambda: [sys.executable, str(fake)])
    with pytest.raises(wv.RenderError) as e: wv.render_many([tmp_path / "a.yml"], tmp_path)
    assert e.value.code == "graphviz-missing"
