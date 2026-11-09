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
  The tour advances a step when the action it asks for arrives.
- Tour library: driver.js (MIT).

## Steps

Eight steps on the example project (`examples/aircraft`, the fictional Kestrel E2; its three mistakes are in
`examples/aircraft/README.md`). Each step points at one `data-tour` element and advances when its action arrives; every
step also has Next / Skip tour. The texts name the example's real findings, so a change to the example's mistakes
must change them too (tests/test_example_aircraft.py pins the ids).

| # | target | title | text | advances on |
|---|---|---|---|---|
| 1 | `diagram` | Your whole system, one picture | This is the Kestrel E2's wiring: batteries and the DC-DC converter on the left, then breakers, buses, the firewall and wing-root connectors, and the loads. Scroll to zoom and drag to pan. | `zoom` |
| 2 | `[data-tour-node="CB-XPDR"]` (fallback `node`) | Click a component | Click the XPDR breaker. Its card shows every wire on it, with gauge and current. | `card-open` |
| 3 | `card` | Everything about one part | The XPDR breaker is 15 A, but the transponder draws 1.5 A through 20 AWG wire, which allows at most 7.5 A. Close the card when you are done. | `card-close` |
| 4 | `issues` | What is wrong | The Issues list found two errors: wire W045 is 22 AWG behind the 10 A landing-light breaker, and the 15 A XPDR breaker is too big for its wire. Click one to find it on the diagram. | `issue-click` |
| 5 | `wires` | The sheet you know | Every row of your sheet is here. Open the Wires drawer: W045, the landing-light switch feed, is marked red; its fix is 18 AWG. | `wires-open` |
| 6 | `simulate` | Does it work with power on? | Press Simulate. The main and essential buses sit near 13.4 V, but the cabin bus stays at 0 V: nothing feeds it, so the cabin light, USB charger and cabin fan stay dark. | `simulate-done` |
| 7 | `add-source` | Try a fix | Add a source to the cabin bus with + Source and simulate again to see its loads come on. Your sheet is not changed. | `source-added` |
| 8 | `import` | Now your own wiring | Import your own wire sheet (.xlsx or .csv) and the same diagram, issues and simulation are made from it. Replay this tour from the help menu. | `import-start` or Done |

- Step 2 needs B to put `data-tour-node="CB-XPDR"` on that card (it does for every card); if the node is off screen the
  tour first fits the view.
- Step 6's numbers come from the simulation of the example as shipped (main bus 13.39 V, essential bus 13.29 V, cabin
  bus 0 V); they hold while the cards in `examples/aircraft/cards` are unchanged.
