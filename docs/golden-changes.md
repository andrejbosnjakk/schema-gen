# Changes to the demo golden files

The golden files in `tests/golden/demo/` were taken from 0.2 before any code change. M1 (typed model) reproduced
them byte for byte. Every later difference is listed here with its reason.

## M2 (rules and views)

| file | difference | why |
|---|---|---|
| X-BH.yml | DSP pin labels `Sensor supply` / `Oil temperature signal` → `SENS 5V` / `AI1 oil temp` | the demo gained a DSP card (pin types, CAN termination), so the card's pin names are used, as for the ECU |
| X-BH.yml, cut list, continuity sheet | `CB-GEN 10 A` → `CB-GEN 7.5 A` | the gauge rule (AC 43.13-1B Table 11-3) found a real error in the demo: 20 AWG may be protected by at most 7.5 A |
| cut list | L11 and L12 run device → ground bus (from and to swapped) | the direction rule found the demo's ECU ground written ground bus → device; fixed with `schemagen fix direction`, labels unchanged |
| index.html | five interface drawings (IF-BAT, IF-CB-ECU, IF-CB-GEN, IF-CB-MAIN, IF-ECU) | 7 demo conductors were in no drawing; every conductor is now in at least one |
| wires.csv | plain column names and the new columns (sides, sources, ...) | M1 neutral table (D4 in decisions.md) |

The demo also gained P (ratings, panel labels), D and O tables.
