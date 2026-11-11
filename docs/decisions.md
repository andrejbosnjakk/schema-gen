# Decisions

One entry per open choice taken during the 0.2 → 0.5 work: context, choice, why.

## D1. Branch name
- Context: the task asks for `dev/0.5`; the session that did the work may only push to `claude/schema-gen-upgrade-fxrgwk`.
- Choice: all milestones are committed on `claude/schema-gen-upgrade-fxrgwk`; the pull request goes from there to `main`.
- Why: pushing to another branch was not permitted in that session. Rename the branch on merge if wanted.

## D2. Synthetic project format
- Context: M0 needs fictional projects of any size that also run on 0.2 for the baseline.
- Choice: `schemagen synth` writes the 0.2 row-module format (ss??_*.py with `R`, plus `P`, `D`, `O`), labels.json,
  cards with ```yaml schemagen blocks, lengths.csv and scenarios/. Extra keys (`src`, `zone`, `harn`, `prot`, `col`,
  `legacy`) and the P/D/O tables mirror what real lists carry. The exact wire count is reached with structure ground
  straps at the end.
- Why: the same files measure 0.2 and every later version, and exercise the lossless import.

## D3. Synthetic harness halves
- Context: 0.2 guesses connector-half sides from `near_words`.
- Choice: synthetic halves are named after their zones (`Front half`, `Cabin half`) and the sides are given only as
  the explicit `sides:` map that 0.3 reads. 0.2 ignores the map, so its baseline shows the guessing problem
  (every half is "far": 651 false open-end findings on synthetic 1k).
- Why: it reproduces the failure seen on the private list with fictional data.

## D4. Plain column names in the neutral table
- Context: "the workbook a team edits is the neutral table itself, with plain column names"; 0.2 used `p1`, `p1c`, ...
- Choice: the exporter writes plain names (`from`, `from connector`, `from pin`, `from side`, `gauge`, `current_A`,
  `length_m`, `sources`, ...). Importers accept both the plain names and the 0.2 names (and `col`, `color`, `harn`,
  `prot`, `src`), so every 0.2 table still loads.
- Why: readable for a student team, backward compatible for everybody else.

## D5. What "lossless" means for empty values and whitespace
- Context: a spreadsheet cell cannot tell an empty string from a missing key, and table importers strip cells.
- Choice: extras with `None` or an empty/blank string are not stored; text extras are stripped. Non-text extras
  (numbers, lists, dicts, booleans) are written as JSON in a `key:json` column and read back with their type.
  A value in a numeric field that is not a number (`amps: "~3"`) is kept as text in `extra` with a warning.
- Why: nothing that carries information is dropped, and import → export → import is exactly equal (property-tested).

## D6. Resolved fields are stored in the model
- Context: label, name, function class, CAN polarity, palette colour and connector sides are derived from
  labels.json, names.py, the config and the display module.
- Choice: the model stores both the input (`cls`, `colour`, `p1side`...) and the resolved value (`kind`, `can`,
  `colour_code`, `Terminal.side`). The table exporter writes inputs (and label, name); sides are written only when
  they were not guessed, so a guess stays a guess (with its warning) after a round trip.
- Why: every view reads one value, and the round trip stays exact.

## D7. A single CSV holds the wires only
- Context: 0.2 `export -o wires.csv` wrote one CSV.
- Choice: `.csv` still writes only the Wires table, with a warning naming the tables left out; `.xlsx` and a folder
  are the lossless table forms, `.json` the lossless model form.
- Why: backward compatible, and the loss is never silent.

## D8. Rows without an id
- Context: 0.2 skipped any row missing id, p1 or p2 (section headers).
- Choice: a row with no id and not both ends is a section header and is skipped; any other incomplete row is a
  validation error naming file, row and column.
- Why: section headers keep working, a half-filled wire row is no longer dropped silently.

## D9. Protection regions end at buses
- Context: the gauge rule needs the conductors each breaker or fuse protects.
- Choice: a region starts at the device's load-side terminal and follows splices, harness pins, shared device pins
  and switch / relay contacts (from part data); it ends at loads, other protective devices and buses. Feeders from a
  bus bar to a breaker's line side are therefore not checked against the upstream main breaker.
- Why: checking panel feeders against the main breaker would flag every bus-fed breaker; real panels size or
  short-link them separately. A project that wants them checked can model the bus as a splice.

## D10. Edits are change sets applied on load
- Context: the app, `fix direction` and future assistants must edit projects whose source may be Python row modules,
  a CSV, a workbook or a JSON model; edits must be reviewable and git-friendly, with undo.
- Choice: an edit is a JSON change set in `<project>/changes/NNNN-*.json` (set / add / delete by conductor id, with
  the old value). Loading applies them in order; a value that is neither old nor new is a conflict and is reported.
  Undo removes the last file. `fix direction` writes its change set and a diff to `out/changes/` and stores it only
  with `--apply`.
- Why: one mechanism for every source format, nothing is edited silently, and history lives in git.

## D11. CAN direction start
- Context: "CAN in bus order from one terminator end" does not say which end.
- Choice: `direction.can_start` can name the end; otherwise the terminator end that most conductors already agree
  with is used (ties: the first by component id).
- Why: a consistent bus order is what matters for review; the choice that changes fewest rows is the least noisy.

## D12. Rule ids are names
- Context: rules need stable ids for config switches, SARIF and the app.
- Choice: kebab-case names (`gauge-protection`, `can-terminators`) instead of numbers.
- Why: readable in schemagen.yml and in findings, and stable.

## D13. Wires lighter than the protection table
- Context: AC 43.13-1B Table 11-3 stops at 22 AWG.
- Choice: a lighter wire is held to the 22 AWG limit (5 A), and the message says so.
- Why: conservative; a 24 AWG wire on a 10 A breaker must not pass silently.

## D14. Fault sweep: loads as their operating-point resistance
- Context: shorting every node with constant-power loads in a full Newton solve took 57 s on synthetic 1k and did
  not converge for 159 faults (constant-power loads have no physical meaning near 0 V).
- Choice: the sweep linearises the circuit at the scenario's operating point (each load becomes the resistance it
  has there; relays hold their settled state), factorises once, and solves every short as a rank-1 update
  (Sherman–Morrison). Current-limited sources switch to their limit when the short pushes them over it.
- Why: short-circuit practice (IEC 60909) neglects load current; the fault current is set by sources and wiring.
  The sweep now takes 0.6 s on 1k and 13.5 s on 5k. The assumption is listed in every sweep result.

## D15. Current-limit modes change only between converged solves
- Context: with constant-power loads a current-limited DC/DC has two consistent solutions (in limit at low voltage,
  out of limit at nominal voltage); switching modes during Newton locked it into the low one.
- Choice: Newton converges for a fixed set of source modes; only then a source over its limit switches to constant
  current (and back, at most five times). Steps are damped to 2 V per iteration and halved when they reverse.
- Why: it finds the nominal operating point, which is the one a real converter starts into.

## D16. Assumed contact resistance by gauge
- Context: one assumed 5 mΩ per contact made 100 A battery feeds through two harness connectors drop 3 V.
- Choice: without part data, contact resistance is assumed by the gauge it carries (0.3 mΩ for 4 AWG up to 5 mΩ for
  20 AWG and lighter; `sim.contact_resistance_by_awg`), and listed as assumed.
- Why: power contacts are larger; the values are typical orders of magnitude and overridable.

## D17. Synthetic power topology scales with size
- Context: one battery feed and one bus could not supply 1k or 5k projects' loads at all (no DC solution exists).
- Choice: `schemagen synth` creates a 14 V bus (with its own 100 A main breaker from the battery) per 16 breakers,
  a 24 V bus with its own DC/DC per 6 breakers, a relay-control breaker per 18 coils, and parallel battery returns
  (marked `parallel: true`). Battery internal resistance scales with the number of buses.
- Why: a synthetic vehicle should be electrically feasible so the simulation metrics mean something.

## D18. numpy and scipy are core dependencies
- Choice: both (BSD) are installed with schemagen; `schemagen[sim]` remains as an empty extra.
- Why: the app's simulation dashboard needs them, and a second install step is a trap for student teams.

## D19. Voltage drop to a load
- Context: `max_drop_V` needs a reference voltage.
- Choice: drop = voltage of the nearest bus or source terminal upstream of the load's supply pin (breadth-first
  over conductors, breakers and closed contacts) minus the voltage across the load (supply pin minus return pin), so
  the return path counts.
- Why: it is the wiring drop a designer budgets, without needing a source per load.

## D20. System graph with Cytoscape.js and its built-in layouts
- Context: the task suggests "Cytoscape.js or React Flow with ELK layout"; ELK (elkjs) is EPL-2.0, which the licence
  rule does not allow.
- Choice: Cytoscape.js (MIT) with its built-in `cose` layout (`concentric` above 300 nodes). The graph shows buses,
  breakers, sources, controllers and harness connectors by default, every component on request.
- Why: permissive, no extra layout dependency, fast enough for synthetic 5k.

## D21. Licence check scope; MPL-2.0 test tools
- Context: hypothesis (property tests) and axe-core (accessibility tests) are MPL-2.0, and the task requires both.
- Choice: `tools/check_licences.py` checks what ships: the Python install closure of schemagen and the npm
  production dependencies bundled into the frontend. Test-only tools (pytest, hypothesis, ruff, mypy, Playwright,
  axe-core, Vite, TypeScript) are not shipped and are not counted. WireViz (GPL-3.0) is reported as an external command.
- Why: MPL-2.0 is file-level copyleft and nothing of those tools is distributed with schemagen.

## D22. The app loads the whole index once
- Context: cold start ≤ 3 s and net highlight ≤ 100 ms on 5,000 wires.
- Choice: `/api/index` returns every conductor, component, connector, harness, net and finding in one cached,
  gzipped JSON document (2.4 MB raw for 5k); search, pins and net membership are derived in the browser; object pages
  are fetched on demand. The server listens at once and loads the project in a background thread while the browser
  fetches the bundle.
- Why: one round trip, then every interaction is local: net highlight takes 20–30 ms on 5k.

## D23. Built frontend assets are committed
- Context: "the built assets ship inside the wheel, so Node is not needed at runtime"; `pip install -e .` from a
  clone should work too.
- Choice: `frontend/` builds into `schemagen/app/static/` and that output is committed (180 kB gzipped); CI rebuilds
  and fails when the committed output is stale.
- Why: no Node for anyone who only installs or runs schemagen.

## D24. No telemetry, even from the web framework
- Context: FastAPI 0.16x ships OpenTelemetry instrumentation (it exports only when OTLP variables are set).
- Choice: the app passes `telemetry={tracing, metrics, logs, operation_spans: False, auto_configure: False}` and
  excludes every request; the server binds to 127.0.0.1; the frontend loads nothing from the network.
- Why: wiring data is often under NDA; nothing may leave the machine.

## D25. Distribution name `schema-gen`
- Context: release prep asks to check the PyPI name; `schemagen` is taken (another project, version 1.0.5).
- Choice: the distribution is `schema-gen` (free when checked); the import package and the command stay `schemagen`.
- Why: no code or user command changes; only `pip install schema-gen`.

## D26. Package layout and 0.2 import paths
- Choice: code lives in `core/`, `importers/`, `exporters/`, `renderers/`, `sim/`, `app/`, `cli/`; the 0.2 module
  paths remain as one-line re-exports.
- Why: backward compatible for anyone importing schemagen modules directly (the 0.2 tests still do).

## D27. Tutorial edits without sed
- Context: the tutorial changed `wires.csv` with `sed -i`, which Windows does not have; `cmd /c` also runs only the
  first line of a multi-line block.
- Choice: an `<!-- edit: path -->` marker with `old  ->  new` lines (find and replace in any editor; the test applies
  them in Python); the test joins a run block's lines with `&&`, which bash and cmd both understand.
- Why: the tutorial stays tested on both platforms, and a reader on Windows can follow it as written.

## D28. Tuple entries in row-module tables
- Context: row modules may give `P`, `D` and `O` as tuples; 0.5 kept only dicts and dropped the rest silently.
- Choice: tuples are zipped with `tables.<table>.fields` from schemagen.yml (defaults: decisions `id, title, decision,
  rationale, reference`; open items `id, text, owner`; protection `id, rating, panel, loads`). Fields the model has no
  slot for (title, rationale, reference) go to `extra` and so survive export. A tuple longer than the field list, or
  an entry that is neither dict nor tuple, is a load warning naming file, table and index.
- Why: the `tables:` key already holds per-project overrides; `fields` is a key no cited table uses, so the two do
  not collide. A shorter tuple is accepted (the missing fields stay empty).

## D29. Simulating without part data
- Context: without battery, source or load part data `schemagen sim` reported `pass` on an empty circuit.
- Choice: a circuit with no source or no load is not a result: the CLI lists what is missing and exits 2, the report
  shows it and the scenario is not ok. `--infer` (or `sim: {infer: true}`) adds sources for devices matched by
  `sim.sources` (regex -> kind battery/dcdc, v_oc / v_out, r_int / r_out, i_limit; defaults `^BAT` and `^DCDC` in
  core/data/sim.yml); without a voltage the highest nominal bus voltage ("14 V") on the device's conductors is used,
  and only those conductors are its output. A DC/DC's input current is not modelled. Loads come from the conductor
  `current` field, as before. Every inferred value is an "assumed" entry in the report.
- Why: the simplest model that gives an operating point and a non-empty fault sweep from a wire list alone, and it
  never hides that the numbers are assumptions.

## D30. Pinout as a reintegration checklist
- Choice: one row per conductor end, so each conductor is listed exactly twice; splices, buses and harness
  connectors get their own blocks (their ends are listed there). Columns: connector/half, pin, pin name, wire label,
  wire name, gauge, colour, far end (display names, codes where there is none), then empty `connected`,
  `continuity`, `initials`. The far end continues through splices and harness pins only, away from the row's own
  end, and stops at devices, breakers and buses (so a breaker never appears twice and a row never names itself).
- Print: one sheet, each block with its own title and header row, A4 landscape, fit to one page wide;
  `schemagen pinout --page-breaks` starts each component on a new page. Excel repeats only one title-row range per
  sheet, so a block longer than a page does not repeat its header on the next page.
- Why: one sheet is what gets printed and ticked off; one sheet per component would need 200+ tabs on a real list.

## D31. Project hooks get the protection table as written
- Context: D28 turned `P` tuples into dicts, so a project's `display.set_protection(P)` that indexes tuples broke.
- Choice: with row modules, `set_protection` receives the modules' `P` entries unchanged (tuples stay tuples, dicts
  stay dicts); with a table source it receives the rows as dicts, as before. Extra tuple fields stay in the
  protective device's `extra` and so in the export's Protection sheet (a test round-trips ten-field tuples).
- Why: existing display.py files keep working without edits; a table source never had tuples to give.

## D32. Direction rule without pin data
- Context: on a list without part data the rule flagged bonds to structure and returns that run splice → harness →
  ground stud (it took the nearest splice as the return's target), and never judged one-way signals.
- Choice: `direction:` patterns (regex on device code or name), with defaults:
  - `bond` (`\bbond`, `structure`, `airframe`, or conductor class `bond`): no direction, never flagged;
  - `ground_points` (`^GND`, `\bground\b`, `earth`): where a return ends when the net has no ground bus; tried after
    buses and before the supplying unit's ground pin and splices;
  - `senders` (`^SW-`, `switch`, `sensor`, `\bmic`) and `receivers` (`{device: driver, function: low.?side}`) type
    untyped signal ends; a `{device, function}` entry also needs a conductor there whose function text matches.
  Signal wires still without a direction are one `direction-unknown` info finding with the count.
- Why: the smallest set of fallbacks that covers the cases seen, all overridable; a pattern that is wrong for a
  project is replaced in its schemagen.yml rather than in code.

## D33. CAN checks without card data
- Context: without CAN pin data every device on a CAN net was "unknown" and the termination check was skipped, so a
  list without cards got no termination or node-count findings (and terminator plugs counted as nodes).
- Choice: a device without CAN pin data whose code or name matches `tables.can.terminator_pattern` (default
  `^R-CAN|terminator|120 ?(Ω|ohm)`) is a termination; every other device on the net is a node (from its stub
  conductor). The termination check is skipped only when no termination is known at all, since an unknown node may
  be terminated inside; otherwise its fix text says so. `can-part-data` (info) names what was inferred.
- Stub limit: `max_stub_m_by_bitrate` (250 kbit/s: 1 m from SAE J1939-11; 500 kbit/s and above: about 0.3 m, the
  ISO 11898-2 design guideline) at `bitrate_kbit` (default 250), one rate per project; `max_stub_m` set in the
  project still wins.
- Why: a bit rate per project is what real lists state; per-bus rates can come later if a project needs them.

## D34. Display names in the app
- Choice: the app shows a component's display name (from display.py, DISPLAY or the default), with its code in
  brackets when the name does not contain it, in the wire table, object page titles and links, and graph labels.
  The code stays in tooltips and in URLs and `data-pin`, so links and tests do not depend on names. Pin cells that
  may be cut off carry the full text in `title`. The wire table's column chooser is kept per browser
  (localStorage, optional).
- Why: names are what people read; codes are what the data joins on.

## D35. Citation status
- Choice: `docs/citations.md` lists every value in `core/data/` with its clause and a status: *definition* (defined
  constants and formulas) or *to verify* (written from memory of the document, not yet checked against a copy).
  Nothing is marked verified until someone has checked it against the current edition.
- Why: the tool cannot check standards it does not hold; the list makes the check a short, explicit task.

## D36. The readable sheet
- Context: the team's source of truth is a hand-edited sheet with plain device names and free-text connector / pin
  cells; the tool could not read it.
- Choice: a separate importer (`importers/readable.py`, docs/readable.md) that keeps every original cell in the
  conductor's `extra.readable`, so an unedited sheet exports cell for cell; codes are generated from the kind and
  name and registered in the in-memory config (prefixes, harness connectors, sides) so the model builder needs no
  changes. Unparseable cells are a rule finding (`readable-cell`), not a load error, so a half-finished sheet still
  loads. Near-duplicates are a load warning plus `schemagen fix names` (a change set), never merged silently.
- Limits: empty rows and a component header with no wires under it are not written back; a relay coil terminal
  (`coil +` / `coil -`) is typed as a load / return everywhere, not only in readable sheets.
- Why: the sheet stays the team's file; schemagen reads it, checks it and proposes edits as change sets.

## D37. CLI output on Windows pipes
- Choice: when stdout / stderr are not UTF-8 (a Windows pipe is cp1252), characters it cannot encode (→, −) are
  printed as `?` instead of raising UnicodeEncodeError.
- Why: a check that crashes while printing its findings is worse than a `?`.

## D38. An item's interface drawing has all its wires
- Context: interface drawings were a set cover, so each conductor appeared once; a device's grounds were only on the
  ground-bus drawing and its harness wires only on the harness drawing.
- Choice: every device, breaker or bus with a conductor outside the harness drawings gets a drawing with every
  conductor on it; a conductor that is on another drawing too is labelled "(also on X-BH, IF-GNDB)". Splices are only
  drawn for what is still undrawn. Items whose conductors all run through harness drawings get no drawing of their
  own (as before).
- Why: a drawing that misses a device's ground is read as "no ground"; repeating costs a few drawings.

## D39. The workspace shell
- Choice: Blueprint 5 (`@blueprintjs/core`, Apache-2.0) for icons, buttons and hotkeys (`HotkeysProvider`,
  `useHotkeys`; `?` shows the list), not for the tree or the Omnibar: the navigator is plain nested lists with
  `aria-expanded` buttons, and the Omnibar is the existing Ctrl K palette with commands added (after `>`, or when the
  box is empty) so its listbox / option roles and the two-click measurement stay as they were. The page keeps one h1
  (the canvas); panels use h2 / h3. Panel visibility is kept per viewer in localStorage.
- Hotkeys: Ctrl K Omnibar, Alt 1-6 views, `[` navigator, `]` inspector, Shift P problems, Shift T theme.
- Why: Blueprint's Tree and Omnibar would bring their own ARIA patterns to re-check with axe for little gain; the
  bundle stays at a third of its budget.

## D40. Fewer false CAN and direction findings (real readable sheet)
- CAN terminations: a T-piece (`T-piece`, `tee` in the name) is a splice, so a terminator after a chain of T-pieces is
  on the bus the chain carries; a jumper between two pins of one device named like a termination ("CAN termination:
  jumper pin 28 to pin 45") counts as that device's termination.
- Direction: no direction for terminator leads (CAN stubs stay in bus order), loops (`direction.loops`: names with
  loop / E-STOP; `direction.loop_devices`: every conductor on a net with an E-STOP), and jumpers on one device. A
  return that reaches no ground bus or ground point and continues through a harness connector is not judged. When a
  supply (or signal) net has loads (receivers) but no source (sender), only the conductors that reach a load are
  judged: a feed from a bus to an untyped terminal has no known direction.
- Why: each case was a false warning on the real sheet; the seeded fault corpus still finds every flipped conductor.

## D41. System canvas: React Flow and dagre
- Choice: `@xyflow/react` and `@dagrejs/dagre` (both MIT; elkjs is EPL and was ruled out). Edges point from the lower
  power rank to the higher one so dagre lays the system out left to right; the `tight-tree` ranker, because network
  simplex took minutes on the synthetic 5k graph. The React Flow attribution stays visible.
- Limits: the 5k main view has about 98 000 straight-line crossings (hub buses and harness connectors); grouping by
  subsystem or zone is the next step if it is used at that size.

## D42. 1.0: one screen, one idea
- Context: the owner's first real use of the 0.7 app: it felt overloaded and sloppy, drawings failed with a 500, the
  simulation said "pass" with unpowered 14 V buses, the wire table scrolled sideways.
- Choice: the engine stays; the UI is rebuilt around "drop your wire sheet → see the whole system as one diagram →
  see what is wrong → press Simulate". Drawings, simulation, diff and revisions are no longer views: harness drawings,
  pinout and the fault sweep are Export options. The shell, navigator, Omnibar commands and hotkeys leave the default UI.
- Work is split into five streams (A engine and API, B main screen, C design system, D example project and tour,
  E desktop packaging), each in its own git worktree and branch `dev/1.0-<stream>`, merged by the lead into `dev/1.0`.
  The contracts come first: `docs/api.md` (A ↔ B), `docs/design-tokens.md` (C → B), `docs/tour.md` (B ↔ D).
- Why: one clear path a new user can follow in ten minutes matters more than feature count.

## D43a. The logo is black and white (owner's decision)
- Choice: the logo is the owner's bolt mark (`logo_bolt.svg`: a lightning bolt drawn as one wire between two round pin
  nodes), used as given, strictly black and white: near-black `#111418` on light backgrounds, white on dark. The app
  icon is the white mark on a near-black rounded tile (the black mark on a white tile only where a light icon fits
  better). Every icon (.ico, PNG sizes, window, installer, start screen) is generated from that one SVG. The rest of
  the UI keeps its accent colour.

