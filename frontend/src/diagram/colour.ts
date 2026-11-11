// Wire colours as drawn: the palette's colour, toned toward the text colour, and swapped for a lighter variant
// (--text-3) when it would be too close to the background to see (black GND wires on the dark canvas).
import { useSyncExternalStore } from "react";

const lum = (c: [number, number, number]) => {
  const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
};
const contrast = (a: [number, number, number], b: [number, number, number]) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const rgb = (s: string): [number, number, number] | null => {
  s = s.trim();
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s);
  if (m) { const h = m[1].length === 3 ? m[1].replace(/./g, "$&$&") : m[1]; return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number]; }
  const r = /rgba?\((\d+)[ ,]+(\d+)[ ,]+(\d+)/.exec(s);
  return r ? [+r[1], +r[2], +r[3]] : null;
};

/** Watches <html data-theme>: components that draw palette colours re-render when it flips. */
export const useTheme = () => useSyncExternalStore(
  (cb) => { const o = new MutationObserver(cb); o.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] }); return () => o.disconnect(); },
  () => document.documentElement.dataset.theme || "light", () => "light");

const cache = new Map<string, string>();
/** CSS colour to draw `hex` in on the surface named by the CSS variable `on` (--canvas, --bg), contrast at least 3:1. `theme` keys the cache. */
export function drawn(hex: string, on = "--canvas", theme = "light", ratio = 3): string {
  const key = `${theme}|${on}|${hex}`;
  let v = cache.get(key);
  if (v) return v;
  const css = getComputedStyle(document.documentElement), bg = rgb(css.getPropertyValue(on)), text = rgb(css.getPropertyValue("--text")), c = rgb(hex);
  if (!c || !bg || !text) v = hex || "var(--text-3)";
  else {
    let t = 0.28, toned = c;
    for (; t <= 1; t += 0.06) { toned = c.map((x, i) => Math.round(x * (1 - t) + text[i] * t)) as [number, number, number]; if (contrast(toned, bg) >= ratio) break; }
    v = `rgb(${toned.join(",")})`;  // too close to the surface: pulled toward the text colour until it shows (black GND on dark becomes grey)
  }
  cache.set(key, v);
  return v;
}
