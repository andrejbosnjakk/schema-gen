"""Generate the app icons in packaging/assets/ from logo.svg (the single source of the logo). Dev-only: needs Pillow.

The white mark on a near-black rounded tile: icon.ico (16-256) and icon-<n>.png. Run from anywhere:
    python frontend/src/theme/make_icons.py
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[2] / "packaging" / "assets"
TILE, MARK = "#111418", "#ffffff"  # --logo light; the dark-theme mark colour
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_SIZES = [16, 32, 48, 256, 512]
SS = 8  # supersampling factor


def geometry() -> tuple[list[tuple[float, float]], float, list[tuple[float, float, float]], float]:
    """The wire polyline, its stroke width, the pin circles and the viewBox size, read from logo.svg."""
    svg = re.sub(r"<metadata>.*?</metadata>", "", (HERE / "logo.svg").read_text(encoding="utf-8"), flags=re.S)
    box = float(re.search(r'viewBox="0 0 ([\d.]+) [\d.]+"', svg).group(1))
    path = re.search(r'<path d="([^"]+)"[^>]*stroke-width="([\d.]+)"', svg)
    nums = [float(n) for n in re.findall(r"-?[\d.]+", path.group(1))]
    pts = list(zip(nums[::2], nums[1::2]))
    circles = [tuple(map(float, c)) for c in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', svg)]
    return pts, float(path.group(2)), circles, box


def render(size: int) -> Image.Image:
    """One icon: the mark centred on a rounded tile; strokes thicken a little below 32 px so they stay visible."""
    pts, sw, circles, box = geometry()
    xs = [x for x, _ in pts] + [c[0] for c in circles]
    ys = [y for _, y in pts] + [c[1] for c in circles]
    pad = max(sw / 2, *(c[2] for c in circles))
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    n = size * SS
    fill = 0.72 if size >= 32 else 0.8  # the mark's share of the tile height
    k = n * fill / (y1 - y0)
    ox, oy = (n - (x1 - x0) * k) / 2 - x0 * k, (n - (y1 - y0) * k) / 2 - y0 * k
    boost = 1.0 if size >= 32 else 1.25 if size >= 24 else 1.45  # at 16 px a 1 px wire would vanish into antialiasing
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, n - 1, n - 1), radius=n * 0.22, fill=TILE)
    p = [(ox + x * k, oy + y * k) for x, y in pts]
    w = sw * k * boost
    d.line(p, fill=MARK, width=round(w))
    for x, y in p: d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=MARK)  # round caps and joins
    for cx, cy, r in circles:
        x, y, r = ox + cx * k, oy + cy * k, r * k * min(boost, 1.2)
        d.ellipse((x - r, y - r, x + r, y + r), fill=MARK)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in PNG_SIZES: render(s).save(OUT / f"icon-{s}.png")
    imgs = [render(s) for s in ICO_SIZES]
    imgs[-1].save(OUT / "icon.ico", sizes=[(s, s) for s in ICO_SIZES], append_images=imgs[:-1])
    print(f"wrote {OUT}: icon.ico ({', '.join(map(str, ICO_SIZES))}), " + ", ".join(f"icon-{s}.png" for s in PNG_SIZES))


if __name__ == "__main__":
    main()
