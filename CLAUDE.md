# schema-gen: notes for Claude sessions

- Python package `schemagen` (repo `schema-gen`). CLI: `schemagen draw <project dir or schemagen.yml>`.
- Run `pytest` before committing; `schemagen draw examples/demo` must render (needs Graphviz `dot`).
- The tool is general-purpose. Real project wire lists are private and must **not** be committed here; only the
  fictional `examples/demo` project lives in this repo. Project-specific rules belong in the project's
  `schemagen.yml` (or its display.py), never in the code.
- Wire colours: never use orange (`OG`) for LV wires by default; it is the usual HV colour. 24 V is yellow.
- `net.py` is the core model (drawings, test sheets and the planned simulation all read from it). Keep breakers
  and switches out of the union-find: they are elements, not connections.
- Renderer: WireViz 0.4.1 (pinned), GPL-3.0: run it only as the `wireviz` command (outputs.render), never import it;
  a test enforces this. Emit plain WireViz YAML so the renderer stays replaceable.
- Continuity tests go between reachable terminals (connector pins, studs, device pins), never from a splice.
- One palette (`colours` in schemagen.yml) for every output; other tools read it via `schemagen palette`.
- Style: compact code that matches the existing modules; short docstrings saying what a function is for.
