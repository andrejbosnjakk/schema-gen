# schema-gen: notes for Claude sessions

- Python package `schemagen` (repo `schema-gen`). CLI: `schemagen draw <project dir or schemagen.yml>`.
- Run `pytest` before committing; `schemagen draw examples/demo` must render (needs Graphviz `dot`).
- Aircraft wire-list data (AeroDelft) is private and must **not** be committed here. Only the fictional
  `examples/demo` project lives in this repo. Project-specific rules belong in the project's `schemagen.yml`,
  not in the code.
- Wire colours: never use orange (`OG`) for LV wires; it is the HV colour in the aircraft. 24 V is yellow.
- `net.py` is the core model (drawings, test sheets and the planned simulation all read from it). Keep breakers
  and switches out of the union-find: they are elements, not connections.
- Renderer: WireViz 0.4.1 (pinned). Emit plain WireViz YAML so the renderer stays replaceable.
- Style: compact code that matches the existing modules; short docstrings saying what a function is for.
