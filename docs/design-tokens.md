# Design tokens (1.0)

The contract between the design system (`frontend/src/theme/`, stream C) and the screens (stream B). Screens use only
these CSS variables, the `KindIcon` / `Logo` components, and the motion classes; no raw colours, sizes or durations.
The values in `frontend/src/theme/tokens.css` are the starting point; stream C refines values, never names.

## Theme switch

`<html data-theme="light|dark">`, light by default (the toggle stores the choice through `/api/settings`). Dark values
are designed (Linear / Blueprint dark as reference), not inverted.

## Type

- `--font`: Inter (bundled, `@fontsource-variable/inter`, OFL-1.1), then system UI.
- `--fs-xs` 11 px, `--fs-sm` 12 px, `--fs` 13 px (base), `--fs-md` 15 px, `--fs-lg` 18 px, `--fs-xl` 24 px.
- `--fw` 400, `--fw-med` 500, `--fw-bold` 600. `--lh` 1.45.

## Space (8 px grid)

`--s-half` 4 px, `--s1` 8, `--s2` 16, `--s3` 24, `--s4` 32, `--s6` 48. Control height `--control-h` 32 px (28 px small:
`--control-h-sm`).

## Colour

Neutral greys plus one accent; red / amber / green only for status.

| token | use |
|---|---|
| `--bg` | app background (top bar, panels) |
| `--canvas` | the diagram background (slightly darker than `--bg` in light) |
| `--surface` | cards, popups, inputs |
| `--surface-2` | hover rows, subtle fills, zone regions |
| `--border`, `--border-strong` | 1 px lines; strong for inputs and focus-less outlines |
| `--text`, `--text-2`, `--text-3` | primary, secondary, faint |
| `--accent`, `--accent-hover`, `--accent-soft`, `--on-accent` | the one accent: primary buttons, selection, links |
| `--ok`, `--warn`, `--err` and `--ok-soft`, `--warn-soft`, `--err-soft` | status only |
| `--focus` | focus ring |
| `--scrim` | backdrop behind popups |
| `--shadow-pop` | popups and menus only; nothing else has a shadow |

## Shape

`--radius` 6 px, `--radius-sm` 4 px, `--border-w` 1 px.

## Motion

`--dur-fast` 150 ms, `--dur` 200 ms, `--ease` `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out). Classes: `.anim-pop` (popup
open: fade + scale from 0.98), `.anim-drawer` (slide up), `.anim-panel` (slide from left), `.anim-pulse` (two pulses
of the accent ring, for zoom-to-object), `.skeleton` (loading shimmer). `prefers-reduced-motion` turns them off.

## Layers

`--z-panel` 10, `--z-drawer` 20, `--z-menu` 30, `--z-dialog` 40, `--z-toast` 50, `--z-tour` 60.

## Icons and logo

- `import { KindIcon, Logo } from "./theme/icons"`. `KindIcon({kind, size = 16})` covers: battery, dcdc, source,
  breaker, fuse, bus, ground, splice, harness, connector, switch, relay, device, avionics, light, motor, can, sensor;
  anything else falls back to `device`. Stroke icons, `currentColor`, 1.5 px stroke at 16 px.
- `Logo({size})` renders `frontend/src/theme/logo.svg` (the single source of the logo: two pins joined by one smooth
  S-shaped wire in a rounded square, one accent colour, readable at 16 px). App icons (`.ico`, `.png`) are generated
  from it into `packaging/assets/` by `frontend/src/theme/make_icons.py`.
