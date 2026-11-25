# Drawing model (1.1, stream A)

The contract of schemagen's own wiring-diagram engine (`schemagen/drawing/`). Pipeline:

```
scope.scene(st, scope) -> Scene -> symbols -> layout (5 mm grid, sheets) -> routing -> Geometry -> renderers (SVG, PDF)
                                                                                       verify.roundtrip(st, scene, geometry)
```

This document fixes the two ends: the **Scene** (what is in a drawing) and the **Geometry** (where everything is). Both are
plain JSON-serialisable dicts; their types are the TypedDicts in `schemagen/drawing/geometry.py`. Version: `1`.

Modules: `scope.py` (`parse`, `members`, `scene`, `walk`), `geometry.py` (types, `to_json`, `from_json`, `validate`),
`verify.py` (`netlist`, `scene_netlist`, `expected`, `roundtrip`, `diff`), `layout.py` (`columns`, `place`, `paginate`), `route.py` (`tracks`, `trace`,
`labels`), `engine.py` (`draw(st, scope, size, meta)`, `export(geometry, path)`), `reference.py` (the six reference drawings). `schemagen.drawing` also keeps the 0.2 names
(`build`, `build_set`, ... from `schemagen.renderers.harness`).

## Ids

| Thing | Id | Example |
|---|---|---|
| component item | `component:<component id>` | `component:ECU` |
| harness connector item | `connector:<component id>` | `connector:X-BH` |
| pin / terminal (anchor) | `pin:<component id>/<connector or half>/<pin>` (`Ctx.ref`, as in issues) | `pin:ECU/J1/3`, `pin:X-BH/Cabin half/3`, `pin:BAT/+/` |
| wire | conductor id; `model` is `conductor:<id>` | `PWR-ECU-1` |
| off-sheet flag | `flag:<conductor id>` | `flag:W011` |

An anchor id equals its `model`, and is unique in a scene. A harness connector has one anchor per half and pin. A splice or
bus anchor is the terminal as written (`pin:GNDB/Stud/`) in the scene. In the geometry a splice, bus or ground has **one anchor per wire** along its bar
(left and right of it), id `<pin ref>#<conductor id>`, `model` the pin ref; so has a pin or terminal that several wires share (a row each on a block or
harness, a short strip on an in-line part).

## Scene

### Scope

`scene(st, scope)` takes a string or a parsed `Scope`. `st` needs `m`, `ctx`, `cfg` (the app's `State` fits); `issues` and
`overlay` are used when present. Unknown kinds or ids raise `ValueError`.

| Scope string | Components drawn in full (S) |
|---|---|
| `component:<id>` | that component (a harness connector too) |
| `connection:<A>~<B>` | A, partial: only runs from A that reach B are walked; B is their far end |
| `harness:<id>` | the harness connector, both halves, every pin to `pin_count` |
| `selection:<id>,<id>,...` | those components |
| `subsystem:<name>` | components most of whose conductors carry that subsystem (ties: first name), splices and harness connectors excluded |
| `system` | every component |

`Scope = {kind, ids, text}`; `text` is the normalised string.

### Inclusion rule (D108)

1. From every conductor end on a component in S, every **run** is walked (`walk`): through splices and harness connector pins
   (both halves are one node) until it lands on any other terminal (device pin, breaker/switch/relay terminal, bus). Every
   conductor on a run is a **wire**. Breakers, fuses, switches and relays are elements: a run stops at their terminal and never
   crosses to the other side (core/net.py semantics).
2. The **drawn nodes** are the core/net.py nodes of S's terminals and of every run end (a bus is one node; a harness pin is one
   node for both halves).
3. Every other conductor with an end on a drawn node is a wire if its other end is on a drawn node too, else an **off-sheet
   flag** on that node. Nothing on a drawn node is left out; a conductor is a wire or a flag, never both.
4. Components that are not in S show only the pins that wires or flags touch (`partial: true`).

### Scene fields

