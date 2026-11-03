# Changelog

## 0.5.0 (unreleased)

Distribution renamed to **`schema-gen`** on PyPI (the name `schemagen` is taken by another project); the import
package and the command stay `schemagen`. Every 0.2 command, the row-module input and the table input keep working;
0.2 module paths (`schemagen.drawing`, `.outputs`, `.cards`, `.project`, `.net`, `.palette`, `.config`, `.table`,
`.styles`, `.display_default`) are kept as thin re-exports.

### 0.3: typed model, rules and views
- Typed, lossless core model (Pydantic v2) with JSON Schemas in `schemas/`; unknown input keys survive in `extra`;
  `P` / `D` / `O` tables become protective devices, decisions and open items; validation errors name file, row and column.
- Importers: row modules, XLSX / CSV / CSV folder / JSON tables (plain or 0.2 column names), WireViz YAML, part cards.
  Exporters: neutral workbook or CSV folder, JSON model.
- Explicit connector-half sides (`sides:` or a side column); the `near_words` guess remains as a fallback with a warning.
- Rules engine (24 rules, severity, objects, fix hints, config switches); `schemagen check --format text|json|sarif`.
- Wire direction convention and `schemagen fix direction` (change set + diff, never silent).
- Pinout (XLSX, HTML), readable wire list, sheet template with dropdowns, label ledger, `schemagen diff` (folders or
  git revisions), interface drawings so every conductor is drawn, coverage report, parallel WireViz rendering.
- Change sets (`changes/*.json`) applied on load: the edit mechanism for every source format.

### 0.4: DC simulation
- Modified nodal analysis (scipy sparse), Newton for constant-power / constant-current loads and current-limited
  sources, relay coils to a fixed point (oscillation reported), breaker and fuse trip curves.
- Provenance on every parameter (measured / datasheet / design / estimated / assumed) and on every result.
- Scenario files with `set`, `faults`, `expect`; `schemagen sim` (HTML + JSON report, non-zero exit on failure).
- Fault sweep: prospective current, first trip and time, wire I²t survival, interrupt rating, selectivity.

### 0.5: the app
- `schemagen app`: local FastAPI server and bundled React + TypeScript frontend: wire table editor (change sets,
  undo), object pages with git history, net explorer across table, drawings and graph, system graph, simulation
  dashboard, issues board, diff and direction-fix preview, Ctrl-K search. Light and dark. No network, no telemetry.

### Tooling
- `schemagen synth` (synthetic projects), `benchmarks/bench.py`, licence check for Python and npm runtime
  dependencies, CI: ruff, mypy (strict on `core/` and `sim/`), pytest with coverage, demo render, Playwright end to
  end, wheel install with pipx and a smoke test.
