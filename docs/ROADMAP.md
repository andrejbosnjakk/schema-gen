# Roadmap

## Now (0.1)

- Harness drawings per harness connector (WireViz), "continues at" notes from the net model
- Cut list, continuity/insulation test sheet, consistency checks, searchable index page
- Project config (`schemagen.yml`), default display for projects without their own naming module
- Fictional demo project, tests, CI

## Next: drawing and data

1. **Lengths**: route segments per zone (nose → firewall → cockpit → cabin → tail/wings) and a length per wire as
   segment sum + service loop. Feeds `lengths.csv`, which already flows into cut list, bundles and BOM.
2. **Connector catalogue**: YAML per part (D-SUB 25 M/F, 8STA, AMPSEAL, M12) with contact part numbers, AWG range and
   max current per contact. Checks gauge and current per contact; real part numbers in the BOM.
3. **Layout**: split very wide harnesses by side or function with cross-references; zone ranks in Graphviz.
4. **Printable test sheet** (xlsx/PDF) with signature boxes, and a pin-pair export for an automatic harness tester.
5. **Cards → pin map** stored in the cards themselves instead of `cardmap` regexes.

## Simulation layer (the one-shot system test)

Goal: from the same wire list, answer *"with these switches and breakers, does each load get power, how much current
flows in each wire, what is the voltage at each load, and does anything trip or overheat?"*, and run fault cases.

### Model

The `Net` graph already gives the topology. The simulation adds electrical values:

| element | model | data needed |
|---|---|---|
| wire | resistance R = ρ(AWG) × length (+ temperature) | AWG (have), length (roadmap item 1) |
| splice, harness pin, crimp | small contact resistance | default per contact type (catalogue) |
| bus bar, ground bus | ideal node | — |
| breaker / fuse | closed switch with trip curve I²t; open when tripped | rating (have in `P`), curve per part |
| switch / relay / contactor | two-state element; relay coil is a load that sets the contact state | pole/terminal map, coil data (cards) |
| battery | voltage source + internal resistance (+ state of charge) | cards |
| DC/DC converter | voltage source with current limit, enabled by a signal | cards |
| load | constant power, constant current or resistor; optional enable input | cards / load analysis |
| signal input | high-impedance node (voltage only) | cards |

### Solver

1. Build the circuit from `Net`: nodes = net roots, branches = wires + elements.
2. DC operating point by **modified nodal analysis** (numpy/scipy sparse); constant-power loads and relays by fixed-point
   iteration (relay coil voltage → contact state → re-solve).
3. Breakers: compare branch current with the trip curve over a scenario timeline (inrush, steady state).

### Scenarios (YAML)

```yaml
scenario: master on, ECU on, engine start
set: {SW-MSTR: ON, CB-ECU: closed, CB-GEN: closed}
faults: [{short: L05, to: GND}]          # optional: short, open wire, failed source
expect:
  powered: [ECU, DSP, OTS]
  max_drop_V: {ECU: 0.5}
  no_trip: true
```

Output: currents per wire vs ampacity, voltage at each load, trips, and pass/fail per `expect`, as CSV + an overlay on
the harness drawing (wire thickness/colour by current).

### Steps

1. `sim/circuit.py`: circuit from `Net` + element library (resistors, sources, switches) — unit tests on tiny nets.
2. MNA DC solver + continuity-style "is it connected to the source" pass (useful before any values exist).
3. Breakers and relays (iteration), scenario YAML runner, report CSV.
4. Fault injection (short/open per wire), I²t trip check, wire ampacity check.
5. Drawing overlay and an interactive page (toggle switches, see currents).
