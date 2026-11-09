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