## D60. Design tokens: one accent, cool neutrals, designed dark
- Choice: accent blue `#2f5fd0` (dark `#6d8ff0` with near-black text on it); neutrals are a slightly cool grey ramp
  (light: `--canvas #f6f7f9` under white surfaces; dark: elevation by lightness, `--canvas #111316` < `--bg #17191d` <
  `--surface #1d2025` < `--surface-2 #25282e`). Status colours are darker in light (`#1d7a43`, `#a15c00`, `#c8323c`) so
  they work as text on their soft fills, lifted in dark. Only popups and menus have a shadow.
- Check: `node frontend/src/theme/contrast.mjs` verifies `--text` / `--text-2` ≥ 4.5:1 on every background, the accent
  and on-accent ≥ 4.5:1, and status ≥ 3:1 on soft fills and surfaces, in both themes.

## D61. Inter, bundled
- Choice: `@fontsource-variable/inter` (OFL-1.1), imported by `src/theme/index.ts`; Vite bundles the woff2 files, so no
  font is fetched from the network. `tools/check_licences.py` now allows `OFL` (a font licence that permits bundling
  and redistribution with software). Base 13 px, `cv05` on (a tailed lowercase l, so wire ids like l1 / I1 / 11 read
  apart).

## D62. Base styles, motion and component classes
- Choice: `base.css` (element defaults, one `:focus-visible` ring, thin token-coloured scrollbars, motion classes) and
  `components.css` (`.btn`, `.input`, `.badge`, `.card`, `.dialog`, `.menu`, `.kbd`, `.divider`, `.tooltip`) so screens
  share one look without a component library. Motion animates transform and opacity only (no layout jumps),
  150-200 ms ease-out; `prefers-reduced-motion` turns animations and transitions off.

