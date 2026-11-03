# schema-gen

Turns a wire list (one row = one physical conductor) into wiring-harness documentation, and later into a
simulation of the electrical system. Built for vehicles, aircraft and machines: anything with harness
connectors, splices, breakers and buses.

- **Harness drawings** per harness connector, rendered with [WireViz](https://github.com/wireviz/WireViz) (SVG, PNG,
  HTML + BOM). One bundle per far item, each wire labelled with its gauge (`RD:L05 · 22`), CAN pairs twisted and shielded.
  Wide harnesses are split by side or by function.
- **"Continues at"**: every wire that ends on a splice, bus, breaker or another harness gets a short next-hop note
  (`L05 → L04 (CB-ECU LOAD), L06 (X-BH 2) [1]`); the full continuation and net end points go into a numbered footnote
  table under the drawing and into the cut list.
- **Cut list** (CSV): label, from, to, bundle, gauge, colour, length, continues-at.
- **Continuity / insulation test sheet** (CSV) between reachable terminals only (splices are sleeved, so tests walk
  through them): each connector half to its equipment, end to end through the mated connector (parallel contacts
  flagged), and pin-to-pin insulation that knows which pins are tied on purpose.
- **Consistency checks**: pin clashes, one-sided pins, gauge or function changes across a connector, TBD pins and gauges.
- **index.html**: all drawings in one offline page; a wire-label search highlights the wire and its footnote.
- **Part data from datasheet cards**: pin names from a structured block in each card (the start of a part library).
- **One palette** for every output; other tools read it with `schemagen palette`.

