# Changelog

## 1.2.0-dev (pre-release, branch dev/1.2)

Reliable drawings. A preview for trying the app; the drawings are a review draft, not a wiring set. Contains all of 1.1.

- The overview is one PDF of three pages made by one engine: power distribution, CAN network, all wires (Export > Overview,
  `overview.pdf`; Wiring diagrams writes it too). Every wire carries its label next to its own wire and no other; a breaker
  terminal that has no wire says `LINE: not in wire list` instead of drawing a stub. `check-drawings` reads `overview.pdf` page by
  page against the wire list. Known: in dense bundles a few wires (the fixture's jumper; 30 of 800 on the real project) find
  no room for their label.
- Export runs as a background job: progress bar, Cancel, the folder opens when done. One drawing that fails is listed
  and the rest complete; drawings stream to disk instead of being held in memory.
- `schemagen check-drawings <project> <pdf folder>`: an independent verifier that reads the PDFs back (no drawing-engine
  code) and compares every wire, pin, gauge, colour, junction, wire-table row and off-sheet flag with the wire list.
- Components that do not fit one sheet are drawn as terminal strips: one stub and flag per wire, no routing across the
  sheet. Boxes and flags show the Name column; flags name the far drawing and sheet.
- Title block: source file name and content hash, `revision:` and `date:` from schemagen.yml. Output is deterministic.
- Faster drawing (text-width cache, routing memo, one layout per page).
- Text is wrapped instead of cut (the verifier reports any text ending in `..`); a flag that names several far sheets gets
  one sheet per flag; the wire table is printed once per drawing, its rows under the first sheet that draws each wire.
- The book starts with a contents page (name, id, sheets, start page) that the verifier checks against the book.
- The verifier has mutation tests for wrapped cells and the contents page.
- The installer workflow builds `dev/1.2*` branches and `v*` tags; a `v*` tag publishes the installer as a GitHub release
  (pre-release when the tag has a "-"). The start screen shows a small wire-and-breaker picture and a one-line statement.
- Known open: sheet counts are above target.

## 1.1.0 (merged into 1.2; branch dev/1.1, never released separately)

Real wiring drawings, made by schemagen itself (decision D106): the drawing engine in `schemagen/drawing/` (geometry JSON,
SVG in the app, SVG and PDF export, A3 / A4 sheets with a title block, a netlist round trip as the accuracy check).
WireViz is an optional extra (D107). Merged into `dev/1.2` (merge 92444f9). What the branch added:

- The map labels a line with its wire count ("6 wires"); a single wire shows its own label. Hovering a card lights its
  power circuit. The per-wire menu on edges is gone.
- The component card shows a drawing of each pin's run (`GET /api/drawing/{id}`, `?to=` for one line) instead of the
  pin table. This first version is not the planned engine.
- A line with several wires opens a connection card.
- "Save as PDF" prints the card's drawing as a sheet with a title block.
- The app uses the drawing engine: "Wiring diagram" on the component and connection cards, and shift-click on the map
  (a selection bar), open a viewer (zoom, pan, sheets) with "Save as PDF" (`GET /api/diagram`). Export "Wiring diagrams"
  writes a PDF per component and one book with the symbol sheet; it no longer needs Graphviz or WireViz (D113). The
  print sheet of the cards is gone.

## 1.0.0

One screen, one idea: import a wire list, see the system, find what is wrong, simulate. Reviewed on branch dev/1.0.
`pyproject.toml` went from 0.6.0 to 1.0.0; there was no separate 0.7 release.

- **Main screen:** a start screen, drag-and-drop import, one block diagram of the whole system (components in power-flow
  order, zones as blocks, bundles instead of wires, no overlapping edge labels), an Issues list in sentences grouped by
  cause, and a compact Wires drawer. Light and designed dark theme, bundled Inter font, black-and-white bolt logo.
- **Cards:** a popup card per component and per wire; read first (issues, then pins and wires), Edit reveals the fields.
  Edits and rating changes are change sets. Adding or removing a card pins every position, so nothing jumps.
- **Simulate:** one button draws the DC result on the cards: voltages, breaker and wire loading, a one-line reason per
  object, a summary chip. A wire that carries more than its gauge allows is too small; one that carries less than
  its breaker rating means the breaker is too big. A bus with loads and no source is never a pass.
- **+ Source:** click a bus and add a battery; stored as a change set, removable.
- **Quickstart tour:** eight steps on the example, advancing on the user's actions, skippable and replayable.
- **Example project:** `examples/aircraft`, a fictional electric aircraft (121 wires, three deliberate mistakes).
- **Desktop app and installer:** `schemagen/desktop.py` (pywebview window around the local server), PyInstaller onedir
  build, per-user Inno Setup installer (`packaging/build.ps1`, CI workflow `installer.yml`). Not code-signed. The
  installer contains no WireViz and no Graphviz (D72).
- **API:** one `/api/workspace` call for the main screen, card endpoints, `/api/simulate`, `/api/sources`,
  `/api/export`, one error shape, a session with recent projects (docs/api.md). The 0.5 endpoints remain.
- **Export:** the checklist (one table per component with tick boxes, A4 print layout); harness drawings fail with a
  plain message when Graphviz or WireViz is missing and leave nothing behind.
- A file that is not a spreadsheet, or has no wires, gets a plain message.
- Docs: `docs/api.md`, `docs/tour.md`, `docs/design-tokens.md`, `docs/review-notes.md`.

## 0.7 (in the 1.0 line, never released on its own)

- **Readable-sheet importer and exporter:** connector and pin grammar, device kinds from names (a Components tab
  overrides), unparseable cells as findings, near-duplicate names, `schemagen export --readable`,
  `schemagen synth --readable`, `schemagen fix names` (docs/readable.md).
- **Fixes from running a real sheet:** CAN wires by name and CAN terminations after T-pieces or by jumper; no direction
  for terminator leads, loops, E-STOP chains or returns through a harness; text such as TBD in number columns is
  kept on the round trip; harness connectors keep the code their name carries; default harness sides.
- **Drawings:** an item's interface drawing shows every wire on it; connector size from the name (D-sub 25, 12-pin);
  Graphviz is found on PATH, `SCHEMAGEN_DOT` or the install folders.
- **Workspace shell and system canvas** (React Flow, dagre): the base the 1.0 screen replaced.
- `schemagen sim --infer` also finds sources by name ("14 V battery", "DC/DC converter").

## 0.6.0

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