## D63. Icons are hand-drawn
- Choice: 18 component-kind icons (`KindIcon`) and 25 UI icons (`Icon`), 16 x 16, 1.5 px round strokes in
  `currentColor`, written as SVG paths in `icons.tsx`; no icon library. Electrical kinds follow IEC symbols where one
  fits at 16 px (breaker: switch with a cross, lamp: circle with a cross, motor: M in a circle, ground, fuse).

## D64. Logo and app icons from one SVG
- Choice: `Logo` inlines `logo.svg` (`?raw`) so the mark's `currentColor` follows `--logo` (D43a). `make_icons.py`
  (dev-only, Pillow) reads the polyline, stroke and pin circles from that SVG and draws the white mark on a `#111418`
  rounded tile: `packaging/assets/icon.ico` (16-256) and `icon-16/32/48/256/512.png`, supersampled 8x.
- At 16 and 24 px the wire is drawn 1.45x and 1.25x thicker and the mark fills 80 % of the tile (72 % from 32 px): at
  the original weight the 16 px wire is about one pixel and blurs; thickened it reads as the bolt.

## D65. The 1.0 example: a fictional electric aircraft
- Choice: `examples/aircraft`, the Kestrel E2 demonstrator, 121 wires in the readable layout, with a 14 V main and
  essential bus, two 14 V batteries, a DC-DC converter from a 400 V pack stub, firewall and wing-root connectors, one
  terminated CAN bus, avionics, lights, the motor controller's LV side and sensors. The HV side is a single stub (two
  wires) so the example stays about LV wiring, which is what the rules and the simulation check.
