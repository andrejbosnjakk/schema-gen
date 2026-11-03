# Tutorial: from an empty folder to a checked, simulated wiring design

This walks a small team through one project end to end: a battery, a main breaker, a bus bar, a switched tail lamp
behind a bulkhead connector, and the ground returns. Everything here is fictional. Every file below is written
exactly as shown, and every command is run by `tests/test_tutorial.py`, so the tutorial stays true.

You need Python 3.10 or newer. Drawings also need Graphviz (`sudo apt-get install graphviz`, `brew install graphviz`).

```bash
pip install schema-gen         # the command is `schemagen`; from a clone: pip install -e .
schemagen --version
```

## 1. The project folder

A project is a folder with a `schemagen.yml` and a wire list. Make a folder `tail-lamp/` and put this in
`tail-lamp/schemagen.yml`:

<!-- file: schemagen.yml -->
```yaml
# Tail lamp demo (fictional). Paths are relative to this file.
source: {path: wires.csv}         # the wire list: one row per conductor
buses: [GNDB, BB1]                # device codes that are one electrical node
breaker_prefixes: [CB-]
switch_prefixes: [SW-]
harnesses:                        # harness connectors: prefix -> [name, code, far side]
  X-1: [Bulkhead X-1, X-1, rear]
sides:                            # which half is drawn on the left (near) and right (far)
  X-1: {Front half: near, Rear half: far}
```

Device strings start with a code (`CB-2`, `SW-1`, `X-1`, `GNDB`); the rest of the string is free text. Codes with the
prefixes above become breakers, switches and harness connectors; `buses` are single nodes; everything else is a device.

## 2. The wire list

The wire list is a table with plain column names. A spreadsheet works just as well (step 7 makes one with dropdowns);
here it is a CSV, `tail-lamp/wires.csv`:

<!-- file: wires.csv -->
```csv
id,label,from,from connector,from pin,to,to connector,to pin,function,bus,gauge,length_m
W1,L01,BAT battery 12 V,+,,CB-1 15 A,LINE,,Battery feed,14 V,12,0.5
W2,L02,CB-1 15 A,LOAD,,BB1 bus bar,Stud,,Bus feed,14 V,12,0.3
W3,L03,BB1 bus bar,Stud,,CB-2 10 A,LINE,,Lamp breaker feed,14 V,20,0.2
W4,L04,CB-2 10 A,LOAD,,SW-1 lamp switch,C,IN,Tail lamp,14 V,22,1.0
W5,L05,SW-1 lamp switch,C,OUT,X-1 bulkhead,Front half,1,Tail lamp,14 V,22,1.5
W6,L06,X-1 bulkhead,Rear half,1,LP-1 tail lamp,P1,1,Tail lamp,14 V,22,3.0
W7,L07,LP-1 tail lamp,P1,2,X-1 bulkhead,Rear half,2,Tail lamp return,GND,22,3.0
W8,L08,X-1 bulkhead,Front half,2,GNDB ground bus,Stud,,Tail lamp return,GND,22,1.5
W9,L09,BAT battery 12 V,-,,GNDB ground bus,Stud,,Battery return,GND,12,0.5
```

Each row is one physical conductor, from one terminal (device, connector, pin) to another. The bulkhead connector `X-1`
has two halves; a pin wired on one half must also be wired on the other.

## 3. Part data

Parts live in markdown "cards", one per part, with a fenced `yaml schemagen` block. The checks and the simulation read
pin types, contact ranges, sources and loads from them. Make `tail-lamp/cards/` with three cards:

<!-- file: cards/battery.md -->
````markdown
# Battery (fictional)

```yaml schemagen
device: '^BAT$'
part: demo battery 12 V
kind: battery
source: {v_oc: 12.8, r_int: 0.02}
connectors:
  - {id: "+", match: '^\+$', type: power_out}
  - {id: "-", match: '^-$', type: ground}
```
````

<!-- file: cards/switch.md -->
````markdown
# Lamp switch (fictional)

```yaml schemagen
device: '^SW-1$'
part: demo toggle switch
kind: switch
contacts: [{a: C.IN, b: C.OUT}]
connectors:
  - id: C
    match: '^C$'
    pins:
      - {n: IN, type: power_in, i_max: 10, awg: [16, 22]}
      - {n: OUT, type: power_out, i_max: 10, awg: [16, 22]}
```
````

<!-- file: cards/lamp.md -->
````markdown
# Tail lamp (fictional)

```yaml schemagen
device: '^LP-1$'
part: demo tail lamp 21 W
kind: load
load: {model: constant_power, p_w: 21, v_min: 9}
connectors:
  - id: P1
    match: '^P1$'
    pins:
      - {n: 1, name: SUPPLY, type: power_in, i_max: 5, awg: [18, 22], required: true}
      - {n: 2, name: GND, type: ground, i_max: 5, awg: [18, 22], required: true}
```
````

## 4. Check it

<!-- run: expect-fail -->
```bash
schemagen check .
```

It finds one error and exits with status 1:

```
error   gauge-protection   L04: 22 AWG is protected by CB-2 10 A; at most 5 A per FAA AC 43.13-1B, Table 11-3 ...
        fix: use a breaker of 5 A or less, or a heavier gauge
```

A 10 A breaker may not protect 22 AWG wire. Every number like this comes from a cited table in
`schemagen/core/data/` and can be overridden per project (`tables:` in schemagen.yml). Use a 5 A breaker: change the
device string in the two rows that name it.

