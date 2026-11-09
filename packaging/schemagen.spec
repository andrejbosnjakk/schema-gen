# PyInstaller spec for the desktop app: `pyinstaller packaging/schemagen.spec` (build.ps1 runs it). See docs/decisions.md D70-D74.
# onedir (not onefile): a onefile exe unpacks ~100 MB to %TEMP% on every start; onedir starts at once and the installer packs it anyway.
from pathlib import Path

HERE = Path(SPECPATH)
ROOT = HERE.parent
ASSETS = HERE / "assets"
EXAMPLE = next(p for p in (ROOT / "examples" / "aircraft", ROOT / "examples" / "demo") if (p / "schemagen.yml").exists())


def icon() -> Path:
    """Stream C's icon; until it lands, a temporary black-and-white tile in build/ (never committed under assets/)."""
    if (ASSETS / "icon.ico").exists(): return ASSETS / "icon.ico"
    from PIL import Image, ImageDraw
    tmp = HERE / "build" / "assets" / "icon.ico"; tmp.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGBA", (256, 256), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 8, 248, 248), 48, fill="#111418")
    d.polygon([(148, 28), (64, 144), (120, 144), (100, 228), (192, 104), (134, 104)], fill="white")  # the bolt
    im.save(tmp, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    return tmp


ICON = icon()
datas = [
    (str(ROOT / "schemagen" / "app" / "static"), "schemagen/app/static"),
    (str(ROOT / "schemagen" / "core" / "data"), "schemagen/core/data"),
    (str(ROOT / "schemagen" / "templates"), "schemagen/templates"),
    (str(EXAMPLE), f"examples/{EXAMPLE.name}"),
    (str(ICON), "assets"),  # the window icon (desktop.py reads assets/icon.ico)
]
datas += [(str(p), "assets") for p in ASSETS.glob("icon-*.png")]

# WireViz is GPL-3.0 and only ever run as a command: it, and what only it needs, never ships in the bundle.
EXCLUDES = ["wireviz", "graphviz", "PIL", "tkinter", "_tkinter", "matplotlib", "IPython", "pytest", "hypothesis", "setuptools", "pip",
            "webview.platforms.qt", "webview.platforms.gtk", "webview.platforms.cef", "webview.platforms.android", "webview.platforms.cocoa"]

a = Analysis([str(HERE / "launch.py")], pathex=[str(ROOT)], datas=datas, excludes=EXCLUDES,
             hiddenimports=["schemagen.app.server", "uvicorn.lifespan.on", "uvicorn.protocols.http.h11_impl", "uvicorn.loops.asyncio"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="schemagen", icon=str(ICON), console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="schemagen", upx=False)