- Why: the tour and a first-time user need a project that looks like theirs (a sheet, not Python wire lists) and is
  small enough to read in one screen; the demo vehicle stays for the 0.2 tests.

## D66. Exactly three deliberate mistakes, everything else clean
- Choice: an undersized wire (W045, 22 AWG on the 10 A landing-light breaker), an oversized breaker (CB-XPDR 15 A on a
  1.5 A transponder, 20 AWG) and a bus with loads and no feed (the cabin bus). Any other finding was fixed in the data,
  not the code; `check` leaves two `gauge-protection` errors and one info (antenna coax has no direction).
- Today `gauge-protection` catches both 1 and 2 (the wire is lighter than the breaker allows); the 1.0 overlay tells
  them apart (wire too small vs breaker oversized). No rule catches 3: the simulation shows the bus at 0 V but `sim`
  still says pass; stream A's overlay flags it. The test pins the ids so the tour texts stay true.

## D67. The example sheet is generated, and byte-reproducible
- Choice: `examples/aircraft/make_sheet.py` writes `wires.xlsx` from rows in the script (openpyxl only); the zip entry
  times and the document's modified time are fixed, so the same rows give the same bytes, and a test checks the
  committed sheet against the script.
- Why: a binary sheet in git is unreviewable; the script is the reviewable source, the xlsx is what users open.