`Scene = {version, scope, title, project, items, wires, flags}`. Lists are sorted: items by (`column`, code), wires and flags by
id (natural order). Output is deterministic and independent of the order of the input lists.

**Item**

| Field | Meaning |
|---|---|
| `id`, `model` | item id (= model id) |
| `role` | `in_scope` (in S), `harness` (a harness connector, in S or not), `part` (distribution part not in S), `far_end` (a block not in S where runs land) |
| `symbol` | see the symbol table |
| `kind` | model kind (`Component.kind`) |
| `code`, `name`, `part`, `location` | component id, display name, part number (part id), zone |
| `partial` | only touched pins are listed (always for items not in S, and for A in a connection) |
| `column` | left-to-right hint: 0 sources, 1 protection and switching, 2 buses, 3 in-scope blocks, 4 harness connectors and splices, 5 far ends and terminators, 6 grounds |
| `blocks` | one per connector, in natural order (harness: near half, then far half) |
| `attrs` | symbol data, see below |

**Block** `{id, part, mate, side, pins}`: connector (or half) name, connector part number (part data), mating half (`extra.mate`
of the part's connector; usually ""), `near`/`far` for harness halves else "", pins in natural order (`_natural`).

**Pin** `{n, name, type, anchor, spare}`: pin number as written ("" when the connector is the terminal: `+`, `LOAD`, `Stud`),
pin name and type from part data (type falls back to the terminal name on breakers, switches, relays, sources), anchor id,
`spare` = no conductor at this terminal in the model. Items in S list every pin the part defines (or 1..`pin_count` on each half
of a harness connector), so unused pins are present and spare. Harness halves always list the same pin numbers (matched side
by side).

**Symbols and attrs**

| `symbol` | for | `attrs` |
|---|---|---|
| `block` | device, load, sensor, controller | `{}` |
| `harness` | harness connector | `{}` |
| `splice` | splice | `{}` |
| `bus` | bus | `{function_class}` |
| `ground` | bus whose function class is GND | `{function_class}` |
| `breaker`, `fuse` | protective devices | `{rating_a, panel}` |
| `switch`, `relay` | switches, relays | `{state: "normal", contacts: [{a,b} or {com,no,nc} as pin refs], coil: {a1,a2} or null}` (relay: de-energised; switch: as given, drawn open) |
| `terminator` | terminator | `{value}` e.g. "120 Ω" from the part or name, else "" |
| `battery`, `dcdc` | sources (`kind_of`: also inferred sources) | `{voltage}` from part data (v_oc or v_out), else null; polarity is in the pin names/types |

**SceneWire** `{id, model, label, name, gauge, colour, hex, cls, weight, a, b, pair, shield, harness, sev, fault}`: `colour` is the
colour code (resolved, else as written), `cls` the function class (`CAN_H`/`CAN_L`, else 14 V, GND, signal ...), `a`/`b` the
anchors of the from and to end, `pair`/`shield` from `extra.pair`/`extra.shield` (the model has no such fields; "" today),
`sev` the worst issue severity, `fault` `{status, reason}` from the simulation overlay when its status is not ok, else null.

**Weight classes** (`weight`): `heavy` <= 10 AWG, `medium` 12-16, `light` 18-22 and unknown gauge, `fine` >= 24.

**SceneFlag** `{id, model, kind: "off_sheet", at, target, target_item, text, label, gauge, colour, hex, cls, weight, covers?}`: `at` is the
anchor on the drawn node, `target` the pin ref of the conductor's other end, `target_item` its item id, `text` "→ " plus
`pinout.far_text` (display names, through splices and harness pins to where it lands). A bus or ground node with 4 or more such flags gets
**one summary flag** instead (D111): `text` "+ 22 more wires on GND-BUS", `covers` the list of `{id, at, target, label, gauge,
colour}` of the conductors it stands for (`at`, `target`, ... of the flag itself are the first one's). Splice flags stay individual.

## Geometry

The output of the engine and the **only input of renderers**. mm, origin top left, y down. Every element carries `model` (the
model id it represents, "" for decoration).

```
{version: 1, drawing: {title, scope, project, revision, date, drawn_by, source},
 sheets: [{n, of, size: "A3"|"A4", w_mm, h_mm, grid_mm: 5, symbols, wires, texts, flags, notes, legend, title_block, rules, table}]}
```

Sheets are landscape: A3 420 x 297, A4 297 x 210. `notes` are texts; `legend` and `title_block` are free dicts the layout fills
(title block: title, scope, project, revision, date, drawn by, sheet n of m).

| Element | Fields |
|---|---|
| symbol | `{id, kind, model, x, y, w, h, anchors, prims}`; `kind` = scene symbol |
| anchor | `{id, model, x, y, side: L/R/T/B}`; on the grid; `side` is where the wire leaves |
| prim | `{kind, stroke, fill?, dash?, ...}`; kinds `line {x1,y1,x2,y2}`, `polyline {points, closed?}`, `rect {x,y,w,h}`, `circle {cx,cy,r}`, `arc {cx,cy,r,a0,a1}` (degrees from +x, clockwise), `path {d}` (SVG data; avoid). `stroke`: `none`, `thin` 0.18, `normal` 0.35, `thick` 0.5 mm; `fill`: `none`/`black`/`white`. Absolute sheet coordinates |
| wire | `{id, model: "conductor:<id>", label, gauge, colour, hex, weight, points: [[x,y],...], a, b, pair, shield, fault}`; points orthogonal and on the grid; the first point is on `a`, the last on `b`; `a`/`b` are anchor or flag ids on the same sheet |
| text | `{s, x, y, w, h, size_mm, align: left/centre/right, model, role}`; (x, y, w, h) is the bounding box, `size_mm` >= 2.5, boxes do not overlap |
| flag | `{id, model: "conductor:<id>", x, y, w, h, text, target, sheet, kind, side?, covers?, narrow?}`; `side` L/R is the edge the wire enters (at the middle of that edge); `covers` as in the scene (summary flag); `narrow` true: the text is broken at the narrowest width (a component drawing that fits the sheet as a net of wires only so; without it the drawing would be terminal strips); `off_sheet`: a scene flag, `target` the pin ref it leads to, `sheet` null; `continuation`: the conductor goes on at `sheet`, `target` is the pin ref of the conductor's other end (not the anchor of the flag's own wire), `text` says in words what it connects to |

An off-sheet flag is reached by a short wire (stub) from its anchor to the flag; a conductor that continues on another sheet
appears on each sheet as a wire from its anchor to a continuation flag. Every flag is the end of exactly one wire.

**Normative for renderers**: everything above; renderers draw prims, wires (weight class to line width, `hex` as colour),
texts and flags as given, add nothing that changes connectivity, and never read the scene or the model.

**What the netlist round trip relies on**: wire `model`, wire `a`/`b`, anchor `model`, flag `target`, and wire `label`, `gauge`,
`colour`. Ids may change between builds; these may not lie.

`validate(geometry)` returns the problems ([] = fine): version, sheet size and `of`, grid, unique ids per sheet, anchor sides
and grid, prim kinds and strokes, wire model, weight, >= 2 points on the grid, orthogonal, inside the sheet, ends on their
anchor or inside their flag, references resolve, flags used once, continuation sheets exist, text size, overlap and bounds.

## Round trip

An **entry** is `(conductor id, end, end, label, gauge, colour)`, the ends being pin refs in sorted order.

- `netlist(geometry)`: per conductor over all sheets, the anchors' `model` and flags' `target` its wires end on.
- `scene_netlist(scene)`: wires by `a`/`b`, flags by `at` and `target`.
- `expected(st, scene)`: from the model, every conductor on a node the scope must show, found by a breadth-first closure over
  core/net.py nodes (independent of `walk`); for a connection the scene's own nodes.
- `roundtrip(st, scene, geometry)` = `diff(netlist(geometry), expected(st, scene))`: sorted `missing: ...` / `extra: ...` lines;
  empty means the drawing says exactly what the model says.

## Worked example (demo, `component:CB-ECU`, shortened)

```json
{"version": 1, "scope": {"kind": "component", "ids": ["CB-ECU"], "text": "component:CB-ECU"}, "title": "CB-ECU 5 A",
 "items": [{"id": "component:CB-ECU", "role": "in_scope", "symbol": "breaker", "column": 1, "partial": false,
            "blocks": [{"id": "LINE", "pins": [{"n": "", "anchor": "pin:CB-ECU/LINE/", "spare": false}]},
                       {"id": "LOAD", "pins": [{"n": "", "anchor": "pin:CB-ECU/LOAD/", "spare": false}]}],
            "attrs": {"rating_a": 5.0, "panel": "ECU"}},
           {"id": "component:BB1", "role": "part", "symbol": "bus", "column": 2, "partial": true, "...": "..."}],
 "wires": [{"id": "PWR-ECU-A", "model": "conductor:PWR-ECU-A", "a": "pin:CB-ECU/LOAD/", "b": "pin:SP-ECU-C/Splice/", "gauge": "20", "weight": "light"},
           {"id": "PWR-ECU-C1", "a": "pin:SP-ECU-C/Splice/", "b": "pin:X-BH/Cabin half/1", "...": "..."}],
 "flags": [{"id": "flag:PWR-BUS-1", "model": "conductor:PWR-BUS-1", "at": "pin:BB1/Stud/", "target": "pin:CB-MAIN/LOAD/",
            "text": "→ CB-MAIN 30 A LOAD"}]}
```

Geometry for one wire that continues on sheet 2: sheet 1 has the wire `[[50,30],[100,30],[100,50]]` from `pin:A/J1/1` to flag
`c1` (`continuation`, `sheet: 2`, `target: "pin:B/J1/2"`); sheet 2 has the wire from flag `c1` (`sheet: 1`, `target:
"pin:A/J1/1"`) to `pin:B/J1/2`. `netlist` gives one entry `("W1", "pin:A/J1/1", "pin:B/J1/2", "W1", "22", "WH")`.

## Not in the model yet (blank in drawings)

Twisted pair and shield grouping and where a shield is grounded (no Conductor fields; `extra.pair`/`extra.shield` are read if
present), the mating half of a connector, plug or receptacle (harness halves are only near/far), connector part numbers of
harness connectors and of parts without connector part data, panel labels on most breakers (aircraft: empty), stud numbers on
buses (one `Stud` terminal), a switch's normal position, part numbers of components without a part.

## Layout, routing, pagination (stream C)

`engine.draw` = `scope.scene` -> `layout.paginate` -> `layout.place` (columns, rows, channels, `route`) -> `symbols.furniture`. The title is the scope in
words; the date is a parameter (never the wall clock); the legend lists the symbol kinds on the sheet; notes carry simulation faults (the wire is dashed),
contact and spare-pin conventions. Rules: columns by walking out from the scope's components (an in-line part or harness connector has two sides, so a
breaker is fed on its LINE side; hints break ties), a lane (dummy) through every column a wire passes, rows by barycentre sweeps and least-displacement
stacking on the grid, one vertical track per wire that changes row (`route.tracks`: fewest crossings, no overlap, no T junction; two wires that swap rows get
a dogleg), wire text `label  gauge colour` above a horizontal stretch (twice on wires over 150 mm). A wire that would have to run back through a symbol
(a loop) is drawn as two off-sheet flags. Too wide: cut between two columns (the cut conductors end in a continuation flag on both sheets); too tall: cut
between connectors of the scope's components, else through the middle. A wire is drawn on every sheet that shows both its ends; a splice, bus or ground
shows a continuation flag for each other conductor drawn elsewhere (a summary flag when 4 or more). Twisted pair and shield notation is not drawn (the model
has no such data); the reference drawings are in `docs/screens/drawings/` (golden SVGs, `python -m schemagen.drawing.reference`).