<!-- run -->
```bash
sed -i.bak 's/CB-2 10 A/CB-2 5 A/' wires.csv && rm wires.csv.bak
schemagen check .
```

`0 error(s), 0 warning(s), 0 info`. Other formats for CI and editors: `--format json` and `--format sarif`.

Rules also cover the **wire direction convention**: supply runs source → load, returns run device → ground bus,
signals run sender → receiver. Had a row been written backwards, `schemagen fix direction .` would show a change set
and a diff, and `--apply` would store it under `changes/`. Nothing is ever edited silently.

## 5. Drawings, pinouts and lists

<!-- run -->
```bash
schemagen draw . --no-render
schemagen pinout .
schemagen wirelist . -o out/wirelist.xlsx
```

`draw` writes a WireViz drawing for the bulkhead connector and interface drawings for every wire no harness drawing
reaches, so every conductor is drawn (`out/coverage.txt`). It also writes a cut list and a continuity and insulation
test sheet per harness connector. Without `--no-render` it renders SVG, PNG and HTML through the `wireviz` command and
an `out/index.html` with search. `pinout` writes a pinout per component and connector (XLSX and HTML) with spare pins.

## 6. Simulate it

A scenario says what is switched on and what you expect. `tail-lamp/scenarios/lamp_on.yml`:

<!-- file: scenarios/lamp_on.yml -->
```yaml
scenario: tail lamp on
set: {SW-1: closed}
expect:
  powered: [LP-1]
  max_drop_V: {LP-1: 1.0}
  min_voltage: {BB1: 12.5}
  no_trip: true
```

<!-- run: expect-fail -->
```bash
schemagen sim .
```

```
FAIL  tail lamp on: 5 iterations, residual 8.3e-13 A
      expectation failed: LP-1: drop 1.058 V (max 1.0 V)
```

The lamp gets power, but 10.5 m of 22 AWG wire there and back drops more than the 1 V budget at 1.7 A. Use 20 AWG for
the lamp circuit (both halves of the bulkhead pins, so the gauge does not change across the connector), check again,
and run the scenario and the fault sweep:

<!-- run -->
```bash
sed -i.bak 's/,14 V,22,/,14 V,20,/; s/,GND,22,/,GND,20,/' wires.csv && rm wires.csv.bak
schemagen check .
schemagen sim . --faults all
```

```
pass  tail lamp on: 5 iterations, residual 1.1e-12 A
fault sweep: 10 nodes, 2 not cleared, 3 not selective, 1 wire damage, 0 over interrupt rating (0.0 s)
```

Read the fault sweep in `out/sim/report.html`:

- **2 not cleared:** shorts at the battery and at CB-1's line terminal, which no breaker protects. Keep that wire
  short and well supported.
- **3 not selective:** shorts behind CB-2 trip CB-1 at the same moment. Neither breaker has a card, so both use the
  generic thermal curve marked *assumed*, and above ten times their rating both trip "instantly". A card with each
  breaker's real time-current curve (`trip_curve:`) settles it.
- **1 wire damage:** a short at CB-2's line terminal is cleared only by the 15 A main breaker, too slowly for the
  20 AWG feeder L03 (I²t). A heavier feeder or a shorter one is the fix.

The report shows bus voltages, breaker loading, the voltage at the lamp and every assumption the result rests on:
lengths are from the wire list (design values); contact and breaker resistances are assumed because the cards do
not give them. The fault sweep shorts every powered node to ground. For each short it reports which breaker trips
first and how fast, whether the wire survives (I²t), and whether the upstream breaker stays closed (selectivity).
`schemagen sim` exits 1 when an expectation fails, so it can run in CI.

## 7. Work as a team

- **A shared sheet.** `schemagen template . -o sheet.xlsx` writes the whole project as a workbook (Wires,
  Protection, Decisions, Open items, Parts, ...). The Wires sheet has dropdowns for gauge, function class, status,
  devices and connector halves. Upload it to Google Sheets or open it in any spreadsheet. Point `source:` at the
  downloaded file to read it back. Round trips are lossless: columns schemagen does not know are kept.
- **Labels.** `schemagen labels . --update` records every printed label in `label_ledger.json`. A label that leaves
  the wire list is retired with a reason, and the `label-reused` rule stops it from being printed again.
- **Git.** Commit the folder. `schemagen diff HEAD~1 HEAD --project .` lists added, removed and changed wires, pins,
  labels, protection and open items between two revisions.

<!-- run -->
```bash
schemagen template . -o out/sheet.xlsx
schemagen labels . --update
schemagen export . -o out/project.xlsx
```

## 8. The app

```bash
schemagen app .
```

This opens the project in your browser. The app runs on your own machine (127.0.0.1), with nothing loaded from the
internet:

- **Wires:** edit a gauge or a status and press Save. The edit becomes a change set in `changes/` (commit it); Undo
  removes the last one.
- **Pins:** click one and its net lights up in the table, the drawings and the system graph.
- **Search:** Ctrl K finds every wire, pin, component, connector, harness, net and part.
- **Simulation:** runs your scenarios and the fault sweep.
- **Issues:** lists the rule findings and open items.
- **Changes & diff:** compares against a git revision and previews the direction fix.

Next: read `README.md` for every command and key, and `docs/decisions.md` for why things are the way they are.