## D68. Example card data: only what the simulation needs
- Choice: cards for sources (v_oc / v_out, r_int), a generic SPST card for every `SW-` switch, the battery contactor's
  coil and contacts, constant-power loads with v_min for the avionics, motor controller and BMS, and CAN pin types
  (terminations as `kind: terminator`). Lights, pump and cabin loads stay as currents from the sheet (assumed). Signal,
  RF and sensor-supply rows have no current, so the simulation does not read sensors and antennas as loads.
- Why: without switch and contactor cards the simulation sees open circuits; without the rest it still runs.

## D69. Tour steps follow the example's findings
- Choice: eight steps (diagram, a component card, its contents, Issues, Wires, Simulate, + Source, Import), each naming
  the real finding it shows (W045, CB-XPDR, the 0 V cabin bus) instead of generic help; listed in docs/tour.md.
- Why: a tour that points at a real mistake teaches what the tool is for in the first minute.

## D70. Desktop app: pywebview window around the local server
- Choice: `schemagen/desktop.py` starts uvicorn on a free 127.0.0.1 port in a thread, waits for `/api/health`, opens a
  pywebview window titled "schemagen" (maximised, minimum 1280 × 720, black-and-white bolt icon), and stops the server
  when the window closes. pywebview (BSD-3-Clause) uses the WebView2 runtime that ships with Windows 10/11, so nothing
  else is installed and no browser tab opens. Logs go to `%LOCALAPPDATA%\schemagen\logs\schemagen.log`
  (`SCHEMAGEN_HOME` overrides the folder); a startup failure is a native error dialog that names the log.
