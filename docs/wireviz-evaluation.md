# WireViz vs Filare (October 2026)

Both were given the same test harness: a connector in the middle of a chain, a splice as `style: simple` with notes,
a twisted shielded pair with a striped colour (`GNWH`), and a cable with a length.

| | WireViz 0.4.1 | Filare 1.6.0 |
|---|---|---|
| Install | `pip install wireviz`, works | crashes on start: undeclared dependency `faker`; also pulls in weasyprint |
| Runs the test YAML | yes | only after `pip install faker`; HTML/title page fails without `company` and `address` metadata |
| `style: simple` + `notes` (splices, "continues at") | note drawn | **note dropped** |
| Striped colour `GNWH` | drawn | warning per wire ("more than 2 colours for a gradient") |
| BOM | every wire (0 m when no length) | wires without length **left out** |
| Extras | — | source connector named in cable box; shared BOM over harnesses; draw.io export |

**Choice: WireViz 0.4.1.** Filare is the more ambitious fork, but in 1.6.0 it is not reliable enough to depend on.
schemagen emits plain WireViz YAML, so moving later only needs a metadata block.

## Splice drawing options

1. **`style: simple` connector with notes (chosen)**: a labelled box where all wires meet, reads like a splice; the
   note carries "continues at". No fake pin table.
2. 1-pin connector: readable, but suggests a pin and a part that do not exist; BOM lists "Connector, 1 pin".
3. 3-pin connector with `loops`: loops are drawn over the box and Graphviz prints `port … unrecognized` warnings.

## What WireViz cannot do (and how schemagen works around it)

1. No splices, buses or nets: splices are simple nodes, nets are computed in `net.py`.
2. No cross-drawing references: "continues at" text is computed and placed as notes.
3. Gauge is per cable, not per wire: mixed-gauge runs are split into several bundles.
4. No mated connector pair in 0.4.1: both halves are drawn as one connector (left/right).
5. No twist drawing: twisted pairs are a `type:` text plus a shield.
6. Layout left to Graphviz: no zoning, wide drawings for big harnesses, nothing to scale.
7. No lengths/routes, no checks, no cut/test documents, no search: all added by schemagen.
