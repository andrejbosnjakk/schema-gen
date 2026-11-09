"""schemagen command line. `<project>` is a schemagen.yml or the folder that holds it.

    schemagen draw <project> [X-BH ...] [--all] [--split none|side|function|auto] [--no-render] [--no-interfaces]
    schemagen check <project> [--format text|json|sarif] [-o FILE]
    schemagen fix direction <project> [--apply]
    schemagen export <project> -o wires.xlsx | DIR | wires.csv | model.json
    schemagen pinout <project> [-o out/pinout.xlsx] [--page-breaks]   (also writes .html)
    schemagen wirelist <project> -o wirelist.xlsx
    schemagen template [<project>] -o sheet.xlsx
    schemagen labels <project> [--update] [--retire LABEL --reason TEXT]
    schemagen diff <A> <B> [--project DIR] [--format text|json|html] [-o FILE]   (A, B: folders or git revisions)
    schemagen changes <project> [--undo]
    schemagen sim <project> [scenario.yml ...] [--faults all] [--infer]
    schemagen app <project> [--port 8765]
    schemagen palette <project> [--json] | schema [-o schemas] | synth --wires N --seed S -o DIR
"""
import argparse, sys
from pathlib import Path

from .. import __version__, table
from ..exporters import palette
from ..core.config import load_config
from ..renderers.project import Project
from .draw import draw, read_lengths  # noqa: F401  (0.2 names)


def _project(p):
    pr = Project(load_config(p))
    for w in pr.warnings: print("warning:", w, file=sys.stderr)
    return pr


