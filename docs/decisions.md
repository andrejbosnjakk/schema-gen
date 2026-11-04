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
