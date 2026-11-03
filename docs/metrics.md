# Metrics

Measured in the development container (4 vCPU, Python 3.13). Benchmarks: `python benchmarks/bench.py`
(synthetic projects from `schemagen synth --seed 1`). CI runners are slower; CI checks the limits with a margin.

## M0: 0.2 baseline (before any change)

| project | wires | load (s) | net (s) | checks (s) | draw, no render (s) | render (s) | findings |
|---|---:|---:|---:|---:|---:|---:|---:|
| demo | 23 | 0.001 | 0.000 | 0.001 | 0.014 | 0.426 | 1 |
| synthetic 1k | 1000 | 0.056 | 0.006 | 0.226 | 0.677 | 14.98 | 651 |
| synthetic 5k | 5000 | 0.275 | 0.051 | 5.475 | 9.845 | – | 3234 |

- Tests: 16 in one file, statement coverage 95 % (618 statements; `cli.py` 64 %).
- Conductors in a drawing: demo 16/23 (70 %), synthetic 1k 568/1000 (57 %).
- Neutral export drops every key outside the 16 neutral fields: on synthetic 1k `src`, `zone`, `harn`, `prot`, `col`,
  `legacy` and the `P`, `D`, `O` tables.
- Findings on synthetic 1k (0.2 checks): 651, nearly all false (open ends from guessed halves).

## M1 (0.3): typed, lossless core model

| metric | target | measured |
|---|---|---|
| round trip import → export → import (model equality) | identical on demo, synthetic 1k, 5k | identical: demo (xlsx, CSV folder, JSON), 1k (xlsx, CSV folder, JSON), 5k (CSV folder, JSON) |
| property test (hypothesis) | ≥ 200 examples | 200 examples, each through CSV folder, JSON and XLSX |
| unknown keys survive export | zero silent drops | test feeds `route`, `legacy`, `under`, `dom` + P/D/O extras; all in the workbook and the model |
| validation errors name file, row, column | yes | e.g. `w.csv, row 4, column 'to side': side must be near or far, not 'left'` |
| load + net, 5,000 wires | ≤ 2.0 s | 0.66 s (load 0.62 s, net 0.03 s) |
| demo outputs vs golden files | unchanged | identical: X-BH.yml, cut list, continuity sheet, checks, index.html |
| findings on synthetic 1k (0.2 checks with explicit sides) | – | 0 (0.2 guessing: 651) |

Benchmark after M1 (`python benchmarks/bench.py --no-sim`):

| project | wires | load (s) | net (s) | checks (s) | draw, no render (s) |
|---|---:|---:|---:|---:|---:|
| demo | 23 | 0.003 | 0.000 | 0.001 | 0.016 |
| synthetic 1k | 1000 | 0.128 | 0.003 | 0.099 | 0.701 |
| synthetic 5k | 5000 | 0.624 | 0.034 | 2.589 | 5.934 |

Load is slower than 0.2 (0.28 s → 0.62 s on 5k) because it now validates and derives the whole model; checks and
draw are faster because the net no longer scans every node per query. Tests: 36, statement coverage 94 %.

## M2 (0.3): rules engine and views

| metric | target | measured |
|---|---|---|
| seeded-fault corpus recall | 100 %, ≥ 30 faults, ≥ 12 rule types | 100 %: 43 of 43 faults across 24 rules (`tests/test_rules.py::test_seeded_fault_corpus_recall`) |
| false positives on the clean demo | 0 | 0: three findings, all from the demo's one open item (O-01: generator field pin TBD) |
| false positives on clean synthetic 1k | 0 | 0: one finding, the project's open item O-001 |
| conductor coverage in rendered views | 100 % on demo and synthetic 1k | demo 23/23 (1 harness + 5 interface drawings); synthetic 1k 1000/1000 (24 harness + 91 interface drawings, all rendered: 115 SVGs in 8.0 s) |
| diff finds seeded edits | 100 % of ≥ 25 | 100 % of 33 (conductors added/removed/changed, labels, pins, protection, open items), plus a git-revision test |
| direction fix on a seeded project | 0 direction findings, no label changes | 0 findings after the change set; labels identical (40 random flips seeded) |

Rules on synthetic 5k: 0.22 s. `schemagen check` formats: text, JSON, SARIF 2.1.0 (with file and row of the
conductor). The rule run found real errors in the demo (CB-GEN 10 A on 20 AWG, ECU ground written backwards) and in
the first synthetic generator (fuses sized from the breaker column); both were fixed, see docs/golden-changes.md.

Benchmark after M2 (`python benchmarks/bench.py --no-sim`):

| project | wires | load (s) | net (s) | checks / rules (s) | draw, no render (s) |
|---|---:|---:|---:|---:|---:|
| demo | 23 | 0.006 | 0.000 | 0.001 | 0.025 |
| synthetic 1k | 1000 | 0.127 | 0.003 | 0.035 | 0.890 |
| synthetic 5k | 5000 | 0.516 | 0.018 | 0.224 | 8.042 |

Draw now also builds the interface drawings (5k: about 450 of them), so it is slower than after M1.
