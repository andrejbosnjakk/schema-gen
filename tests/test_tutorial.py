"""docs/tutorial.md stays true: write its files, run its commands, check what it says they print."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TUT = (ROOT / "docs" / "tutorial.md").read_text(encoding="utf-8")


def blocks():
    """[(kind, arg, body)] for <!-- file: path --> and <!-- run[: expect-fail] --> markers, each followed by a fenced block."""
    pat = re.compile(r"<!-- (file|run)(?::\s*([^>]*?))? -->\n(`{3,4})[^\n]*\n(.*?)\n\3\n", re.S)
    return [(m.group(1), (m.group(2) or "").strip(), m.group(4)) for m in pat.finditer(TUT)]


def test_tutorial_runs(tmp_path):
    d = tmp_path / "tail-lamp"
    d.mkdir()
    bin_dir = Path(sys.executable).parent
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    out = {}
    bl = blocks()
    assert sum(k == "file" for k, _, _ in bl) == 6 and sum(k == "run" for k, _, _ in bl) == 6
    for kind, arg, body in bl:
        if kind == "file":
            p = d / arg; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(body + "\n", encoding="utf-8")
            continue
        r = subprocess.run(body, shell=True, cwd=d, env=env, capture_output=True, text=True)
        out[body.splitlines()[0]] = r
        if arg == "expect-fail": assert r.returncode == 1, r.stdout + r.stderr
        else: assert r.returncode == 0, r.stdout + r.stderr
    first = out["schemagen check ."]
    assert "error   gauge-protection   L04: 22 AWG is protected by CB-2 10 A; at most 5 A per FAA AC 43.13-1B, Table 11-3" in first.stdout
    assert "fix: use a breaker of 5 A or less, or a heavier gauge" in first.stdout
    assert out["sed -i.bak 's/CB-2 10 A/CB-2 5 A/' wires.csv && rm wires.csv.bak"].stdout.strip().endswith("0 error(s), 0 warning(s), 0 info")
    assert "expectation failed: LP-1: drop 1.058 V (max 1.0 V)" in out["schemagen sim ."].stdout
    fixed = out["sed -i.bak 's/,14 V,22,/,14 V,20,/; s/,GND,22,/,GND,20,/' wires.csv && rm wires.csv.bak"].stdout
    assert "0 error(s), 0 warning(s), 0 info" in fixed and "pass  tail lamp on:" in fixed
    assert "fault sweep: 10 nodes, 2 not cleared, 3 not selective, 1 wire damage, 0 over interrupt rating" in fixed
    assert (d / "out" / "coverage.txt").read_text().startswith("9 of 9 conductors in a drawing")
    for f in ("pinout.xlsx", "pinout.html", "wirelist.xlsx", "sheet.xlsx", "project.xlsx", "sim/report.html"): assert (d / "out" / f).exists(), f
    assert (d / "label_ledger.json").exists()