Next: a neutral data model, then a DC current-flow simulation on the same net model ("does this load get power with
these switches, how much current flows in each wire, does this breaker protect this wire?"). See [docs/ROADMAP.md](docs/ROADMAP.md).

![demo harness](docs/demo_X-BH.png)

## Quick start

```bash
sudo apt-get install graphviz        # WireViz needs Graphviz's `dot`
pip install -e ".[dev]"
schemagen draw examples/demo         # writes examples/demo/out/
pytest
```

| command | does |
|---|---|
| `schemagen draw <project> [X-BH ...] [--all] [--split none\|side\|function\|auto] [--no-render]` | drawings and their extras |
| `schemagen export <project> -o wires.xlsx` | the project in the neutral table format: `.xlsx` workbook, a folder of CSVs, `.csv` (wires only) or `.json` (the whole model) |
| `schemagen schema [-o schemas]` | JSON Schemas of the model, the part library and issues |
| `schemagen synth --wires N --seed S -o DIR` | a synthetic (fictional) project for tests and benchmarks |
| `schemagen palette <project> [--json]` | function class → colour code and hex, for spreadsheets and schematic tools |

`<project>` is a `schemagen.yml` or the folder that holds it. `--no-render` writes YAML, CSVs and checks without WireViz.

## A project

A project is a folder with a `schemagen.yml` and a wire list. The wire list stays in your own (private) repository;
this repository only holds the tool and a fictional demo. The wire list is either a **table** or **Python row modules**:

```
my-project/
  schemagen.yml
  wires.csv            # a table: CSV, XLSX or JSON, one row per conductor (set `source` in schemagen.yml)
  wirelist/            # ...or Python row modules:
    ss01_power.py      #   R = [dict(id=..., p1=..., p1c=..., p1p=..., p2=..., ..., func=..., bus=..., awg=...)]
    labels.json        #   optional: wire id -> printed label (L05)
    display.py         # optional (both forms): readable names; default in display_default.py
    names.py           # optional: NAMES (id -> wire name)
  cards/               # optional: datasheet interface cards (markdown) for real pin names
```

Row fields (the neutral format, `schemagen export` writes it): `id`, `label`, `name`, `p1`/`p1c`/`p1p` = from device /
connector / pin, `p2`/`p2c`/`p2p` = to, `func`, `bus`, `awg`, `amps`, `st` (status; `Open…` is flagged),
`subsystem`, `notes`. Device strings start with a code (`SP-…` splice, `CB-…` breaker, `GNDB` ground bus, `X-…`
harness connector); the prefixes are set in `schemagen.yml`.

The neutral table is lossless: every input key that has no column of its own is kept in the model's `extra` and gets
its own column on export (`key:json` when it holds lists or numbers). Row-module keys `src` (sources: `DOC p. 4; DOC2 p. 7`),
`zone`, `harn` (harness), `prot` (protective device) and `col` (explicit colour) map to model fields; module-level
`P` (protection), `D` (decisions) and `O` (open items) tables become objects. Plain column names (`from`, `from connector`,
`from pin`, `from side`, `gauge`, `current_A`, ...) and the 0.2 names (`p1`, `p1c`, ...) are both accepted.

Connector-half sides: give them in `schemagen.yml` (`sides: {X-BH: {Cabin half: near, Engine half: far}}`) or in the
table's `from side` / `to side` columns. `near_words` is only a fallback, and every guess is reported as a warning.

A *readable* wire list (display names, connector and pin merged into one text cell) is a view, not a source: it has
lost the device codes and pin structure the net model needs. Export the structured rows instead.

`schemagen.yml` (all keys optional except what your data needs; see [examples/demo/schemagen.yml](examples/demo/schemagen.yml)):

| key | meaning |
|---|---|
| `wirelist`, `cards`, `out` | folders, relative to the yml |
| `source` | table input: `{path, sheet, header_row, columns: {field: column name}}` (see `table.py`) |
| `default_harnesses` | harness connectors drawn when none are named |
| `split`, `split_default`, `split_threshold` | per-harness split mode; `auto` splits by side above the threshold of far items (default 20) |
| `buses`, `bus_prefixes`, `breaker_prefixes`, `splice_prefix` | how device codes map to roles |
| `near_words` | words in a connector-half name that put it on the left (e.g. `cabin`, `half a`) |
| `colours` | function class → WireViz colour. Default: 14 V `RD`, 24 V `YE`, 5 V `VT`, GND `BK`, signal `BU`, CAN_H `GN`, CAN_L `GNWH`. Orange is not used: it is the usual HV colour. |
| `bus_class` | bus name → function class (e.g. `Switched out: 14 V`) |
| `label_class` | wire-label regex → function class, for powered wires whose bus name has no voltage (e.g. `'^T\d': 24 V`) |
| `harnesses` | for projects without `display.py`: `prefix: [name, code, far side]` |
| `cardmap` | fallback for cards without a structured block: `{device, connector, card, table}` regexes |

Optional `<out>/lengths.csv` (`label,length_m`) fills in lengths in the cut list, the bundles and the BOM.

### Datasheet cards

A card is a markdown file in `cards/`. schemagen reads a fenced block marked `yaml schemagen` anywhere in it:

````markdown
```yaml schemagen
device: '^ECU$'                 # regex on the device code in the wire list
connectors:
  - id: J1
    match: '^J1$'               # regex on the wire list's connector field
    part: TE 776286-1
    pins:
      - {n: 1, name: VBAT, type: power_in, v_max: 16, i_max: 5}
```
````

Cards without a block can still be used through `cardmap` (markdown pin tables), but that is fragile; ask whoever
writes the cards for the block.

## Code map

| module | role |
|---|---|
| `core/model.py` | the typed model (Pydantic v2): conductors, components, connectors, parts, protection, decisions, open items, ledger; JSON Schemas in `schemas/` |
| `core/config.py` | `schemagen.yml` → `Config` |
| `core/load.py`, `core/build.py` | pick the importer, resolve labels / classes / sides, derive components and protection |
| `core/net.py` | typed connectivity (union-find); breakers and switches are elements, not connections |
| `importers/` | row modules, tables (XLSX / CSV / CSV folder / JSON), WireViz YAML, part cards |
| `exporters/` | neutral table (workbook / CSV folder / CSV), JSON model |
| `project.py`, `table.py`, `config.py` | 0.2 interfaces on top of the model (wire dicts for the drawing code) |
| `styles.py`, `palette.py` | function class, wire colour, gauge; the palette for other tools |
| `net.py` | 0.2 interface to `core/net.py` for the drawing code: reachable terminals, next hops |
| `cards.py` | pin data from card blocks (or markdown tables) |
| `drawing.py` | WireViz document for one harness connector or one part of it |
| `checks.py` | consistency checks |
| `outputs.py` | YAML, render (WireViz command), footnotes, cut list, test sheet, checks, index page |
| `cli.py` | `schemagen` command |

## Why WireViz 0.4.1 (and not Filare)

Short version: WireViz renders everything this needs; Filare 1.6.0 (its fork) drops notes on simple nodes and
wires without a length from the BOM, and does not install cleanly. Details in [docs/wireviz-evaluation.md](docs/wireviz-evaluation.md).
The generator emits plain WireViz YAML, so the renderer stays replaceable.

## Licence

MIT (see `LICENSE`). WireViz is GPL-3.0, so schemagen never imports it: it writes WireViz YAML and runs the separate
`wireviz` command (a test checks this).