- Without a project argument it uses the server's start screen when `create_app(None)` is accepted; until then it
  copies the bundled example to `%LOCALAPPDATA%\schemagen\projects\Example aircraft` and opens that copy. It sets
  `SCHEMAGEN_EXAMPLE` to the bundled example. Web storage persists in `%LOCALAPPDATA%\schemagen\webview`.
- Why: the owner's users are not programmers: double-click, a window, no terminal, no Python or Node.

## D71. PyInstaller onedir, Python 3.14
- Choice: one onedir bundle (`packaging/schemagen.spec`), windowed, no UPX. Onefile would unpack about 130 MB to %TEMP%
  on every start (seconds, and antivirus scans each time); onedir starts in about 2 s and the installer compresses it
  anyway (132 MB on disk, 42 MB installer). Built with Python 3.14 (pythonnet 3.2 and cffi have 3.14 wheels).
- Bundled: `schemagen/app/static`, `schemagen/core/data`, `schemagen/templates`, `examples/aircraft` (else
  `examples/demo`), `packaging/assets/icon*`. Excluded: `wireviz`, the `graphviz` Python package and Pillow (only
  WireViz needs them), tkinter, test tools, and pywebview's non-Windows back ends.
- `packaging/third_party.py` writes `THIRD_PARTY.txt` from what PyInstaller actually bundled (its TOC files), with the
  licence texts, and fails the build on a non-permissive package or on WireViz.

