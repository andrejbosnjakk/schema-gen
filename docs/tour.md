# Tour hooks (1.0)

The contract between the main screen (stream B) and the quickstart tour (stream D, `frontend/src/tour/`).

- B renders `<Tour />` once at the root of the app and calls `startTour()` from the help menu ("Replay the tour").
  On first launch, after "Open the example project", B calls `startTour()` when `/api/session` says `tour_done: false`.
  D stores completion or skip with `POST /api/settings {tour_done: true}`.
- B puts these `data-tour` attributes on the controls (one element each):
  `diagram` (the React Flow wrapper), `fit` (fit-to-screen button), `node` (the first component card on the diagram,
  also on every card via `data-tour-node="ID"`), `card` (the popup dialog), `issues` (the Issues panel),
  `wires` (the Wires drawer handle), `simulate` (Simulate button), `add-source` (+ Source button),
  `import` (Import button), `help` (help menu button).
- B dispatches `window.dispatchEvent(new CustomEvent("schemagen:action", {detail: {action}}))` with `action` one of:
  `zoom` (any zoom or pan by the user), `card-open`, `card-close`, `issue-click`, `wires-open`, `wire-click`,
  `simulate-done`, `simulate-clear`, `source-added`, `import-start`, `import-done`, `example-open`.
  A click on a Wires row sends `wire-click` and selects the wire; it no longer opens a card (the row's label does).
  The tour advances a step when the action it asks for arrives.
- Tour library: driver.js (MIT).

## Steps

Eight steps on the example project (`examples/aircraft`, the fictional Kestrel E2; its three mistakes are in
`examples/aircraft/README.md`). Each step points at one `data-tour` element and advances when its action arrives; every
step also has Next / Skip tour. The texts name the example's real findings, so a change to the example's mistakes
must change them too (tests/test_example_aircraft.py pins the ids). The texts promise only what the screen shows.

| # | target | title | text | advances on |
|---|---|---|---|---|
| 1 | `diagram` | Your whole system, one picture | This is the Kestrel E2's wiring, grouped by subsystem. Scroll to zoom and drag to pan. | `zoom` |
| 2 | `[data-tour-node="CB-XPDR"]` (fallback `node`) | Click a component | Click the XPDR breaker. Its card lists the wire on each of its pins. | `card-open` |
| 3 | `card` | Everything about one part | The card shows what is wrong with this part, then its pins and the wire on each. Close it when you are done. | `card-close` |
| 4 | `issues` | What is wrong | The Issues list found three errors: a wire too thin for its breaker, a breaker too big for its wire, and a bus with no power source. Click one to find it on the diagram. Esc clears it. | `issue-click` |
| 5 | `wires` (the open drawer) | The sheet you know | Every row of your sheet is here, with W045 marked. Click a row to see that wire on the diagram. Click its label to open its card. | `wire-click` |
| 6a | `simulate` | Does it work with power on? | Press Simulate to switch the power on. | `simulate-done` (then 6b) |
| 6b | `sim-summary` | What the simulation shows | Each bus card now shows its voltage, and the bars on the breakers show how loaded they are. The cabin bus is red at 0 V: nothing feeds it, so the cabin light, USB charger and cabin fan stay dark. Press Next. | Next only |
| 7a | `add-source` | Try a fix | Click + Source, then click the cabin bus to add a battery to it. Your sheet is not changed. | `source-added` (then 7b) |
| 7b | `simulate` | Press Simulate again | The new source is wired to the cabin bus. Simulate again to see the result. | `simulate-done` (then 7c) |
| 7c | `sim-summary` | The cabin bus has power | The cabin bus now shows its voltage and is no longer red, so its loads come on. Press Next. | Next only |
| 8 | `import` | Now your own wiring | Import your own wire sheet (.xlsx or .csv) and the same diagram, issues and simulation are made from it. Replay this tour from the help menu. | `import-start` or Done |

- Steps 6 and 7 have phases (a, b, c) inside one step: the counter stays "6 of 8" / "7 of 8", the popover re-anchors when
  a phase's action arrives, and the last phase waits for Next. Next in an earlier phase skips to the next step.
- Whenever the tour moves to a new step, the app closes any open card or dialog first (the tour asks with
  `window.dispatchEvent(new CustomEvent("schemagen:tour", {detail: {what: "close"}}))`; the card step is the exception).
  Step 5's `enter` asks `{what: "show-wire", arg: "W045"}`: the drawer opens, scrolls to that row and marks it
  (selects it, zooms to it). Neither request sends an action event.
- The tour steps aside (`source-pick`) while a source is placed and comes back on `source-pick-end` (added, or Esc).
- Step 2 needs B to put `data-tour-node="CB-XPDR"` on that card (it does for every card); if the node is off screen the
  tour first fits the view.
- Step 6's numbers come from the simulation of the example as shipped (main bus 13.39 V, essential bus 13.29 V, cabin
  bus 0 V); they hold while the cards in `examples/aircraft/cards` are unchanged.
- A step whose target is missing is skipped and the counter shrinks ("1 of 7"); Next and Skip tour always work.
- Clicking the logo (back to the start screen) ends the tour without recording it as seen.
- `e2e/tour.spec.ts` walks the tour with the real actions (real server); `e2e/fixes.spec.ts` walks it against the mock;
  screenshots are in `docs/screens/7-tour/`.
