"""Per-user data of the app: settings (tour, theme, recent projects), the projects folder (the example's copy and
imported sheets) and the log file. Root: SCHEMAGEN_HOME, else %LOCALAPPDATA%\\schemagen on Windows, else
$XDG_STATE_HOME/schemagen (~/.local/state/schemagen). Nothing here is project data.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import shutil
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULTS: dict[str, Any] = {"tour_done": False, "theme": "light", "recent": []}


def home() -> Path:
    if os.environ.get("SCHEMAGEN_HOME"): return Path(os.environ["SCHEMAGEN_HOME"])
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"): return Path(os.environ["LOCALAPPDATA"]) / "schemagen"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "schemagen"


def projects() -> Path:
    return home() / "projects"


def log() -> logging.Logger:
    """The app's logger, writing to <home>/logs/schemagen.log (rotated at 1 MB, 3 kept)."""
    lg = logging.getLogger("schemagen")
    path = home() / "logs" / "schemagen.log"
    if not any(isinstance(h, RotatingFileHandler) and Path(h.baseFilename) == path for h in lg.handlers):
        for h in [h for h in lg.handlers if isinstance(h, RotatingFileHandler)]: lg.removeHandler(h); h.close()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            h = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            lg.addHandler(h)
        except OSError: pass  # a read-only home: the app still runs, without a log
        lg.setLevel(logging.INFO); lg.propagate = False
    return lg


def settings() -> dict[str, Any]:
    try: d = json.loads((home() / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): d = {}
    return {**DEFAULTS, **(d if isinstance(d, dict) else {})}


def save_settings(**kw: Any) -> dict[str, Any]:
    d = {**settings(), **kw}
    p = home() / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.part")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"); tmp.replace(p)
    return d


def add_recent(name: str, path: Path) -> None:
    now = _dt.datetime.now().replace(microsecond=0).isoformat()
    rec = [r for r in settings()["recent"] if isinstance(r, dict) and r.get("path") != str(path)]
    save_settings(recent=[dict(name=name, path=str(path), opened=now)] + rec[:9])


def example_source() -> Path:
    """The shipped example: SCHEMAGEN_EXAMPLE, the desktop build's copy, the repository's (aircraft, else demo)."""
    if os.environ.get("SCHEMAGEN_EXAMPLE"): return Path(os.environ["SCHEMAGEN_EXAMPLE"])
    cands = [Path(sys._MEIPASS) / "examples" / "aircraft"] if getattr(sys, "_MEIPASS", None) else []
    cands += [REPO / "examples" / "aircraft", REPO / "examples" / "demo"]
    return next((p for p in cands if (p / "schemagen.yml").is_file()), cands[-1])


def example() -> Path:
    """The user's copy of the example (made the first time): the install folder is read-only and edits write change sets."""
    dest = projects() / "Example aircraft"
    if not (dest / "schemagen.yml").is_file():
        src = example_source()
        if not (src / "schemagen.yml").is_file(): raise FileNotFoundError(f"the example project is missing ({src})")
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("out", "__pycache__", "changes", "layout.json"), dirs_exist_ok=True)
    return dest


def new_import(filename: str, data: bytes) -> Path:
    """A project folder for an uploaded sheet (named after the file; a new folder each time, so nothing is overwritten)
    with the sheet copied in and a schemagen.yml that points at it."""
    from ..importers import readable
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(filename).name).strip(" .") or "sheet.xlsx"
    stem, k = Path(name).stem, 2
    dest = projects() / stem
    while dest.exists(): dest = projects() / f"{stem} ({k})"; k += 1
    dest.mkdir(parents=True)
    (dest / name).write_bytes(data)
    src: dict[str, Any] = {"path": name}
    try:
        if readable.detect(dest / name): src["format"] = "readable"
    except Exception as e:  # noqa: BLE001  (not a workbook at all)
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError(f"{filename} could not be read. Save it as .xlsx or .csv and try again.") from e
    import yaml
    (dest / "schemagen.yml").write_text(f"# Imported in the app from {filename}. Paths are relative to this file.\n"
                                        + yaml.safe_dump({"source": src}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return dest
