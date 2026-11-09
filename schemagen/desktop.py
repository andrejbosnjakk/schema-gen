"""The desktop app: the local server in a thread and the frontend in its own window (pywebview), for the installer.

    schemagen-desktop [<project>]   (no project: the start screen, or the bundled example on servers without one)

Logs go to %LOCALAPPDATA%\\schemagen\\logs\\schemagen.log (SCHEMAGEN_HOME overrides the folder); a startup failure is shown
in a native dialog, since the installed app has no terminal.
"""
from __future__ import annotations

import inspect
import logging
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("schemagen.desktop")


def home() -> Path:
    """The user folder for logs, settings and projects (never the install folder, which may be read-only)."""
    if os.environ.get("SCHEMAGEN_HOME"): return Path(os.environ["SCHEMAGEN_HOME"])
    if os.name == "nt": return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "schemagen"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "schemagen"


def bundled_example() -> Path | None:
    """The example shipped next to the app (PyInstaller) or in the source tree: examples/aircraft, else examples/demo."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return next((base / "examples" / n for n in ("aircraft", "demo") if (base / "examples" / n / "schemagen.yml").exists()), None)


def _logging() -> Path:
    d = home() / "logs"; d.mkdir(parents=True, exist_ok=True)
    f = d / "schemagen.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(f, encoding="utf-8")], force=True)
    if sys.stdout is None or sys.stderr is None:  # windowed exe: no console, so print() and tracebacks go to the log
        out = open(f, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or out; sys.stderr = sys.stderr or out
    return f


def _error(msg: str) -> None:
    log.error(msg)
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "schemagen", 0x10)  # MB_ICONERROR
    else: print(msg, file=sys.stderr)


def _project(arg: str | None):
    """The project to open; None when the server has a start screen (create_app(None)), else a copy of the example."""
    from .app.server import create_app
    if arg or inspect.signature(create_app).parameters["project"].default is None: return arg
    ex = bundled_example()
    if not ex: raise RuntimeError("no project given and no example bundled")
    dst = home() / "projects" / "Example"
    if not dst.exists(): shutil.copytree(ex, dst)  # the install folder is not for change sets
    return str(dst)


def main(argv: list[str] | None = None) -> int:
    """Start the server on a free 127.0.0.1 port, open the window, stop the server when the window closes."""
    argv = sys.argv[1:] if argv is None else argv
    logfile = _logging()
    ex = bundled_example()
    if ex and "SCHEMAGEN_EXAMPLE" not in os.environ: os.environ["SCHEMAGEN_EXAMPLE"] = str(ex)
    t0 = time.perf_counter()
    try:
        import uvicorn
        import webview
        from . import __version__
        from .app.server import create_app
        app = create_app(_project(argv[0] if argv else None), background=True)
        with socket.socket() as s: s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None))
        th = threading.Thread(target=server.run, daemon=True); th.start()
        url = f"http://127.0.0.1:{port}/"
        for _ in range(300):
            if not th.is_alive(): raise RuntimeError("the local server stopped during startup")
            try:
                with urllib.request.urlopen(url + "api/health", timeout=1) as r:
                    if r.status == 200: break
            except OSError: time.sleep(0.1)
        else: raise RuntimeError("the local server did not answer within 30 s")
        log.info("schemagen %s serving %s after %.2f s", __version__, url, time.perf_counter() - t0)
        webview.create_window("schemagen", url, width=1366, height=768, min_size=(1280, 720), maximized=True, background_color="#FFFFFF")
        icon = Path(getattr(sys, "_MEIPASS", "")) / "assets" / ("icon.ico" if os.name == "nt" else "icon-256.png")  # stream C's mark
        webview.start(private_mode=False, storage_path=str(home() / "webview"), icon=str(icon) if icon.is_file() else None)
    except Exception as e:  # noqa: BLE001  (shown to the user; the traceback is in the log)
        log.exception("startup failed")
        _error(f"schemagen could not start:\n\n{e}\n\nDetails are in {logfile}")
        return 1
    server.should_exit = True
    th.join(timeout=5)
    log.info("window closed, server stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
