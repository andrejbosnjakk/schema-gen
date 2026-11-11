# Notes for the 1.0 product review

Open questions the owner and the lead want the reviewer to look at. Not bugs to fix silently: each needs a decision.

## The diagram does not show clearly where each wire goes (owner)
Edges are coloured by function class only, so most of a 14 V system is one red; bundled edges between a pair of
components hide which wire is which, and long edges run in shared gutters, so following one wire from end to end is
hard (docs/screens/3-main/). Kept as it is for now. Directions to evaluate: colour or dash by bus / circuit instead of
class; highlight a whole circuit (source → breaker → bus → load) on hover or selection; route edges per bus with
fewer shared gutters; show a bundle's wires when it is selected; a per-component "pin view" instead of edges.

## The unpowered bus is only found by Simulate
No check rule reports a bus that has loads but no source; it appears only in the Simulate overlay (D44, D66, D75).
A rule flagged a bus in examples/demo and broke pinned findings, so it was left out. Should Issues show it at import?

## Rule wording vs the overlay
The oversized breaker (CB-XPDR 15 A on 20 AWG) is reported by `gauge-protection` as "wire gauge too light"; only the
overlay says "15 A is too big for 20 AWG wire". Same fact, two framings.

## Heavy-wire threshold
A wire without a protector is "far heavier than needed" only above 25 × its current (`sim.heavy_margin`, a design
default with no standard behind it, D75). In practice it almost never fires.

## Smaller items
- An imported project is named after its file stem ("wires").
- The installer is not code-signed (SmartScreen shows "unknown publisher").
- Graphviz and WireViz are not in the installer (licences, D72); harness drawings need them installed separately.
- Weakest kind icons: relay, sensor, harness.