## Wire table, wire text, flag text (readable drawings)

- `sheet.table = {sheet, rows}` (since the wrap round only the conductors first drawn on that sheet, see the last section): one row per conductor the sheet shows (as a wire, as a flag, or under a summary flag): `{id, label, gauge, colour, a, b, frm, to}`,
  `a`/`b` the pin refs of its two ends (a flagged conductor: the drawn end and the far end), `frm`/`to` those ends in words (`EFIS, J1, pin 2 (GND)`,
  `splice SP-1`, `ground bus GND-BUS`; a far end that continues on another sheet ends in `(sheet N)`). Rows are in the natural order of the label.
  `sheet` is the sheet the table is drawn on: the sheet itself when it fits under the drawing, else a table sheet after the last drawing sheet (no symbols,
  no wires; its notes say which sheets' rows it holds). The table is drawn as `texts` plus `rules` (prims, drawn under the symbols); the renderers draw
  `rules` like any prims. The colour column spells the code out (`GNWH` = green / white stripe, names in `exporters/palette.py`), the gauge column says `AWG`.
  `verify.table(g)` (part of `verify.roundtrip`) compares each sheet's rows with the netlist of that sheet alone.
- Wire text is `W052 20 AWG BK` (label, gauge with its unit, colour code). The notes box gives a worked example from the sheet, the colour codes used on it in words,
  and where the wire table is.
- Wires are drawn in their colour (`hex`) inside a black casing, in the app, the SVG and the PDF; the code text stays, so a black-and-white print reads the same.
- Flag text is plain words: an off-sheet flag `to X-FW cockpit side 11`, a continuation `continues on sheet 2: X-FW cockpit side 11`; the contract's `text` still
  holds the long form. A terminal of a part that is not in scope and has no wire on the sheet has a dashed lead (a stub that cannot be taken for a wire).

## Rules the checks enforce (`checks.report`)

`wire_through_symbol`: no wire segment enters the interior of any symbol or flag (the wire's own end symbol included; a wire reaches its anchor from outside).
`wire_overlaps`: two different conductors never share a collinear stretch (stubs of one conductor may). `gauge_unit`: a gauge is a plain number and the unit appears
once in any text (the scene strips a `AWG` the sheet already wrote; a gauge that is not a number, such as `TBD`, is printed as written). Label overlaps are
`text_overlaps`, `text_symbol_overlaps` and `wire_text_overlaps`. A wire whose two ends are on one component is drawn as two off-sheet flags, each naming the other
end. The in-line symbols of two terminals (breaker, fuse, terminator, battery) are used only for parts that list at most two terminals; others are blocks.

## Names, flags, hubs, title block, determinism (round 1.2)

- **Names.** A box (component, harness connector, bar, breaker, ...) is headed by the Name column of the wire list (the code when there is no name); the code
  stands small underneath only when it differs from the name. Flags and table cells name a far end by display name: `Battery 14 V, + terminal`, `EFIS, J1, pin 2`.
- **Flags say where the far end is.** An off-sheet flag reads `to <far end> (drawing VCU, sheet 3)`: the drawing (a component id; its PDF is `component-<id>.pdf`)
  that shows the far end and a sheet of it that shows the conductor. Past a splice the far end is the first terminal the run lands on (`... +2 more via <splice>`).
  A continuation flag reads `continues on sheet 2: <far end> (drawing VCU)` (the drawing it is in); a summary flag `+ 59 more wires on GND-BUS (drawing GND-BUS, sheet 1)`.
  A drawing does not know how the others are paginated, so `export_all` draws every drawing twice: the first pass writes `sheet 44` (two digits: the layout measures
  every flag as if it said so, so both passes lay out alike), `drawing.index.index_of` reads where each conductor went, the second pass writes the real sheets
  (`engine.draw(..., where=)`; without `where` a flag names the drawing only).
- **Hubs are terminal strips** (`drawing/hub.py`). A bus, ground bus or splice in scope with at least 12 legs, mostly to different parts, is drawn as a bar with
  one stub per wire (wire text on the stub) ending in a flat one-line flag naming the far end. Nothing is routed. Splices and harness pins the runs go through, and a
  part's pin that carries other conductors too, are small bars of their own with a stub per conductor; a conductor between two bars is drawn at both ends and each flag
  names the other end's sheet. Pages are filled to the foot of the sheet in order; a last page with fewer than 4 wires takes some from the one before.
- **Packing** (`layout.paginate`): a drawing that is too tall is cut into as many sheets as its height needs, at connector boundaries nearest to equal shares, so
  several connectors of one component share a sheet and no sheet but the last is thin.
- **Title block.** REV is `revision:` of schemagen.yml, else the first 8 hex digits of the sha256 of the source wire list (the same hash the SOURCE field carries).
  DATE is `date:` of schemagen.yml, else the modification date of the source file (the newest file of the wirelist folder); never the clock. The PDF's creation and
  modification date are that date. Geometry JSON and PDF bytes are identical for identical input.

## Wrapping, the wire table, the book (round 1.2, wrap)

- **Nothing is cut off.** A text that does not fit goes on to further lines: table cells (the row grows by a line of 4.5 mm per line), flags (the narrowest of
  50..150 mm in steps of 5 that needs two lines, more lines only if the text needs them; a flag is 10 mm high for two lines, 20 for three or four, so the wire
  still attaches on the grid), box names and pin names (`MAXW` = 60 mm), the headings of strip bars (at hyphens), notes and title-block cells (the title block is
  35 mm high; a value or the title goes on to a second line). `style.wrap_all(text, width_mm, size, bold)` is the one wrapper (font metrics of the drawings;
  a word wider than a line is broken inside, after a hyphen if there is one). The verifier reports any text ending in `..` as `text_truncated`.
- **A flag names one sheet**: the sheet of the other drawing that draws the conductor at the terminal the flag leads to (`index.index_of` maps
  (drawing, conductor, terminal) to sheets; `Where` takes the terminal as third argument), never a range. A summary flag names the first sheet.
- **The wire table lists every conductor once per drawing**, under the first sheet that draws it (`sheet.table.rows` holds only those rows; `table.sheet` is
  the sheet the table is drawn on). Chosen over one table per sheet because a conductor between two parts of one drawing, or through splices and harness
  pins, was listed on every sheet that touched it, which cost about half the strip sheets their room; chosen over one table at the end of the drawing because
  the rows keep their `Sheet n` heading, so a person on a sheet finds its wires and the verifier checks each row against the sheet it names. Drawings
  that fit one sheet keep the table under the drawing. A strip drawing's table follows its strips: from the free room under the last strip sheet on, then
  table sheets; strips are filled to the foot of the sheet. The columns are sized per drawing (`table.columns`): the label column as wide as the longest label.
  The SEE column holds `(drawing X, sheet N)`. The verifier's rule: every drawn label has exactly one row in the drawing, under the first sheet that draws it
  (or under a sheet whose summary flag covers it), and the row agrees with the lines of that sheet.
- **Contents of the book** (`drawing/toc.py`): `wiring-diagrams.pdf` is the symbol sheets, then the contents pages (title block `Contents`), then every drawing,
  in alphabetical order of display name, so the page numbers are real. A line: name (a long one goes on to a second line), the id in grey when it differs from
  the name, the number of sheets, the book page the drawing starts on. `export_all` writes the contents from the first pass's sheet counts and, should a count
  differ in the second pass, writes the book again with the real ones. Per-component PDFs have no contents. The verifier (`verify/toc.py`) reads the contents
  pages and checks every entry against the book (name, id shown only when it differs, sheet count, the page of the drawing's first sheet), the order, and that
  each drawing has exactly one entry.
