"""Run the WireViz command (GPL-3.0: a separate program, never imported) on many YAML files, in parallel batches.

Graphviz `dot` is found first (PATH, SCHEMAGEN_DOT, the usual install folders) and its folder is put on WireViz's PATH,
so an installed Graphviz that is not on PATH still works and a missing one is one plain error, not a traceback.
WireViz writes `<name>.tmp` (the Graphviz source) and `<name>.tmp.svg` next to each drawing; both are removed
whether the render worked or not.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

GRAPHVIZ_MISSING = "Graphviz is not installed, so harness drawings cannot be made. The diagram and simulation still work."


class RenderError(Exception):
    """A drawing could not be made: `code` is graphviz-missing or render-failed, `detail` the full stderr (for the log)."""

    def __init__(self, code: str, message: str, detail: str = ""):
        super().__init__(message)
        self.code, self.message, self.detail = code, message, detail


def _candidates() -> list[Path]:
    exe = "dot.exe" if os.name == "nt" else "dot"
    out = []
    if os.environ.get("SCHEMAGEN_DOT"):
        p = Path(os.environ["SCHEMAGEN_DOT"]); out.append(p / exe if p.is_dir() else p)
    if getattr(sys, "_MEIPASS", None): out.append(Path(sys._MEIPASS) / "graphviz" / exe)  # the desktop build
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if os.environ.get(env):
            out += [Path(os.environ[env]) / "Graphviz" / "bin" / exe, Path(os.environ[env]) / "Programs" / "Graphviz" / "bin" / exe]
    out += [Path("/opt/homebrew/bin/dot"), Path("/usr/local/bin/dot"), Path("/usr/bin/dot")]
    return out


def find_dot() -> str | None:
    """Path of Graphviz `dot`, or None."""
    w = shutil.which("dot")
    if w: return w
    return next((str(p) for p in _candidates() if p.is_file()), None)


def graphviz() -> dict[str, Any]:
    """{found, version, message} for /api/health and the CLI."""
    dot = find_dot()
    if not dot: return dict(found=False, version="", message=GRAPHVIZ_MISSING)
    try:
        r = subprocess.run([dot, "-V"], capture_output=True, text=True, timeout=10)
        v = (r.stderr or r.stdout).strip()
        ver = v.split("version", 1)[1].split()[0] if "version" in v else v
    except (OSError, subprocess.SubprocessError) as e:
        return dict(found=False, version="", message=f"Graphviz was found at {dot} but does not run ({e}).")
    return dict(found=True, version=ver, message="")


def wireviz_cmd() -> list[str] | None:
    """The WireViz command: on PATH, else next to this Python (a venv's Scripts folder that is not on PATH)."""
    w = shutil.which("wireviz")
    if w: return [w]
    d = Path(sys.executable).parent
    for p in (d / "wireviz.exe", d / "wireviz", d / "Scripts" / "wireviz.exe"):
        if p.is_file(): return [str(p)]
    return None


def _clean(ymls: list[Path], out: Path) -> None:
    for y in ymls:
        for suf in (".tmp", ".tmp.svg"):
            try: (out / f"{y.stem}{suf}").unlink(missing_ok=True)
            except OSError: pass


def _reason(text: str) -> str:
    """The last meaningful line of WireViz's stderr (the exception, not the traceback)."""
    lines = [x.strip() for x in text.strip().splitlines() if x.strip()]
    return lines[-1][:300] if lines else "no message"


def render_many(ymls: list[Path], out: Path, fmt: str = "hpst", jobs: int | None = None) -> None:
    """Render every YAML into out/ (output name = file stem). Raises RenderError with a plain message on failure."""
    if not ymls: return
    dot = find_dot()
    if not dot: raise RenderError("graphviz-missing", GRAPHVIZ_MISSING)
    cmd = wireviz_cmd()
    if not cmd: raise RenderError("render-failed", "The WireViz command is not installed (pip install wireviz==0.4.1), so drawings cannot be made.")
    env = dict(os.environ, PATH=str(Path(dot).parent) + os.pathsep + os.environ.get("PATH", ""), PYTHONIOENCODING="utf-8")
    jobs = max(1, min(jobs or os.cpu_count() or 1, len(ymls)))
    chunks = [ymls[i::jobs] for i in range(jobs)]
    try:
        procs = [(c, subprocess.Popen([*cmd, "-f", fmt, "-o", str(out), *map(str, c)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, encoding="utf-8", errors="replace", env=env)) for c in chunks]
        bad = []
        for c, p in procs:
            so, se = p.communicate()
            if p.returncode: bad.append((c, se or so))
    finally:
        _clean(ymls, out)
    if bad:
        c, text = bad[0]
        if "ExecutableNotFound" in text or "failed to execute" in text: raise RenderError("graphviz-missing", GRAPHVIZ_MISSING, text)
        raise RenderError("render-failed", f"WireViz could not draw {', '.join(x.stem for x in c)}: {_reason(text)}",
                          "\n\n".join(t for _, t in bad))
