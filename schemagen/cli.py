"""schemagen command line.

    schemagen draw path/to/schemagen.yml                 # the project's default harnesses
    schemagen draw path/to/schemagen.yml X-FW X-WL     # chosen harness connectors
    schemagen draw path/to/schemagen.yml --all           # every harness connector the project knows
    schemagen draw path/to/schemagen.yml --no-render     # YAML/CSV/checks only, no WireViz/Graphviz needed
"""
import argparse, csv

from . import __version__
from .cards import Cards
from .config import load_config
from .drawing import build
from .net import Net
from .outputs import render, write_checks, write_continuity, write_cutlist, write_index, write_yaml
from .project import Project


def read_lengths(path):
    """Optional <out>/lengths.csv with columns label,length_m."""
    if not path.exists(): return {}
    with open(path, encoding="utf-8") as fh:
        return {r["label"].strip(): float(r["length_m"]) for r in csv.DictReader(fh) if r.get("length_m")}


def draw(cfg_path, harnesses=(), all_=False, no_render=False, out=None):
    cfg = load_config(cfg_path)
    if out: cfg.out = out
    cfg.out.mkdir(parents=True, exist_ok=True)
    pr = Project(cfg)
    targets = list(pr.dsp.HARNESS) if all_ else (list(harnesses) or cfg.default_harnesses or list(pr.dsp.HARNESS))
    net, cards, lengths = Net(pr), Cards(cfg.cards, cfg.cardmap), read_lengths(cfg.out / "lengths.csv")
    drawings = []
    for H in targets:
        dr = build(pr, net, cards, H, lengths)
        yml = cfg.out / f"{H}.yml"
        write_yaml(yml, dr.doc)
        if not no_render: render(yml, cfg.out, H)
        write_cutlist(pr, cfg.out / f"{H}_cutlist.csv", dr, lengths)
        write_continuity(pr, cfg.out / f"{H}_continuity.csv", dr)
        write_checks(cfg.out / f"{H}_checks.txt", dr)
        drawings.append(dr)
        print(f"{H}: {len(dr.ends)} wires, {len(dr.doc['cables'])} bundles, {len(dr.doc['connectors'])} connectors, "
              f"{len(dr.checks)} check finding(s)")
    write_index(pr, cfg.out, drawings)
    print(f"output in {cfg.out}")
    return drawings


def main(argv=None):
    ap = argparse.ArgumentParser(prog="schemagen", description="Wire list to harness drawings, cut lists and test sheets.")
    ap.add_argument("--version", action="version", version=f"schemagen {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw", help="render harness drawings and their extras")
    d.add_argument("config", help="schemagen.yml (or the folder that holds it)")
    d.add_argument("harness", nargs="*", help="harness connector ids, e.g. X-FW X-WL")
    d.add_argument("--all", action="store_true", help="all harness connectors")
    d.add_argument("--no-render", action="store_true", help="skip WireViz (YAML, CSV and checks only)")
    a = ap.parse_args(argv)
    if a.cmd == "draw": draw(a.config, a.harness, a.all, a.no_render)


if __name__ == "__main__":
    main()
