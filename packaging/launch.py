"""PyInstaller entry point for the desktop app (schemagen/desktop.py)."""
import subprocess
import sys

if sys.platform == "win32":  # a windowless app: a console program it starts (dot -V, git log) must not flash a console window
    _popen = subprocess.Popen.__init__

    def _no_window(self, *a, **k):
        k["creationflags"] = k.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        _popen(self, *a, **k)
    subprocess.Popen.__init__ = _no_window

from schemagen.desktop import main  # noqa: E402

sys.exit(main())
