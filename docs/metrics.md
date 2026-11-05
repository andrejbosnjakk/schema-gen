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

## M3 (0.4): DC simulation

| metric | target | measured |
|---|---|---|
| known-answer tests vs hand calculations | ≥ 15, error ≤ 0.1 % or ≤ 1 mV / 1 mA | 19 (`tests/test_sim.py`): divider, battery + R_int + load, parallel wires, AWG resistance (20 °C and 60 °C), constant-power Newton (2), constant current, current-limited source (in and out of limit), DC/DC input power, relay pick-up / open / below pick-up / oscillation, trip-curve interpolation, project operating point, fault current and trip, selectivity, wire I²t |
| Kirchhoff current residual | ≤ 1e-9 A at every node | ≤ 9e-11 A on every synthetic scenario (1k, 5k); ≤ 2e-12 A on the demo |
| Newton iterations | ≤ 50 on every synthetic scenario | 8–10 (synthetic 1k and 5k, both scenarios) |
| operating point, synthetic 1k | ≤ 200 ms | 102 ms |
| operating point, synthetic 5k | ≤ 2 s | 0.55 s |
| full fault sweep, synthetic 1k | ≤ 30 s | 0.55 s (766 nodes); 5k: 13.5 s (3,619 nodes) |
| ngspice cross-check | ≥ 3 circuits within 0.5 % | 3 circuits (constant-power, constant-current and resistive loads), all node voltages within 0.5 % (they agree to 1e-6) |

The fault sweep on synthetic 1k reports, as design findings: battery feeds before the main breakers are not cleared
(unprotected section), and short 22 AWG feeders from a bus bar to small breakers are protected only by the 100 A main
breaker and would not survive a short at the breaker's line side (I²t). Both are true for the generated design.

Benchmark after M3 (`python benchmarks/bench.py`):

