# The readable sheet

The layout a team edits by hand. schemagen reads it directly (`source: {path: wires.xlsx}`; the layout is detected from
the header row, or set `format: readable`) and writes it back with `schemagen export <project> --readable -o x.xlsx`.
`schemagen synth --readable [--clean]` writes a fictional example.

## Layout

One header row, then rows of three kinds:

| row | how it is recognised | becomes |
|---|---|---|
| subsystem title | text in column A only (usually a merged, coloured bar) | `subsystem` of the wires below it |
| component header | text in column B only | a group heading kept for export |
| wire | anything else | one conductor |

Columns (by header text, in any order): **Label, Name, From, From connector / pin, To, To connector / pin, Voltage,
Current (A), Gauge, Length (m), Weight (g)**. Empty rows are skipped and are not written back.

## Devices

From and To hold plain names ("Breaker 'AVIONICS' 10 A", "Sling panel", "Firewall connector PSW", "Ground bus",
"VCU"). The kind of each device comes from the first matching pattern (case-insensitive), overridable under
`readable: {kinds: {...}}` in schemagen.yml:

| kind | default pattern |
|---|---|
| splice | `\bsplice\b` |
| bus | `\bbus\b`, `\bbus ?bar\b` |
| breaker | `^breaker\b`, `\bcircuit breaker\b` |
| fuse | `^fuse\b` |
| harness connector | `\bconnector\b` |
| relay | `\brelay\b`, `\bcontactor\b` |
| switch | `\bswitch\b` |
| device | anything else |

Each device gets a code: its kind's prefix (`CB-`, `FU-`, `SP-`, `BB-`, `X-`, `K-`, `SW-`) and the name in capitals
(for breakers, fuses and switches the quoted part: `CB-AVIONICS`). An optional **Components** tab (columns Name, Kind,
Code, Location, Part) overrides the kind and code and sets the zone and part number. The name stays the display name.

Harness connector halves get their side from the connector text ("cockpit side, pin 7"). By default *cockpit side*,
*fuselage side* and *cabin side* are near and *nose side*, *tank side*, *wing side*, *back cabin side* and *side-wall
sensor side* far; add or override under `readable: {sides: {"engine side": far, "nose side": near}}`.

## Connector / pin grammar

Whitespace is collapsed and a trailing `(note)` is allowed and ignored ("terminal 87 (NO)", "positive terminal (M6)").
The rest must be one of:

| written | connector | pin |
|---|---|---|
| `pin P` | | P |
| `terminal T` | | T |
| `C.P` (e.g. `X1.A`) | C | P |
| `C, pin P` (e.g. `J2, pin C3`, `cockpit side, pin 19`) | C | P |
| `lead N`, `red lead` (any wire colour) | lead | N / red |
| `coil +`, `coil -`, `coil A1`, `coil A2` | coil | + / - / A1 / A2 |
| `A1 (+) M8 stud`, `A2 (-) stud` | | A1 / A2 |
| `positive terminal`, `negative terminal` | + / - | |
| `line side`, `load side` | LINE / LOAD | |
| `splice`, `stud` | Splice / Stud | |
| `C, name` (e.g. `3, in`, `2, drop`, `Connector, V_in 5 V`) | C | name |
| a name without a pin number (`line stud`, `fuse output`, `in`, `TNC`, `tip + ring`, `safety loop in`) | the name | |
| (empty) | | |

P, T and N are letters, digits, `+` and `-`. A named terminal is letters, digits, spaces and `.,+/&-`; placeholders
(`TBD`, `TBC`, `n/a`, `spare`, `see ...`, `check ...`), questions (`?`) and `pin` / `terminal` without a single pin are
not names. A cell that matches none of these is kept as written (as the connector name) and reported by the `readable-cell` rule with its sheet, row and column.

## Round trip and edits

The cell text is kept with each conductor, and text in a number column (`TBD` in Current (A)) is kept and written
back as read. Export writes it back unchanged while the connector and pin it means are
unchanged; after an edit the cell is written in the canonical form of the table above (first form per row).

## Near-duplicate names

Names that differ only in case, spacing or punctuation, or by a typo of one letter (two in words of six or more
letters) are reported when the sheet loads. `schemagen fix names <project>` proposes a change set that merges each
variant into the more used spelling (the first used on a tie). Names whose numbers differ, or that differ in a token
of one or two letters (L / R, A / B), are never merged.

## CAN

A wire whose name starts with `CAN1`, `CAN2` ... or `GCAN`, or contains `CAN_H` / `CAN_L`, and a wire touching a splice
with CAN in its name, is CAN (`CAN_L` when the name says L, else `CAN_H`); override the pattern with
`readable: {can: <regex>}`. CAN has no one-way direction: it is never judged as a signal from sender to receiver, only in bus
order from a termination (when two are found).
