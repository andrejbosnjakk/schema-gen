"""Start `schemagen app` on a throwaway copy of a project, for the end-to-end tests.

    python e2e/serve.py demo 8801       # the demo, in a fresh git repo, with one wire written backwards
    python e2e/serve.py synth5k 8802    # a synthetic 5,000-wire project
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def prepare(kind: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=f"sg-e2e-{kind}-"))
    if kind == "demo":
        d = tmp / "demo"
        shutil.copytree(ROOT / "examples" / "demo", d, ignore=shutil.ignore_patterns("out"))
        p = d / "wirelist" / "ss01_demo.py"  # one wire written ground bus -> battery, for the direction-fix flow
        p.write_text(p.read_text(encoding="utf-8").replace(
            'row("GND-BAT-1", "BAT battery 14 V", "−", "", "GNDB ground bus", "Stud", ""',
            'row("GND-BAT-1", "GNDB ground bus", "Stud", "", "BAT battery 14 V", "−", ""'), encoding="utf-8")
        git = lambda *a: subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)  # noqa: E731
        git("init", "-q"); git("add", "."); git("-c", "user.email=e2e@example.invalid", "-c", "user.name=e2e", "commit", "-qm", "demo")
        if shutil.which("wireviz") and shutil.which("dot"):
            subprocess.run([sys.executable, "-m", "schemagen", "draw", str(d)], check=True, capture_output=True)
        return d
    from schemagen import synth
    synth.main(5000, 1, str(tmp / "s5k"))
    return tmp / "s5k"


if __name__ == "__main__":
    kind, port = sys.argv[1], sys.argv[2]
    d = prepare(kind)
    from schemagen.app.server import serve
    serve(d, "127.0.0.1", int(port), open_browser=False)
