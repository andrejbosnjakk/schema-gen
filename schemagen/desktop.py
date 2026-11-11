"""The desktop app: the local server in a thread and the frontend in its own window (pywebview), for the installer.

    schemagen-desktop [<project>]   (no project: the start screen)

Logs go to %LOCALAPPDATA%\\schemagen\\logs\\schemagen.log (SCHEMAGEN_HOME overrides the folder); a startup failure is shown
in a native dialog, since the installed app has no terminal.
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

from .app.userdata import home

log = logging.getLogger("schemagen.desktop")


def bundled_example() -> Path | None:
    """The example shipped next to the app (PyInstaller) or in the source tree: examples/aircraft, else examples/demo."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return next((base / "examples" / n for n in ("aircraft", "demo") if (base / "examples" / n / "schemagen.yml").exists()), None)


def _logging() -> Path:
    """The app's rotating log (app/userdata.py); a windowed exe has no console, so print() and tracebacks go to stdout.log."""
    from .app import userdata
    userdata.log()
    if sys.stdout is None or sys.stderr is None:
        out = open(home() / "logs" / "stdout.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or out; sys.stderr = sys.stderr or out
    return home() / "logs" / "schemagen.log"


def _error(msg: str) -> None:
    log.error(msg)
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "schemagen", 0x10)  # MB_ICONERROR
    else: print(msg, file=sys.stderr)


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
        app = create_app(argv[0] if argv else None, background=True)  # no project: the start screen
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
