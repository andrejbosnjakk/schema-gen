// Checks the WCAG contrast of the colour tokens in tokens.css, both themes. Run: node src/theme/contrast.mjs
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");
const block = (sel) => Object.fromEntries([...css.split(sel)[1].split("}")[0].matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})\b/gi)]
  .map((m) => [m[1], m[2]]));
const light = block(':root[data-theme="light"] {'), dark = { ...light, ...block(':root[data-theme="dark"] {') };
const lum = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)).reduce((s, c, i) => s + c * [0.2126, 0.7152, 0.0722][i], 0);
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const checks = [
  ...["text", "text-2"].flatMap((t) => ["bg", "surface", "canvas", "surface-2"].map((b) => [t, b, 4.5])),
  ["on-accent", "accent", 4.5], ["accent", "surface", 4.5], ["accent", "accent-soft", 4.5],
  ...["ok", "warn", "err"].flatMap((s) => [[s, `${s}-soft`, 3], [s, "surface", 3]]),
];
let bad = 0;
for (const [name, t] of [["light", light], ["dark", dark]]) {
  for (const [fg, bg, min] of checks) {
    const r = ratio(t[fg], t[bg]), ok = r >= min;
    if (!ok) bad++;
    console.log(`${name.padEnd(5)} --${fg.padEnd(10)} on --${bg.padEnd(11)} ${r.toFixed(2).padStart(5)}:1  (min ${min})  ${ok ? "ok" : "FAIL"}`);
  }
}
console.log(bad ? `${bad} pair(s) below the minimum` : "all pairs pass");
process.exit(bad ? 1 : 0);