| project | wires | load (s) | net (s) | rules (s) | draw, no render (s) | sim op (s) | fault sweep (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| demo | 23 | 0.006 | 0.000 | 0.001 | 0.027 | 0.002 | 0.004 |
| synthetic 1k | 1000 | 0.138 | 0.003 | 0.036 | 1.259 | 0.102 | 0.554 |
| synthetic 5k | 5000 | 0.504 | 0.017 | 0.210 | 9.419 | 0.550 | 13.509 |

## M4 (0.5 alpha): the app

| metric | target | measured |
|---|---|---|
| Playwright end-to-end flows (Chromium) | ≥ 10, green | 14 tests green: search, open object, edit and save, undo (two ways), net highlight, run scenario (and fault sweep), open drawing (click a wire label), fix direction preview + apply, diff view, issues filter; plus the metric tests below |
| cold start to interactive, synthetic 5k | ≤ 3 s | 2.0 s (process start to the first table row and a working filter) |
| net highlight, synthetic 5k | ≤ 100 ms | 28 ms worst of 5 (to the second animation frame after the click) |
| every object type within 2 clicks of search | yes | conductor, pin, component, harness connector, harness, net, part: 2 (open search, click the result) |
| frontend bundle | ≤ 2 MB gzipped | 183 kB gzipped (181 kB JS + 2 kB CSS) |
| axe-core: serious or critical violations | 0 on the main pages | 0 on 8 pages (table, wire page, pin page, issues, graph, simulation, diff, drawings) in light and dark |

API tests without a browser: `tests/test_app.py` (11). Runtime dependencies (licence check): 19 Python and 8 npm, all permissive.

## M5 (0.5): packaging and release prep

| item | state |
|---|---|
| layout `core/`, `importers/`, `exporters/`, `renderers/`, `sim/`, `app/`, `cli/` | done; 0.2 module paths kept as re-exports (all 0.2 tests unchanged and green) |
| CI wheel job: build, `pipx install` in a clean environment, `schemagen app examples/demo`, Playwright smoke test | in `.github/workflows/ci.yml` (job `wheel`); run locally: wheel built, installed with pipx into an empty venv, smoke test green |
| `docs/tutorial.md` | from an empty folder to a checked, drawn, simulated project and the app; every file and command in it is run by `tests/test_tutorial.py` |
| release prep | version 0.5.0, CHANGELOG.md, roadmap updated; PyPI name `schemagen` is taken, distribution renamed `schema-gen` (D25) |
| licence check | 19 Python and 8 npm runtime dependencies, all permissive; WireViz reported as an external command |

## Summary after 0.5 (same container)

| | 0.2 | 0.5 |
|---|---|---|
| package code | 905 lines, 618 statements | 4,358 statements (Python) + 1,100 lines TypeScript |
| tests | 16, one file, 95 % coverage | 88 Python tests (incl. 200-example property test, 43-fault corpus, 19 known-answer circuits, tutorial) at 95 % statement coverage; 14 Playwright end-to-end tests + 1 wheel smoke test |
| conductors in a rendered view, synthetic 1k | 57 % | 100 % (1000/1000) |
| findings on clean synthetic 1k | 651 (nearly all false) | 1 (its open item) |
| keys lost on export | all extras and the P/D/O tables | none (round trip exact) |

Final benchmark (`python benchmarks/bench.py`, seconds):

| project | wires | load | net | rules | draw (no render) | sim op | fault sweep |
|---|---:|---:|---:|---:|---:|---:|---:|
| demo | 23 | 0.007 | 0.000 | 0.001 | 0.029 | 0.003 | 0.009 |
| synthetic 1k | 1000 | 0.135 | 0.003 | 0.039 | 1.058 | 0.111 | 0.464 |
| synthetic 5k | 5000 | 0.507 | 0.016 | 0.228 | 9.629 | 0.604 | 11.830 |

Rendering every drawing of synthetic 1k with WireViz (115 drawings, 4 parallel processes): 8.0 s (0.2: 15.0 s for
24 harness drawings covering 57 % of the conductors).

## 0.6: fixes from a real project, Windows

Measured on a Windows 11 laptop (Python 3.14), and in CI on Ubuntu and Windows.

| metric | target | measured | pass |
|---|---|---|---|
| `pytest -q` on Windows and Ubuntu (CI) | 0 failures, no new skips | 96 passed, 2 skipped locally; CI green on ubuntu-latest and windows-latest × 3.12, 3.14 | yes |
| text I/O without an encoding | 0 | 0 (AST check over `schemagen/` and `tests/`) | yes |
| tuple tables survive import → export → import | lossless, nothing dropped silently | decisions, open items and ten-field protection tuples round-trip (CSV, XLSX); unreadable entries are warnings | yes |
| sim without part data | not a pass | exit 2 with what is missing; synthetic 1k without cards + `--infer`: operating point, fault sweep 426 nodes | yes |
| pinout: each conductor listed exactly twice, no self-references | yes | demo and synthetic 600: every conductor twice, 0 self-references; golden test for the XLSX layout and print setup | yes |
| direction rule on the seeded no-pin-data corpus | 0 false positives, 100 % recall, unknown counted | 0 false positives (0.5: 3), 9/9 flips caught, unknown count reported | yes |
| CAN on synthetic 1k without cards | termination and node-count findings | node counts equal to the carded project; a cut terminator is an error; stub limit 1 m / 0.3 m by bit rate | yes |
| display name shown where display.py gives one (Playwright) | yes | wire table and object page show "Cockpit display (DSP)" | yes |
| Playwright end-to-end | 15/15 | CI (Ubuntu, Windows): all green. Locally 14/15: the drawing test passes with Graphviz; the cold-start test measured 3.4–3.9 s (limit 3 s) on a laptop running on battery | partly |
| cited values listed with clause and status | all | 17 values in `docs/citations.md`: 5 definition, 11 to verify, 1 naming pattern | yes |
