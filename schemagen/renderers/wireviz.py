"""Run the WireViz command (GPL-3.0: a separate program, never imported) on many YAML files, in parallel batches."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def render_many(ymls: list[Path], out: Path, fmt: str = "hpst", jobs: int | None = None) -> None:
    """Render every YAML into out/ (output name = file stem). Raises SystemExit with WireViz's message on failure."""
    if not ymls: return
    exe = shutil.which("wireviz")
    if not exe: raise SystemExit("wireviz command not found: pip install wireviz==0.4.1 (and Graphviz), or use --no-render")
    jobs = max(1, min(jobs or os.cpu_count() or 1, len(ymls)))
    chunks = [ymls[i::jobs] for i in range(jobs)]
    procs = [(c, subprocess.Popen([exe, "-f", fmt, "-o", str(out), *map(str, c)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
             for c in chunks]
    for c, p in procs:
        so, se = p.communicate()
        if p.returncode: raise SystemExit(f"wireviz failed on {', '.join(x.name for x in c)}:\n{se or so}")