## D72. No Graphviz or WireViz in the installer
- WireViz is GPL-3.0: schemagen only runs it as a command and it never ships in the bundle. Graphviz is EPL-1.0, a weak copyleft
  licence, not on the permissive list for anything that ships; its Windows build also carries LGPL libraries (cairo,
  pango, glib). Shipping unmodified binaries would be legal with a source offer, but it fails the permissive-only rule,
  and it would not help: without WireViz there is nothing to call `dot`.
- Behaviour in the installed app: the main diagram, checks, simulation, pinout, wire list and fault sweep need neither.
  Harness drawings run the `wireviz` command if it is on PATH (a user who installs Graphviz and `pip install
  wireviz==0.4.1`); otherwise the export answers `graphviz-missing` with a plain sentence. No runtime download.

## D73. Per-user Inno Setup installer
- Choice: `packaging/installer.iss`: no admin (`PrivilegesRequired=lowest`), installs into
  `%LOCALAPPDATA%\Programs\schemagen`, Start-menu entry and a desktop shortcut (checked by default), MIT licence page,
  `LICENSE.txt` and `THIRD_PARTY.txt` in the install folder, uninstaller in Apps & features. An upgrade deletes the old
  `_internal` first. User data lives in `%LOCALAPPDATA%\schemagen` and survives uninstall.
- Why: a university or company laptop often has no admin rights; Inno Setup is free and scriptable on CI.

## D74. One build command and a CI installer
- `packaging/build.ps1`: frontend (if npm), the build venv `packaging/.venv` (pinned pywebview and PyInstaller in
  `packaging/requirements.txt`), PyInstaller, the notices, then Inno Setup if `iscc` is found →
  `packaging/dist/schemagen-setup-<version>.exe`. `packaging/smoke.ps1` starts the built exe with a fresh
  `SCHEMAGEN_HOME`, checks `/api/health` and the "schemagen" window, closes it and checks the server stopped.
- `.github/workflows/installer.yml` runs both on `windows-latest` for pushes to `dev/1.0*` and tags `v*`, and uploads the
  installer as an artifact. The installer is not code-signed yet: SmartScreen shows "unknown publisher" on first run.
## D43. Drawings fail loudly and clean up
- Choice: Graphviz `dot` is found on PATH, `SCHEMAGEN_DOT` or the usual install folders; a missing one is the plain
  `graphviz-missing` error, WireViz's own stderr is surfaced on a failed render, and `.tmp` files are always removed.
- Why: a silent empty drawing folder looked like a bug in the tool.

## D44. Never a pass while a bus with loads is unpowered
- Choice: the simulation walks from sources through wires, breakers and closed contacts; a bus with loads that no source
  reaches reads 0 V and the run is not a pass. Not a `check` rule: the demo has a fed-from-nowhere bus on purpose, and
  D66 pins the example's findings; the overlay and `sim` carry it.
- Why: a floating return drop (about 14 V) made an unfed bus look healthy.

## D45. One definition of a source
- Choice: `Ctx.is_source` (battery or DC/DC by kind, part data, else the `sim.sources` names minus `sim.not_sources`:
  battery management systems, chargers, sensors) is used by the workspace rank and the simulation.
- Why: the rank and the simulation disagreed about what a source is.

## D46. Errors are one shape, causes go to a log
- Choice: every non-2xx answer is `{error: {code, message, retry}}`; global handlers turn any exception into `internal`
  and write the traceback to `<user data>/logs/schemagen.log` (rotating, 1 MB x 3). The user data root is
  `SCHEMAGEN_HOME`, else `%LOCALAPPDATA%\schemagen`, else `~/.local/state/schemagen`.
- Why: the frontend shows a sentence and a Retry button; a traceback helps nobody there.

## D47. The app may start with no project
- Choice: `schemagen app` without a project serves the start screen; settings (tour, theme, recent) live in
  `settings.json` under the user data root; the example is copied once to `projects/Example aircraft` and the copy is
  opened (located by `SCHEMAGEN_EXAMPLE`, `sys._MEIPASS`, then the repository); an uploaded sheet gets its own project
  folder. `python-multipart` (Apache-2.0) reads the upload.
- Why: the install folder is read-only, and edits are change sets in the project folder.

## D48. The overlay says why, in one line, per object
- Choice: `sim/overlay.py` judges wires against the protection table (too small for its breaker or current: error;
  3 or more gauges heavier than needed: warn), breakers (too big for the wire: error; over the rating: error; trips;
  80 % loading: warn) and buses (no source: error). W045, CB-XPDR and the cabin bus come out as three different texts.
- Why: `gauge-protection` reports one finding for two different mistakes; the fix differs.

## D49. Sources added in the app are change sets
- Choice: `POST /api/sources` and `DELETE /api/sources/{id}` write `add-source` / `delete-source` ops; the simulation
  reads them with the project's own sources, and they show as rank-0 components. Positions are view state in
  `<project>/layout.json`, not a change set. Export writes under `<project>/out/`.
