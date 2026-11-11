# App API (1.0)

The contract between the server (`schemagen/app/server.py`, stream A) and the frontend (`frontend/`, stream B).
Local only: the server binds to 127.0.0.1, nothing leaves the machine. All bodies are JSON unless stated.
Ids in `objects` and overlay keys are typed refs as in the rules engine: `component:ID`, `conductor:ID`, `pin:ID/C/P`.

## Errors (every endpoint)

Any non-2xx answer has this body, and the server never crashes or returns a bare 500:

```json
{"error": {"code": "graphviz-missing", "message": "Graphviz is not installed, so harness drawings cannot be made. The diagram and simulation still work.", "retry": false}}
```

- `message` is a plain sentence a user can read; the frontend shows it with a Retry button when `retry` is true.
- The full cause (traceback, stderr) goes to the log file (`%LOCALAPPDATA%\schemagen\logs\schemagen.log`, or
  `~/.local/state/schemagen/logs/` elsewhere), never to the response.
- Codes used: `no-project`, `bad-request`, `not-found`, `import-failed`, `graphviz-missing`, `render-failed`,
  `sim-failed`, `internal`.

## Session and projects

`schemagen app` may start with no project: the frontend then shows the start screen.

| method | path | body | returns |
|---|---|---|---|
| GET | `/api/health` | | `{ready, version, graphviz: {found, version, message}}` |
| GET | `/api/session` | | `{project: ProjectInfo \| null, recent: [{name, path, opened}], tour_done, theme}` |
| POST | `/api/settings` | `{tour_done?, theme?: "light"\|"dark"}` | `{ok: true}` (stored in the user settings file, not the project) |
| POST | `/api/open` | `{path}` or `{example: true}` | `Workspace` |
| POST | `/api/import` | multipart, field `file` (.xlsx or .csv) | `Workspace` |
| GET | `/api/workspace` | | `Workspace` of the open project (error `no-project` if none) |

- `{example: true}` copies the shipped example (`examples/aircraft`) to the user's projects folder
  (`%LOCALAPPDATA%\schemagen\projects\Example aircraft`) the first time and opens that copy, since the install folder is
  read-only and edits write change sets.
- `/api/import` makes a project folder next to the example (named after the file), copies the sheet in, writes a
  `schemagen.yml` that points at it (readable layout detected by the existing importer) and opens it. Import problems
  are findings in `Workspace.issues`, never an error, unless the file cannot be read at all (`import-failed`).

## Workspace (everything the main screen needs, in one call)

```ts
interface Workspace {
  project: ProjectInfo;          // {name, root, version, warnings: string[]}
  components: Node[];            // every component except splices (they fold into edges)
  edges: Edge[];                 // wires bundled per component pair
  conductors: Wire[];            // every wire
  issues: Issue[];
  zones: {id: string; name: string; members: string[]}[];   // subsystem (else zone) groups for the soft regions
  positions: Record<string, [number, number]>;              // user-dragged positions, by component id
  sources: Source[];             // sources added in the app (see below)
  palette: Record<string, string>;  // function class -> hex
}
interface Node { id: string; name: string; kind: string; zone: string; subsystem: string; pins: number;
                 rank: number;   // power-flow column: 0 sources, 1 protection, 2 buses, 3 harness connectors, 4 loads
                 sev: "" | "error" | "warning" | "info" }
interface Edge { id: string; a: string; b: string; wires: string[]; cls: string[]; label: string }  // a -> b in power order; label e.g. "3 × 14 V"
interface Wire { id: string; label: string; name: string; from: string; to: string;   // display text "Device conn pin"
                 a: string; b: string;                                                  // component ids at each end (after splices)
                 gauge: string; voltage: string; current: number | null; cls: string; hex: string;
                 length: number | null; harness: string; protection: string; status: string; notes: string;
                 sev: "" | "error" | "warning" | "info" }
interface Issue { k: number; rule: string; severity: "error" | "warning" | "info"; title: string;  // short plain sentence
                  message: string; fix: string; objects: string[] }
```

