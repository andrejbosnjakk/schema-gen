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
- `Logo({size})` renders `frontend/src/theme/logo.svg`, the single source of the logo: the owner's bolt mark (a
  lightning bolt drawn as one wire between two round pin nodes, rounded corners), used as given. The logo and icons
  are strictly black and white, never the accent: `--logo` is near-black `#111418` on light backgrounds and white on
  dark (the SVG uses `currentColor`, so `Logo` inlines it). App icon: the white mark on a near-black rounded tile; the
  black mark on a white tile only where a light icon fits better. The `.ico`, PNG sizes, window icon, installer
  icon and start-screen logo are all generated from that one SVG into `packaging/assets/` by
  `frontend/src/theme/make_icons.py`, and checked for legibility at 16 px.

## Using the theme

`import "./theme"` (from `src/`) loads Inter, `tokens.css`, `base.css` (element defaults, focus ring, scrollbars, motion
classes) and `components.css`, and re-exports `KindIcon`, `Icon`, `Logo`. `Icon({name, size = 16})` names: import,
export, play, sun, moon, plus, fit, zoom-in, zoom-out, close, chevron-down/up/left/right, help, alert, warning, check,
info, search, x-circle, refresh, folder, file, grip. `node src/theme/contrast.mjs` checks the contrast of the colour
tokens; `src/theme/Specimen.tsx` is the style sheet page (`/specimen.html` under `npx vite`, `?theme=dark`).

## Component classes (`components.css`)

| class | what |
|---|---|
| `.btn` | the default (secondary) button: 32 px, surface fill, strong border; `.btn-sm` 28 px |
| `.btn-primary` | accent fill, one per area (Simulate, Apply) |
| `.btn-ghost` | no border or fill until hover; toolbars; `aria-pressed="true"` shows it as on |
| `.btn-danger` | red fill, destructive confirmations only |
| `.btn-icon` | square icon-only button, combine with `.btn-ghost` / `.btn-sm`; give it an `aria-label` |
| `.input` | text input, `select.input`, `textarea.input`; `aria-invalid="true"` turns the border red |
| `.badge`, `.badge-ok`, `.badge-warn`, `.badge-err` | status pill with a dot; neutral without a modifier |
| `.card` | flat bordered surface (diagram blocks, panel sections); no shadow |
| `.dialog` | popup card with shadow; optional `header` / `section` / `footer` children |
| `.menu`, `.menu-item` | dropdown / context menu; `aria-selected="true"` for the active item, `.menu-item-danger` |
| `.kbd` | a key (`<span class="kbd">K</span>`) |
| `.divider` | 1 px line; `.divider divider-v` vertical inside a flex row |
| `.tooltip` | dark chip, absolutely positioned by the caller |
