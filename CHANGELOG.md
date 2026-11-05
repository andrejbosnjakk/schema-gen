# Changelog

## 0.6.0 (unreleased)

Fixes from running 0.5 on a real wire list, and Windows support.

- **Windows:** XLSX sources are closed after reading (no lock); every text read/write names UTF-8, enforced by a
  test; the tutorial edits files without `sed`; CI runs test, app (Playwright) and wheel jobs on Ubuntu and Windows
  with Python 3.12 and 3.14; frontend sources and built assets are LF so builds match across systems.
- **Row modules:** `P` / `D` / `O` entries may be tuples (field order in `tables.<table>.fields`); unreadable entries
  are warnings naming file, table and index; `display.set_protection` receives the entries as written.
- **Simulation:** a project without sources or loads is no longer a pass (exit 2, says what is missing);
  `schemagen sim --infer` assumes sources (`sim.sources`) and loads (conductor current), all marked assumed.
- **Pinout:** a printable reintegration checklist: one row per conductor end (splices and buses included), display
  names, gauge, colour, wire name, check columns, A4 landscape, `--page-breaks`.
- **Direction rule:** bonds have no direction; returns judged by where the chain ends; sender / receiver fallbacks
  for untyped signals; `direction-unknown` (info) counts the rest.
- **CAN:** terminations inferred from device names and nodes from stubs when there is no card data; stub limit by bit
  rate (SAE J1939-11, ISO 11898-2).
- **App:** display names in the wire table, object pages and graph (codes in tooltips), column chooser.
- `docs/citations.md`: every cited value with its clause and whether it has been checked.

## 0.5.0

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
