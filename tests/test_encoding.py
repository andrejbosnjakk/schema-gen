"""Text I/O always names its encoding: Windows defaults to cp1252, which garbles the · and − in wire labels."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOT_TEXT = {"tarfile", "zipfile", "webbrowser", "os"}  # X.open() that opens no text stream


def _binary(call: ast.Call) -> bool:
    mode = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "mode"), None)
    return isinstance(mode, ast.Constant) and "b" in str(mode.value)


def unencoded(src: str) -> list[int]:
    """Lines of open() / .open() / .read_text() / .write_text() calls in text mode without encoding=."""
    out = []
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.Call): continue
        f = n.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        if name not in ("open", "read_text", "write_text"): continue
        if any(k.arg == "encoding" or k.arg is None for k in n.keywords): continue  # **kwargs may carry it
        if name == "open" and _binary(n): continue
        if name == "open" and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in NOT_TEXT: continue
        out.append(n.lineno)
    return out


def test_checker_finds_what_it_should():
    bad = 'open("a")\np.read_text()\np.write_text(s)\nPath("x").open()\n'
    good = 'open("a", "rb")\np.read_text(encoding="utf-8")\nopen(f, mode="wb")\np.write_text(s, **kw)\n'
    assert unencoded(bad) == [1, 2, 3, 4] and unencoded(good) == []


def test_no_text_io_without_encoding():
    found = [f"{p.relative_to(ROOT)}:{ln}" for d in ("schemagen", "tests") for p in sorted((ROOT / d).rglob("*.py"))
             for ln in unencoded(p.read_text(encoding="utf-8"))]
    assert not found, "pass encoding= to: " + ", ".join(found)