def main(argv=None):
    for s in (sys.stdout, sys.stderr):  # a Windows pipe is cp1252: print "?" for → and − rather than crash
        if hasattr(s, "reconfigure") and (s.encoding or "").lower().replace("-", "") != "utf8": s.reconfigure(errors="replace")
    ap =argparse.ArgumentParser(prog="schemagen", description="Wiring design from one source of truth: drawings, tables, checks, simulation.")
    ap.add_argument("--version", action="version", version=f"schemagen {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw", help="render harness and interface drawings and their extras")
    d.add_argument("config", help="schemagen.yml (or the folder that holds it)")
    d.add_argument("harness", nargs="*", help="harness connector ids, e.g. X-BH X-J2")
    d.add_argument("--all", action="store_true", help="all harness connectors")
    d.add_argument("--split", choices=["none", "side", "function", "auto"], help="split wide harnesses into parts")
    d.add_argument("--no-render", action="store_true", help="skip WireViz (YAML, CSV and checks only)")
    d.add_argument("--no-interfaces", action="store_true", help="no interface drawings for conductors outside the harness drawings")
    c = sub.add_parser("check", help="run the rules")
    c.add_argument("config"); c.add_argument("--format", choices=["text", "json", "sarif"], default="text"); c.add_argument("-o", "--output")
    c.add_argument("--rule", action="append", help="only these rule ids")
    f = sub.add_parser("fix", help="propose fixes as a reviewable change set")
    f.add_argument("what", choices=["direction", "names"]); f.add_argument("config")
    f.add_argument("--apply", action="store_true", help="store the change set in <project>/changes/ (applied on load)")
    e = sub.add_parser("export", help="write the project in the neutral table format or as JSON")
    e.add_argument("config"); e.add_argument("-o", "--output", required=True, help=".xlsx, a folder, .csv (wires only) or .json (model)")
    e.add_argument("--readable", action="store_true", help="the readable sheet layout (.xlsx): sections, headers, plain names")
    po = sub.add_parser("pinout", help="pinout per component and harness connector (XLSX and HTML)")
    po.add_argument("config"); po.add_argument("-o", "--output", help="default <out>/pinout.xlsx")
    po.add_argument("--page-breaks", action="store_true", help="start every component on a new printed page")
    wl = sub.add_parser("wirelist", help="readable wire list (XLSX) with the project's display names")
    wl.add_argument("config"); wl.add_argument("-o", "--output", required=True)
    t = sub.add_parser("template", help="the editable sheet: neutral workbook with dropdowns (works in Google Sheets)")
    t.add_argument("config", nargs="?"); t.add_argument("-o", "--output", required=True)
    lb = sub.add_parser("labels", help="label ledger: printed labels are never reused")
    lb.add_argument("config"); lb.add_argument("--update", action="store_true"); lb.add_argument("--retire"); lb.add_argument("--reason", default="")
    df = sub.add_parser("diff", help="added, removed and changed wires, pins, labels, protection and open items")
    df.add_argument("a"); df.add_argument("b", nargs="?", default=".", help="folder or git revision (default: the working tree)")
    df.add_argument("--project", default=".", help="project folder (for git revisions)")
    df.add_argument("--format", choices=["text", "json", "html"], default="text"); df.add_argument("-o", "--output")
    ch = sub.add_parser("changes", help="list or undo stored change sets")
    ch.add_argument("config"); ch.add_argument("--undo", action="store_true")
    sm = sub.add_parser("sim", help="DC simulation: scenarios and fault sweep (HTML + JSON report)")
    sm.add_argument("config"); sm.add_argument("scenarios", nargs="*", help="scenario YAML files (default: <project>/scenarios/*.yml)")
    sm.add_argument("--faults", choices=["all"], help="short every node to ground"); sm.add_argument("-o", "--output", help="report folder")
    sm.add_argument("--infer", action="store_true", help="assume sources (sim.sources) and loads (conductor current) missing from part data")
    a_ = sub.add_parser("app", help="the local app (browser UI)")
    a_.add_argument("config"); a_.add_argument("--port", type=int, default=8765); a_.add_argument("--host", default="127.0.0.1")
    a_.add_argument("--no-browser", action="store_true")
    p = sub.add_parser("palette", help="print the wire palette (function class -> colour)")
    p.add_argument("config"); p.add_argument("--json", action="store_true")
    y = sub.add_parser("synth", help="write a synthetic (fictional) project for tests and benchmarks")
    y.add_argument("--wires", type=int, default=1000); y.add_argument("--seed", type=int, default=1)
    y.add_argument("-o", "--output", required=True)
    y.add_argument("--readable", action="store_true", help="the readable sheet layout (seeded with typos and unreadable cells)")
    y.add_argument("--clean", action="store_true", help="with --readable: no seeded faults")
    sc = sub.add_parser("schema", help="write the JSON Schemas of the model")
    sc.add_argument("-o", "--output", default="schemas")
    a = ap.parse_args(argv)
    from . import commands
    if a.cmd == "draw":
        from ..renderers.wireviz import RenderError
        try: draw(a.config, a.harness, a.all, a.no_render, split=a.split, interfaces=not a.no_interfaces)
        except RenderError as e:
            if e.detail and e.code != "graphviz-missing": print(e.detail.rstrip(), file=sys.stderr)
            print(f"error: {e.message}" + (" Install it from graphviz.org (or set SCHEMAGEN_DOT), or use --no-render." if e.code == "graphviz-missing" else ""),
                  file=sys.stderr)
            return 1
    elif a.cmd == "check": return commands.check(a)
    elif a.cmd == "fix": return commands.fix(a)
    elif a.cmd == "export" and a.readable:
        from ..importers import readable
        L = commands._loaded(a.config); readable.export(L.model, Path(a.output))
        print(f"{len(L.model.conductors)} wires -> {a.output}")
    elif a.cmd == "export":
        pr = _project(a.config)
        for w in table.export(pr, Path(a.output)): print("warning:", w, file=sys.stderr)
        print(f"{len(pr.wires)} wires -> {a.output}")
    elif a.cmd == "pinout": commands.pinout(a)
    elif a.cmd == "wirelist": commands.wirelist(a)
    elif a.cmd == "template": commands.template(a)
    elif a.cmd == "labels": return commands.labels(a)
    elif a.cmd == "diff": return commands.diff(a)
    elif a.cmd == "changes": commands.changes(a)
    elif a.cmd == "sim": return commands.sim(a)
    elif a.cmd == "app": commands.app(a)
    elif a.cmd == "schema":
        import json
        from ..core.model import json_schemas
        out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
        for k, v in json_schemas().items(): (out / k).write_text(json.dumps(v, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"schemas -> {out}")
    elif a.cmd == "synth":
        if a.readable:
            from .. import synth_readable; synth_readable.main(a.wires, a.seed, a.output, a.clean)
        else:
            from .. import synth; synth.main(a.wires, a.seed, a.output)
    elif a.cmd == "palette": palette.write(load_config(a.config), "json" if a.json else "csv", sys.stdout)
    return 0


def run():
    sys.exit(main() or 0)


if __name__ == "__main__":
    run()
