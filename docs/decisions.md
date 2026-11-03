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
