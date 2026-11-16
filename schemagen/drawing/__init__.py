"""schemagen's own wiring-diagram engine (docs/drawing-model.md): scope.py builds the scene, geometry.py holds the scene and
geometry contracts, verify.py rebuilds the netlist from them. The names below keep the 0.2 import path; that code lives in
schemagen.renderers.harness."""
from ..renderers.harness import Drawing, PARTS, build, build_set, clean_func, function_part, harness_ends, pin_order, pv, safe, split_mode  # noqa: F401
