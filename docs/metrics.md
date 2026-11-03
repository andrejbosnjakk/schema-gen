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
