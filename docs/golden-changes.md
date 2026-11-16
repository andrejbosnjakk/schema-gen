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

## 1.1 drawing engine (stream C)

| file | difference | why |
|---|---|---|
| docs/screens/drawings/*.svg (new) | the six reference drawings, compared byte for byte by tests/test_drawing_reference.py | regenerate with `python -m schemagen.drawing.reference` or `UPDATE_GOLDEN=1 pytest tests/test_drawing_reference.py`; change them only with a reason listed here |
| symbol-sheet.svg / .pdf | terminator drawn upright, flag `side`, battery with both leads on one side | symbols needed by the layout |

## Readable drawings, stage 1 (pagination and use of the sheet)

| file | difference | why |
|---|---|---|
| docs/screens/drawings/*.svg, *.pdf | sheets are cut between columns by what fits (the scope's components first), rows stretched up to 2x and channels widened to use the sheet; fewer, fuller sheets (aircraft components: 115 -> 94 sheets) | a sheet is split only when the content does not fit; no near-empty sheets |
| same | a block's name is left out when it only repeats the code (`BATTERY-MANAGEMENT-SYSTEM` / "Battery management system"); the same in flag texts | the repeat made blocks and flags needlessly wide |
| same | flag text wraps at 60 mm (72 mm only when it would be cut off) | narrower flags, more fits on one sheet |
| same | a bus or ground in scope has no "+ N more wires" flag | every wire of the part the sheet is about is drawn |

## Readable drawings, stage 2 (wire table, colour, words)

| file | difference | why |
|---|---|---|
| docs/screens/drawings/*.svg, *.pdf | wire table under the drawing (or on a table sheet), wire text `W052 20 AWG BK`, wires in colour, worked key and colour codes in the notes, flags `to ...` / `continues on sheet N: ...`, dashed leads on unwired terminals of parts, summary flag `+ N more wires on X`, harness name without the repeated code | part 1 and 2 of the readable-drawings brief (D114) |
| symbol-sheet-3.svg (new), symbol-sheet.pdf | third page `How to read these drawings` | part 3 of the brief |

## Drawing defects found on a real project

| file | difference | why |
|---|---|---|
| docs/screens/drawings/*.svg, *.pdf | wire casing 0.4 mm wider than the colour core (core centred at any zoom); a wire with both ends on one part is two off-sheet flags | the coloured line looked doubled on screen; such wires were drawn through the block |
