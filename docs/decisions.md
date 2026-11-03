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
