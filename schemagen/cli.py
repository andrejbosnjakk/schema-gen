"""schemagen command line.

    schemagen draw path/to/schemagen.yml                 # the project's default harnesses
    schemagen draw path/to/schemagen.yml X-BH X-J2       # chosen harness connectors
    schemagen draw path/to/schemagen.yml --all           # every harness connector the project knows
    schemagen draw path/to/schemagen.yml --split side    # none | side | function | auto (default: per project config)
    schemagen draw path/to/schemagen.yml --no-render     # YAML/CSV/checks only, no WireViz/Graphviz needed
    schemagen export path/to/schemagen.yml -o wires.csv  # the wire list in the neutral table format (.csv or .json)
    schemagen palette path/to/schemagen.yml --json       # the wire palette, for other tools
"""
import argparse, csv, sys
from pathlib import Path

from . import __version__, palette, table
from .cards import Cards
from .config import load_config
from .drawing import build_set
from .net import Net
from .outputs import add_footnotes, render, write_checks, write_continuity, write_cutlist, write_index, write_yaml
from .project import Project


def read_lengths(path):
    """Optional <out>/lengths.csv with columns label,length_m."""
    if not path.exists(): return {}
    with open(path, encoding="utf-8") as fh:
        return {r["label"].strip(): float(r["length_m"]) for r in csv.DictReader(fh) if r.get("length_m")}


def draw(cfg_path, harnesses=(), all_=False, no_render=False, out=None, split=None):
    cfg = load_config(cfg_path)
    if out: cfg.out = Path(out)
    cfg.out.mkdir(parents=True, exist_ok=True)
    pr = Project(cfg)
    targets = list(pr.dsp.HARNESS) if all_ else (list(harnesses) or cfg.default_harnesses or list(pr.dsp.HARNESS))
    net, cards, lengths = Net(pr), Cards(cfg.cards, cfg.cardmap), read_lengths(cfg.out / "lengths.csv")
    sets = []
    for H in targets:
        full, parts = build_set(pr, net, cards, H, lengths, split or cfg.split.get(H, cfg.split_default))
        for d in parts:
            yml = cfg.out / f"{d.harness}.yml"
            write_yaml(yml, d.doc)
            if not no_render:
                render(yml, cfg.out, d.harness)
                add_footnotes(cfg.out / f"{d.harness}.html", d)
        write_cutlist(pr, cfg.out / f"{H}_cutlist.csv", full, lengths)
        write_continuity(pr, net, cfg.out / f"{H}_continuity.csv", full)
        write_checks(cfg.out / f"{H}_checks.txt", full)
        sets.append((full, parts))
        names = ", ".join(d.harness for d in parts)
        print(f"{H}: {len(full.ends)} wires, drawings: {names}, {len(full.checks)} check finding(s)")
    write_index(pr, cfg.out, sets)
    print(f"output in {cfg.out}")
    return sets


def main(argv=None):
    ap = argparse.ArgumentParser(prog="schemagen", description="Wire list to harness drawings, cut lists and test sheets.")
    ap.add_argument("--version", action="version", version=f"schemagen {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw", help="render harness drawings and their extras")
    d.add_argument("config", help="schemagen.yml (or the folder that holds it)")
    d.add_argument("harness", nargs="*", help="harness connector ids, e.g. X-BH X-J2")
    d.add_argument("--all", action="store_true", help="all harness connectors")
    d.add_argument("--split", choices=["none", "side", "function", "auto"], help="split wide harnesses into parts")
    d.add_argument("--no-render", action="store_true", help="skip WireViz (YAML, CSV and checks only)")
    e = sub.add_parser("export", help="write the wire list in the neutral table format")
    e.add_argument("config"); e.add_argument("-o", "--output", required=True, help=".csv or .json")
    p = sub.add_parser("palette", help="print the wire palette (function class -> colour)")
    p.add_argument("config"); p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "draw": draw(a.config, a.harness, a.all, a.no_render, split=a.split)
    elif a.cmd == "export":
        pr = Project(load_config(a.config)); table.export(pr, Path(a.output)); print(f"{len(pr.wires)} wires -> {a.output}")
    elif a.cmd == "palette": palette.write(load_config(a.config), "json" if a.json else "csv", sys.stdout)


if __name__ == "__main__":
    main()
