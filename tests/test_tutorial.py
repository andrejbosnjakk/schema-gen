"""docs/tutorial.md stays true: write its files, run its commands, check what it says they print."""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TUT = (ROOT / "docs" / "tutorial.md").read_text(encoding="utf-8")


def blocks():
    """[(kind, arg, body)] for <!-- file: path -->, <!-- edit: path --> and <!-- run[: expect-fail] --> markers, each followed by a fenced block."""
    pat = re.compile(r"<!-- (file|edit|run)(?::\s*([^>]*?))? -->\n(`{3,4})[^\n]*\n(.*?)\n\3\n", re.S)
    return [(m.group(1), (m.group(2) or "").strip(), m.group(4)) for m in pat.finditer(TUT)]


def test_tutorial_runs(tmp_path):
    d = tmp_path / "tail-lamp"
    d.mkdir()
    bin_dir = Path(sys.executable).parent
    env = {"PATH": os.pathsep.join([str(bin_dir), "/usr/bin", "/bin"]), "HOME": str(tmp_path)}
    if os.name == "nt": env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    out = []
    bl = blocks()
    assert sum(k == "file" for k, _, _ in bl) == 6 and sum(k == "edit" for k, _, _ in bl) == 2 and sum(k == "run" for k, _, _ in bl) == 6
    for kind, arg, body in bl:
        if kind == "file":
            p = d / arg; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(body + "\n", encoding="utf-8")
            continue
        if kind == "edit":  # find and replace, one "old  ->  new" per line; no sed, so it runs on Windows too
            p = d / arg; s = p.read_text(encoding="utf-8")
            for line in body.splitlines():
                old, new = line.split("  ->  "); assert old in s, old; s = s.replace(old, new)
            p.write_text(s, encoding="utf-8")
            continue
        r = subprocess.run(" && ".join(body.splitlines()), shell=True,  # cmd /c runs only the first line of a block
                           cwd=d, env=env, capture_output=True, text=True)
        out.append(r)
        if arg == "expect-fail": assert r.returncode == 1, r.stdout + r.stderr
        else: assert r.returncode == 0, r.stdout + r.stderr
    first = out[0]
    assert "error   gauge-protection   L04: 22 AWG is protected by CB-2 10 A; at most 5 A per FAA AC 43.13-1B, Table 11-3" in first.stdout
    assert "fix: use a breaker of 5 A or less, or a heavier gauge" in first.stdout
    assert out[1].stdout.strip().endswith("0 error(s), 0 warning(s), 0 info")
    assert "expectation failed: LP-1: drop 1.058 V (max 1.0 V)" in out[3].stdout
    fixed = out[4].stdout
    assert "0 error(s), 0 warning(s), 0 info" in fixed and "pass  tail lamp on:" in fixed
    assert "fault sweep: 10 nodes, 2 not cleared, 3 not selective, 1 wire damage, 0 over interrupt rating" in fixed
    assert (d / "out" / "coverage.txt").read_text(encoding="utf-8").startswith("9 of 9 conductors in a drawing")
    for f in ("pinout.xlsx", "pinout.html", "wirelist.xlsx", "sheet.xlsx", "project.xlsx", "sim/report.html"): assert (d / "out" / f).exists(), f
    assert (d / "label_ledger.json").exists()
