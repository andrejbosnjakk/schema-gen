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
