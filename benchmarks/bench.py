"""Time the pipeline phases on the demo and on synthetic projects.

    python benchmarks/bench.py                       # demo, synthetic 1k and 5k
    python benchmarks/bench.py --sizes 1000 --render  # also run WireViz (slow on big projects)
    python benchmarks/bench.py --json results.json

Phases: load (rows -> project), net, checks (rules, or the 0.2 per-harness checks), draw (YAML without WireViz),
render (WireViz, only with --render), sim (operating point and fault sweep, when schemagen.sim exists).
Each phase is timed separately, best of --repeat runs.
"""
from __future__ import annotations

import argparse, contextlib, io, json, shutil, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemagen import __version__  # noqa: E402
from schemagen.config import load_config  # noqa: E402
from schemagen.net import Net  # noqa: E402
from schemagen.project import Project  # noqa: E402


def best(fn, repeat):
    out, ts = None, []
    for _ in range(repeat):
        t = time.perf_counter(); out = fn(); ts.append(time.perf_counter() - t)
    return out, min(ts)


def phases(proj: Path, repeat: int, render: bool, sim: bool) -> dict:
    from schemagen.cards import Cards
    from schemagen.cli import draw
    from schemagen.drawing import build
    cfg = load_config(proj)
    res: dict = {}
    pr, res["load"] = best(lambda: Project(cfg), repeat)
    net, res["net"] = best(lambda: Net(pr), repeat)
    res["wires"] = len(pr.wires)
    try:  # 0.3+: rules engine
        from schemagen.core.rules import run_rules
        issues, res["checks"] = best(lambda: run_rules(pr.model, pr.cfg), repeat)
        res["findings"] = len(issues)
    except ImportError:
        cards = Cards(cfg.cards, cfg.cardmap)
        hs = list(pr.dsp.HARNESS)
        def checks():
            return sum(len(build(pr, net, cards, h).checks) for h in hs)
        res["findings"], res["checks"] = best(checks, repeat)
    out = Path(tempfile.mkdtemp())
    with contextlib.redirect_stdout(io.StringIO()):
        _, res["draw"] = best(lambda: draw(proj, all_=True, no_render=True, out=out), repeat)
        if render and shutil.which("wireviz"):
            _, res["render"] = best(lambda: draw(proj, all_=True, out=out), 1)
    shutil.rmtree(out, ignore_errors=True)
    if sim:
        try:
            from schemagen.sim import api
            r, res["sim_op"] = best(lambda: api.operating_point(pr.model, pr.cfg), repeat)
            res["sim_iterations"] = r.iterations
            sw, res["sim_faults"] = best(lambda: api.fault_sweep(pr.model, pr.cfg), 1)
            res["sim_fault_nodes"] = len(sw.rows)
        except ImportError:
            pass
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="*", default=[1000, 5000])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--no-sim", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    from schemagen import synth
    tmp = Path(tempfile.mkdtemp())
    projects = {"demo": ROOT / "examples" / "demo"}
    for n in a.sizes:
        with contextlib.redirect_stdout(io.StringIO()): synth.main(n, a.seed, str(tmp / f"s{n}"))
        projects[f"synthetic {n}"] = tmp / f"s{n}"
    results = {k: phases(p, a.repeat, a.render, not a.no_sim) for k, p in projects.items()}
    keys = ["load", "net", "checks", "draw", "render", "sim_op", "sim_faults"]
    print(f"schemagen {__version__}, python {sys.version.split()[0]}")
    print("| project | wires | " + " | ".join(f"{k} (s)" for k in keys) + " | findings |")
    print("|---|---:|" + "---:|" * len(keys) + "---:|")
    for k, r in results.items():
        print(f"| {k} | {r['wires']} | " + " | ".join(f"{r[x]:.3f}" if x in r else "–" for x in keys) + f" | {r.get('findings', '')} |")
    if a.json: Path(a.json).write_text(json.dumps(dict(version=__version__, results=results), indent=1))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
