# Cited values in `schemagen/core/data/`

Every number the rules and the simulation take from a standard, with the clause it comes from. All of them can be
overridden per project (`tables:` in schemagen.yml; `sim:` for the simulation defaults).

**Status** says how far a value has been checked:
- *definition*: a defined constant or formula, low risk;
- *to verify*: written from memory of the document, not yet checked against a copy of it. Check it against the
  current edition before a design relies on it.

The assumed simulation defaults in `sim.yml` (contact resistance, breaker and switch resistance, default lengths,
the generic trip curve, interrupt rating, inferred sources) cite no standard. Every result that uses one lists it as
*assumed*.

## wire.yml

| key | value | source and clause | status |
|---|---|---|---|
| AWG diameter (code: `awg_diameter_mm`) | d = 0.127 mm × 92^((36 − n)/39) | ASTM B258, standard nominal diameters of solid round wires (the AWG definition) | definition |
| `resistivity_ohm_m` | 1.7241e-8 Ω·m at 20 °C | IEC 60028, International Annealed Copper Standard (100 % IACS) | definition |
| `alpha_per_K` | 0.00393 /K at 20 °C | IEC 60028 (temperature coefficient of annealed copper) | definition |
| `k_insulation` | 143 (copper, XLPE/EPR, 90 → 250 °C); PVC 115 | IEC 60364-4-43:2008, clause 434.5.2, Table 43A | to verify |

`k_insulation` is a choice per project. Aircraft wire is often ETFE- or PTFE-insulated (e.g. to SAE AS22759), and
Table 43A has no row for fluoropolymers. Their k follows from the conductor's permitted initial and final
temperatures (for example via IEC 60949 or the wire specification's short-circuit rating). Set `tables: {wire:
{k_insulation: ...}}` from the wire's datasheet, not from the default.

## protection.yml

| key | value | source and clause | status |
|---|---|---|---|
| `breaker` | AWG 22…2 → 5, 7.5, 10, 15, 20, 30, 40, 50, 80, 100, 125 A | FAA AC 43.13-1B (change 1), chapter 11, Table 11-3 "Wire and circuit protector chart" | to verify |
| `fuse` | AWG 22…0 → 5, 5, 10, 10, 15, 20, 30, 50, 70, 70, 100, 150, 150 A | same table, fuse column | to verify |

The chart's basis (135 °F ambient, up to 30,000 ft, bundles of 15 or more wires at no more than 20 % of the bundle
capacity) is quoted in the file header. A project with other conditions sets its own table.

## can.yml

| key | value | source and clause | status |
|---|---|---|---|
| `max_nodes` | 30 | SAE J1939-11, physical layer (250 kbit/s, shielded twisted pair): maximum number of ECUs on a segment | to verify |
| `min_nodes` | 2 | a bus needs a sender and a receiver (no standard clause) | definition |
| `terminators` | 2 × 120 Ω, one at each end | SAE J1939-11; ISO 11898-2 (bus termination) | to verify |
| `max_stub_m_by_bitrate` 250 | 1.0 m | SAE J1939-11: maximum stub (node) length | to verify |
| `max_stub_m_by_bitrate` 500, 1000 | 0.3 m | ISO 11898-2 design guideline for high bit rates. The figure may come from transceiver application notes rather than the standard's normative text | to verify |
| `bitrate_kbit` | 250 | default only (J1939 rate) | definition |
| `terminator_pattern` | `^R-CAN\|terminator\|120 ?(Ω\|ohm)` | naming heuristic, no standard | n/a |
