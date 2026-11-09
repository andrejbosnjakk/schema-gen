"""Write packaging/licences/THIRD_PARTY.txt from what PyInstaller actually bundled (build/work/schemagen/*.toc) and the
frontend's npm production dependencies. Fails when a bundled package is not permissive or WireViz slipped in.

    python packaging/third_party.py   (after pyinstaller; build.ps1 runs it)
"""
from __future__ import annotations

import ast
import sys
from importlib import metadata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
from check_licences import ALLOWED, npm_licences
from check_licences import licence as meta_licence  # noqa: E402

WORK = HERE / "build" / "work" / "schemagen"
OUT = HERE / "licences" / "THIRD_PARTY.txt"
NEVER = {"wireviz", "graphviz", "pillow"}  # GPL WireViz and what only it needs stay out of the bundle (D72)
FIXED = [  # bundled, but not Python distributions
    ("Python", "PSF-2.0", "the Python runtime (python3xx.dll and the standard library), https://docs.python.org/3/license.html"),
    ("PyInstaller bootloader", "GPL-2.0-or-later WITH Bootloader-exception",
     "the exception allows distributing the bootloader with any program under any licence, https://pyinstaller.org/en/stable/license.html"),
    ("Microsoft WebView2 SDK (webview/lib)", "BSD-3-Clause (Microsoft)", "the loader pywebview ships; the WebView2 runtime itself is part of Windows"),
    ("Microsoft Visual C++ runtime (vcruntime140.dll)", "Microsoft redistributable", "shipped with Python for Windows"),
]


def bundled_dists() -> dict[str, metadata.Distribution]:
    """Distributions with at least one module or file in the bundle."""
    tops: set[str] = set()
    for toc in ("PYZ-00.toc", "COLLECT-00.toc"):
        data = ast.literal_eval((WORK / toc).read_text(encoding="utf-8"))
        entries = data[1] if toc.startswith("PYZ") else data[0]
        for e in entries:
            name = e[0].replace("\\", "/")
            tops.add(name.split("/")[0].split(".")[0] if "/" in name or e[2] == "PYMODULE" else name.split(".")[0])
    owners = metadata.packages_distributions()
    out = {}
    for t in tops:
        for d in owners.get(t, []):
            dist = metadata.distribution(d)
            out[dist.metadata["Name"].lower().replace("_", "-")] = dist
    return out


def licence_text(dist: metadata.Distribution) -> str:
    files = [f for f in dist.files or [] if any(k in f.name.upper() for k in ("LICEN", "COPYING", "NOTICE"))]
    return "\n\n".join(Path(f.locate()).read_text(encoding="utf-8", errors="replace").strip() for f in files if f.locate().is_file())


def licence(dist: metadata.Distribution) -> str:
    """The metadata licence, else the first line of the licence file (clr_loader declares none: its file says MIT)."""
    lic = meta_licence(dist)
    return lic if lic != "UNKNOWN" else next((x.strip() for x in licence_text(dist).splitlines() if x.strip()), lic)


def main() -> int:
    dists = bundled_dists()
    dists.pop("schema-gen", None)
    bad = sorted(n for n, d in dists.items() if n in NEVER or not ALLOWED.search(licence(d)))
    if bad: print("not allowed in the bundle:", ", ".join(f"{n} ({licence(dists[n])})" for n in bad)); return 1
    npm = npm_licences()
    lines = ["schemagen: third-party software in this installation", "=" * 52, "",
             "schemagen itself is MIT-licensed (see LICENSE.txt). It bundles the components below, each under its own licence.",
             "WireViz (GPL-3.0) and Graphviz (EPL-1.0) are not bundled: harness drawings use them only if they are installed separately.", "",
             "Summary", "-------"]
    lines += [f"{n:40} {lic}" for n, lic, _ in FIXED]
    lines += [f"{n + ' ' + d.version:40} {licence(d)}" for n, d in sorted(dists.items())]
    if npm: lines += ["", "Frontend (JavaScript, bundled in the app's web assets)", "-" * 54] + [f"{n:40} {lic}" for n, lic in sorted(npm.items())]
    else: lines += ["", "Frontend: the JavaScript dependencies of frontend/package.json (all MIT/ISC/BSD/Apache, checked by tools/check_licences.py)."]
    lines += ["", "", "Notes", "-----"] + [f"{n}: {note}" for n, _, note in FIXED] + ["", "", "Licence texts", "-------------"]
    for n, d in sorted(dists.items()):
        lines += ["", f"== {n} {d.version} ({licence(d)}) ==", "", licence_text(d) or "(no licence file in the package metadata; see its project page)"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(dists)} Python packages, {len(npm)} npm packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
