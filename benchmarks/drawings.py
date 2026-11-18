"""Time the drawing engine per component and the whole export job.

    python benchmarks/drawings.py                 # the fictional light large project (generated in a temp folder)
    python benchmarks/drawings.py <project dir>   # any project, e.g. a real one (read only; outputs go to a temp folder)
    python benchmarks/drawings.py --export 3      # export job wall time, best of 3 runs (default 1)

Prints n, p50, p95, max and the slowest components of draw + PDF per component, and the wall time of the export job (all drawings + the book)."""
from __future__ import annotations

import argparse, statistics, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def per_component(st, tmp: Path) -> list[tuple[str, float]]:
    """(component id, seconds to draw it and write its PDF) for every component the export job would draw; a drawing under half a second is timed
    twice and the faster run kept (other processes on the machine only ever add time)."""
    from schemagen.app.workspace import _natural
    from schemagen.drawing.engine import draw, export, meta
    out = []
    for c in sorted(st.m.components, key=lambda c: _natural(c.id)):
        if c.kind == "splice": continue
        best = 9e9
        for _ in range(2):
            t = time.perf_counter()
            g = draw(st, f"component:{c.id}", "A3", meta(st.cfg))
            if any(sh["wires"] or sh["flags"] for sh in g["sheets"]): export(g, tmp / "x.pdf")
            best = min(best, time.perf_counter() - t)
            if best > 0.5: break
        out.append((c.id, best))
    return out


def table(ts: list[tuple[str, float]]) -> str:
    v = sorted(t for _, t in ts)
    p95 = v[min(len(v) - 1, int(0.95 * len(v)))]
    worst = max(ts, key=lambda x: x[1])
    return f"n={len(v)}  p50={statistics.median(v) * 1e3:.0f} ms  p95={p95 * 1e3:.0f} ms  max={v[-1] * 1e3:.0f} ms  worst={worst[0]}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?", help="project folder or schemagen.yml (default: the fictional light large project)")
    ap.add_argument("--export", type=int, default=1, metavar="N", help="runs of the export job (0: skip)")
    a = ap.parse_args()
    from schemagen.app.diagrams import export_all
    from schemagen.app.server import State
    with tempfile.TemporaryDirectory(prefix="schemagen-bench-") as td:
        tmp = Path(td)
        proj = a.project
        if not proj:
            proj = tmp / "p"
            subprocess.run([sys.executable, str(ROOT / "tools" / "make_large_fixture.py"), str(proj), "--light"], check=True, stdout=subprocess.DEVNULL)
        t = time.perf_counter(); st = State(proj); print(f"load: {time.perf_counter() - t:.2f} s")
        ts = per_component(st, tmp)
        print("per component:", table(ts))
        print("slowest:", ", ".join(f"{k} {v * 1e3:.0f} ms" for k, v in sorted(ts, key=lambda x: -x[1])[:5]))
        runs = []
        for k in range(a.export):
            out = tmp / f"out{k}"; out.mkdir()
            t, c = time.perf_counter(), time.process_time(); export_all(st, out); runs.append((time.perf_counter() - t, time.process_time() - c))
        if runs: print("export job wall time (cpu):", ", ".join(f"{w:.1f} s ({c:.1f})" for w, c in runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