- Why: a what-if source survives a reload, is undoable, and never rewrites the input sheet.
## D50. Start screen: one choice, no project list as the headline
- Choice: with no project open the screen shows the logo, "Open the example project" (the only primary button), a drop zone
  ("Import your wire sheet", .xlsx or .csv, click or drop) and the recent projects below, quiet.
- Why: a new user has two paths, the example or their own sheet; recent projects are for people who came back.

## D51. A sheet can be dropped anywhere
- Choice: dragging a file over the window shows a full-window overlay; dropping imports it, from the start screen or the
  main screen. A short bar (uploading, then reading) shows progress; diagram, wire list and Issues replace their
  skeletons at once, with no extra clicks.
- Why: the owner's workflow is "drop the sheet and look". Import problems (unreadable cells, skipped rows) are Issues
  from the server, never a modal; only a file that cannot be imported at all is a message with Retry.

## D52. The top bar holds six things
- Choice: logo, project name, Import, Export (Harness drawings, Pinout, Fault sweep, Wire list), Simulate (primary),
  light/dark toggle, a help menu with "Replay the tour". Nothing else, no hotkeys.
- Why: everything else is reachable by clicking an object; fewer controls means fewer decisions.

## D53. One fetch wrapper, plain errors
- Choice: `src/api.ts` is the only place that calls the server. GETs retry three times with backoff when the error says
  `retry`; errors are read from `{"error": {code, message, retry}}`; the UI shows the message and, if retryable, a Retry
  button. "500" and "Failed to fetch" never reach a person. The same module can route to an in-memory server (`src/mock`)
  for the e2e tests and development (`?mock=1`).
- Why: the 0.7 app showed raw status codes; and a mock lets the screens be built and tested before the engine API exists.

## D54. The block diagram: bundles, not wires
- Choice: one React Flow canvas. A component is a card (icon, short name, kind and pin count, status dot, full name in the
  title attribute). All wires between the same two components are one bundle, coloured by class, labelled "3 × 14 V".
  Nodes and edges are memoised and only visible elements render, so 1,000 wires pan smoothly.
- Why: a drawing with one line per wire is unreadable at this size; bundles keep it a diagram of the system.

## D55. Edge labels never overlap
- Choice: a collision pass places each bundle's label on the first free spot of its curve (largest bundles first, cards
  count as obstacles) and hides it when none is free; labels are also hidden below 55 % zoom and shown on hover or when
  the bundle is highlighted.
- Why: overlapping labels were the most visible sloppiness in the 0.7 canvas.

## D56. Layout: power flow left to right, zones as blocks
- Choice: `diagram/layout.ts` places cards in columns by `Node.rank` (sources left, loads right), each zone as a soft
  background block with a label, blocks stacked and wrapped to fit a wide screen, cards ordered by barycentre to reduce
  crossings. It does not use dagre (not a dependency any more): zones and a screen-shaped aspect ratio were the
  requirements dagre does not give. Dragged positions are saved with a debounced `POST /api/positions` and win over the
  automatic layout when restored.
- Why: the zone structure is what the owner reads; a general graph layout loses it.

## D57. Issues: sentences, grouped, clickable
- Choice: the left Issues panel groups findings by severity with counts, each as a plain sentence (title, then the
  message in two lines at most). A click zooms the diagram to the object (animated) and pulses it with `.anim-pulse`.
  The panel collapses to a chip.

## D58. The Wires drawer fits 1366 px
- Choice: bottom drawer, collapsible, at most seven columns (label, name, from, to, gauge, voltage, current) in a grid
  that wraps text instead of scrolling sideways, virtualised with `@tanstack/react-virtual`, with a filter box. A row
  click highlights its bundle and the two cards (and zooms to them).
- Why: the 0.7 table scrolled sideways; a wire list is something you scan.

## D59. Feel and acceptance
- Choice: 13 px Inter, 8 px grid, 1 px borders, 6 px radius, shadows only on popups, skeletons instead of blank areas,
  150 to 200 ms transforms and opacity only. The theme comes only from `src/theme` (tokens and component classes); small
  text uses `--text-2` because `--text-3` fails 4.5:1 on dark. Playwright e2e (with axe, no serious violations), at
  1366x768 and 1920x1080 in both themes, are the acceptance tests for steps 1 to 3.

## D75. The overlay counts root causes and judges wires against their protector
- Choice: `summary.problems` is the number of `summary.groups`, one per root cause: a wire and the breaker it does not
  fit are one group (W045 with CB-LANDING-LT), loads unpowered only because their bus has no source fold into that
  bus's group (their items stay `error`, "no supply: Cabin bus has no source"), a trip is its own group. The text is
  "N problems, M trips" plus ", K unpowered bus(es)" only when K > 0; the unpowered bus is also one of the N problems.
  "Far heavier than needed" (warn only) means: a protected wire whose gauge two steps thinner is still allowed for its
  breaker or fuse by `protection.yml`; an unprotected wire is compared with its current times `heavy_margin`
  (`core/data/sim.yml`, 25, a design default: no standard gives it, and a feeder is sized for drop and faults).
  `oversize_steps` is gone.
- Why: the aircraft example has three mistakes and said "20 problems"; 10 AWG on a 30 A breaker is correct, a wire is
  sized for its protection, not its load. Supersedes the wire-warn rule in D48.