## Cards (popup)

| method | path | returns |
|---|---|---|
| GET | `/api/card/component/{id}` | `{id, name, kind, location, rating_A, connectors: [{id, pins: [{pin, wire, wire_label, name, other, gauge}]}], issues: Issue[], sim?: OverlayItem}` |
| GET | `/api/card/wire/{id}` | `{id, label, name, from, to, gauge, voltage, current, length, colour, hex, harness, protection, status, notes, issues: Issue[], sim?: OverlayItem}` |
| POST | `/api/component/{id}` | body `{name?, kind?, rating_A?}` → `Workspace`; stored as a change set |
| POST | `/api/wire/{id}` | body `{label?, name?, gauge?, current?, notes?}` → `Workspace`; stored as a change set |
| POST | `/api/positions` | body `{positions: {id: [x, y]}}` → `{ok}`; stored in `<project>/layout.json` (view state, not wire data) |

## Simulate

| method | path | body | returns |
|---|---|---|---|
| POST | `/api/simulate` | `{}` | `Overlay` |

Runs the DC operating point with sources and loads inferred where part data is missing (and the app-added sources).

```ts
interface Overlay {
  ok: boolean;                   // false while any bus that has loads is unpowered, or any error item exists
  summary: {problems: number; trips: number; unpowered: number; text: string;   // text e.g. "3 problems, 0 trips, 1 unpowered bus"
            groups: {title: string; objects: string[]; status: "ok" | "warn" | "error"}[]};  // one per root cause; problems = groups.length
  buses: {id: string; voltage_V: number; nominal_V: number | null; powered: boolean}[];
  breakers: {id: string; current_A: number; rating_A: number | null; loading: number | null; trips: boolean}[];
  items: Record<string, OverlayItem>;   // key "component:ID" or "conductor:ID"; only objects with something to say
  assumptions: string[];
}
interface OverlayItem { status: "ok" | "warn" | "error"; reason: string }  // reason: one line, e.g. "22 AWG is too small for 10 A breaker CB-AV (max 5 A)"
```

Problems are counted as groups, one per root cause: a wire and the breaker it does not fit; a bus with no source together
with the loads that lack supply only because of it ("no supply: Cabin bus has no source"); a trip. The text adds
", K unpowered bus(es)" only when K > 0; an unpowered bus is also one of the problems.

Flags (status and reason): wire too small for its breaker or current (error); wire far heavier than needed (warn: the gauge two
steps thinner would still be allowed for its breaker, or for its current times `heavy_margin` when unprotected);
breaker oversized for its wire (error) or undersized for its load (warn/error); component below its minimum voltage
(error); breaker trips (error); bus with loads and no source (error).

## Sources added in the app

| method | path | body | returns |
|---|---|---|---|
| POST | `/api/sources` | `{attach: "component id", type: "battery"\|"dcdc"\|"bench", nominal_V, r_int_ohm?, i_limit_A?, capacity_Ah?, name?}` | `Workspace` |
| DELETE | `/api/sources/{id}` | | `Workspace` |

`Source = {id, name, attach, type, nominal_V, r_int_ohm, i_limit_A, capacity_Ah}`. Stored as a change set (so it lives in
the project folder and survives reloads) and used by `/api/simulate`. It appears in `Workspace.components` with `rank 0`.

## Export

| method | path | body | returns |
|---|---|---|---|
| POST | `/api/export` | `{kind: "drawings"\|"pinout"\|"faults"\|"wirelist"}` | `{folder, files: string[]}` |
| POST | `/api/reveal` | `{path}` | `{ok}`: opens the folder in the file manager |

Drawings need Graphviz; without it the answer is the `graphviz-missing` error. The diagram never needs Graphviz.

## Kept from 0.7

`/api/index`, `/api/object`, `/api/graph`, `/api/edit`, `/api/undo`, `/api/sim/*`, `/api/drawings*`, `/api/diff` stay
for the CLI tests and power users; the 1.0 frontend does not call them.
