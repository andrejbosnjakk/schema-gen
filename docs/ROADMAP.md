# Roadmap

Goal: an open-source tool for wiring design with one source of truth and many views (drawings, tables, test sheets,
simulation), with checks built in and every value traceable to its source.

## Done

**0.1**
- Harness drawings per harness connector (WireViz), "continues at" notes from the net model
- Cut list, continuity/insulation test sheet, consistency checks, searchable offline index page
- Project config (`schemagen.yml`), default display for projects without their own naming module
- Fictional demo project, tests, CI; general-purpose (project rules live in the project's config)

**0.2 (P0 quick wins)**
- Table input (CSV / XLSX / JSON with column mapping) and `schemagen export` to the neutral format
- Split wide harnesses by side or function (`auto` above a threshold)
- Short next-hop notes, full continuation in a numbered footnote table (drawing HTML, index, cut list)
- One bundle per far item, gauge in each wire label
- One palette, readable by other tools (`schemagen palette`)
- Structured card blocks (`yaml schemagen`) as the start of a part library; markdown tables as fallback
- Continuity tests between reachable terminals only; parallel contacts flagged
- WireViz run as a separate command (GPL-3.0), never imported

**0.3 – 0.5** (see CHANGELOG.md)
- P1.1 neutral data model (Pydantic + JSON Schema), importers (rows, tables, WireViz YAML) and lossless exporters
- P1.3 rules engine with part-library rules; P1.5 label ledger and `schemagen diff`
- P2.1–P2.3 DC operating point, scenarios, fault sweep (transients remain open)
- P3 the app: table editor, object pages, net explorer, clickable drawings, system graph, simulation dashboard,
  issues board, change sets with undo

**0.6** (see CHANGELOG.md)
- Windows support (CI on Ubuntu and Windows), tuple tables in row modules, `sim --infer`, pinout reintegration
  checklist, direction and CAN checks without part data, display names in the app, `docs/citations.md`

**Next (0.7):** readable-sheet importer, Blueprint workspace shell, system canvas, schematic and connector views
with sheet output, import wizard, revisions, desktop packaging spike.

Still open: KiCad netlist import, label-printer / harness-tester / CATIA exporters, zones with route segments and
service loops for lengths, transients, a 2D vehicle map, change-set review/approve, an assistant panel.

## P1: a real tool

1. **Neutral data model** (Pydantic + JSON Schema): `Part` (type, pins, contact data), `Component` (instance, location),
   `Terminal`, `Conductor` (label, gauge, colour, length, from/to terminal), `Splice`, `Bundle`/`Harness`, `Net`
   (computed), `Zone`/`Route`, `Issue`, `Source` (document + page, so every value traces to a datasheet page).
   Importers become adapters onto this model: table, row modules, WireViz YAML, KiCad netlist.
2. **Exporters**: label-printer CSV, continuity sheet as XLSX/PDF with signature boxes, harness-tester pin pairs,
   routing-tool wire list (e.g. CATIA iXF), schematic SVG.
3. **Rules engine**: pluggable rules with severity and fix hints, using the part library: contact AWG range, current
   per contact, pin type compatibility (output↔input, power↔ground).
4. **Lengths**: zones with coordinates plus route segments; wire length = route + service loops; import measured
   lengths later.
5. **Stable IDs and history**: labels never reused once printed; `schemagen diff rev-A rev-B`; tagged releases.

## P2: electrical simulation (the one-shot system test)

1. **DC operating point** per scenario by modified nodal analysis (numpy/scipy).
   - Sources: battery = open-circuit voltage + internal resistance; DC/DC = voltage source with current limit.
   - Wires: R = Ω/m(AWG) × length × temperature factor, plus contact resistance per pin.
   - Breakers/fuses: small resistance while closed. Switches/relays: set per scenario (relay coil drives the contact).
   - Loads from the part library: constant power, constant current or resistive, each with a minimum operating voltage.
   - Outputs: voltage at every load pin, current in every wire and breaker, drop per circuit, % loading of every
     breaker, wire and contact.
2. **Scenarios**, one file each (power-up, battery only, normal operation, charging, converter failure, cold battery):
   switch positions and load states; loads below their minimum voltage are flagged.

   ```yaml
   scenario: master on, ECU on, engine start
   set: {SW-MSTR: ON, CB-ECU: closed, CB-GEN: closed}
   faults: [{short: L05, to: GND}]          # optional: short, open wire, failed source
   expect:
     powered: [ECU, DSP, OTS]
     max_drop_V: {ECU: 0.5}
     no_trip: true
   ```
3. **Fault analysis**: short each node to ground, compute the prospective fault current, and check that the nearest
   upstream breaker trips (trip curve) before the wire's smoke point, that the fault current is within its interrupt
   rating, and that an upstream breaker does not trip first (selectivity).
4. **Transients** (later): inrush of contactors, motors and capacitive loads against trip curves (time-stepped solver
   or ngspice).

Every input is marked measured / datasheet / assumed, and results show which assumptions they rest on. Use it for
design checks, not as certification evidence. Tests: known-answer circuits with hand-calculated results.

## P3: the app

Everything is an object with links; every view is a lens on the same objects. Local-first (project files in git,
SQLite/DuckDB index), because wiring data is often under NDA.

- Table editor with dropdowns from the data model and inline check errors
- Object page per wire / pin / connector / harness: properties, links, source document, issues, history
- Net explorer: click a pin, highlight the net in every drawing and table
- Clickable drawings and system schematics; a 2D vehicle map with zones and routes
- Simulation dashboard: scenario picker, bus voltage tree, breaker loading, failing loads
- Issues board, change sets with review/approve, tagged releases
- Assistant panel that proposes edits as change sets, never directly

## Packaging

- Layout once the model lands: `core/` (model, net, rules, simulation), `importers/`, `exporters/`, `renderers/`,
  `cli/`, `app/`; a JSON Schema for every input format.
- Tests: golden files per exporter, property tests for the net builder, known-answer tests for the simulation.
- PyPI: the name `schemagen` is taken; the distribution is `schema-gen` (checked November 2026), the import package
  and command stay `schemagen`.
