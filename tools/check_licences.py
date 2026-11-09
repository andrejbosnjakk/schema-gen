"""Licence check for runtime dependencies (CI). Python: the install closure of schema-gen (package schemagen); npm: the production
dependencies of frontend/ (when node_modules exists). Fails on anything that is not permissive.

WireViz (GPL-3.0) is the one exception: schemagen runs it as a separate command and never imports it, so it and the
packages only it needs are reported but not counted.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ALLOWED = re.compile(r"\b(MIT|BSD|Apache|ISC|PSF|Python Software Foundation|HPND|MIT-CMU|0BSD|Unlicense|CC0|Zlib|BlueOak)\b", re.I)
EXTERNAL = {"wireviz"}  # run as a command only
ROOT = Path(__file__).resolve().parents[1]


def licence(dist: metadata.Distribution) -> str:
    m = dist.metadata
    expr = m.get("License-Expression")
    if expr: return expr
    cls = [c.split("::")[-1].strip() for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
    if cls: return "; ".join(cls)
    return (m.get("License") or "UNKNOWN").splitlines()[0][:80]


def requires(name: str) -> list[str]:
    try: reqs = metadata.requires(name) or []
    except metadata.PackageNotFoundError: return []
    out = []
    for r in reqs:
        if "extra ==" in r: continue
        out.append(re.split(r"[ ;<>=!~\[(]", r, maxsplit=1)[0].lower())
    return out


def python_closure() -> tuple[dict[str, str], dict[str, str]]:
    seen: dict[str, str] = {}
    external: dict[str, str] = {}
    todo = requires("schema-gen")
    while todo:
        n = todo.pop()
        key = n.replace("_", "-")
        if key in seen or key in external: continue
        try: d = metadata.distribution(n)
        except metadata.PackageNotFoundError: continue
        if key in EXTERNAL: external[key] = licence(d); continue
        seen[key] = licence(d)
        todo += requires(n)
    return seen, external


def npm_licences() -> dict[str, str]:
    fe = ROOT / "frontend"
    if not (fe / "node_modules").exists(): return {}
    r = subprocess.run([shutil.which("npm") or "npm", "ls", "--omit=dev", "--all", "--json"], cwd=fe, capture_output=True, text=True)
    tree = json.loads(r.stdout or "{}")
    out: dict[str, str] = {}

    def walk(deps: dict) -> None:
        for name, d in (deps or {}).items():
            pj = fe / "node_modules" / name / "package.json"
            if name not in out and pj.exists():  # an optional peer that is not installed is not in the bundle
                lic = json.loads(pj.read_text(encoding="utf-8")).get("license", "UNKNOWN")
                out[name] = lic if isinstance(lic, str) else str(lic)
            walk(d.get("dependencies", {}))  # a "deduped" entry has no children; the full one does
    walk(tree.get("dependencies", {}))
    return out


def main() -> int:
    py, ext = python_closure()
    npm = npm_licences()
    bad = []
    for kind, items in (("python", py), ("npm", npm)):
        for n, lic in sorted(items.items()):
            ok = bool(ALLOWED.search(lic))
            print(f"{kind:6} {n:28} {lic}{'' if ok else '   <-- not permissive'}")
            if not ok: bad.append(f"{kind}:{n}")
    for n, lic in ext.items(): print(f"python {n:28} {lic}   (external command, not imported)")
    if bad: print("not permissive:", ", ".join(bad)); return 1
    print(f"ok: {len(py)} python and {len(npm)} npm runtime dependencies are permissive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
