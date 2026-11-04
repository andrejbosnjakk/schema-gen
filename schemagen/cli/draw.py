"""`schemagen draw`: harness drawings (per harness connector, split when wide), interface drawings for every
conductor no harness drawing reaches, cut lists, test sheets, checks, the coverage report and the index page."""
import json
import sys

from ..importers.cards import Cards
from ..core.config import load_config
from ..core.load import measured_lengths
from ..renderers.harness import build_set
from ..renderers.wirenet import Net
from ..exporters.documents import add_footnotes, write_checks, write_continuity, write_cutlist, write_index, write_yaml
from ..renderers.project import Project
from ..renderers import interface
from ..renderers.wireviz import render_many


def read_lengths(path):
    """Optional lengths.csv with columns label,length_m (0.2 helper)."""
    import csv
    if not path.exists(): return {}
    with open(path, encoding="utf-8") as fh:
        return {r["label"].strip(): float(r["length_m"]) for r in csv.DictReader(fh) if r.get("length_m")}


def coverage(pr, drawings):
    """{total, covered, uncovered: [labels], drawings: {name: [labels]}} from what the drawings hold."""
    per = {d.harness: sorted({w["label"] for w, *_ in d.ends}) for d in drawings}
    ids = {w["_i"] for d in drawings for w, *_ in d.ends}
    unc = [w["label"] for w in pr.wires if w["_i"] not in ids]
    return dict(total=len(pr.wires), covered=len(ids), uncovered=unc, drawings=per)


def draw(cfg_path, harnesses=(), all_=False, no_render=False, out=None, split=None, interfaces=True):
    from pathlib import Path
    cfg = load_config(cfg_path)
    if out: cfg.out = Path(out)
    cfg.out.mkdir(parents=True, exist_ok=True)
    pr = Project(cfg)
    for w in pr.warnings: print("warning:", w, file=sys.stderr)
    targets = list(pr.dsp.HARNESS) if all_ else (list(harnesses) or cfg.default_harnesses or list(pr.dsp.HARNESS))
    net, cards, lengths = Net(pr), Cards(cfg.cards, cfg.cardmap), measured_lengths(cfg)
    sets, rendered = [], []
    for H in targets:
        full, parts = build_set(pr, net, cards, H, lengths, split or cfg.split.get(H, cfg.split_default))
        for d in parts:
            write_yaml(cfg.out / f"{d.harness}.yml", d.doc); rendered.append(d)
        write_cutlist(pr, cfg.out / f"{H}_cutlist.csv", full, lengths)
        write_continuity(pr, net, cfg.out / f"{H}_continuity.csv", full)
        write_checks(cfg.out / f"{H}_checks.txt", full)
        sets.append((full, parts))
        print(f"{H}: {len(full.ends)} wires, drawings: {', '.join(d.harness for d in parts)}, {len(full.checks)} check finding(s)")
    if interfaces:
        covered = {w["_i"] for d in rendered for w, *_ in d.ends}
        ifs = interface.build_all(pr, net, cards, covered)
        for d in ifs:
            write_yaml(cfg.out / f"{d.harness}.yml", d.doc); rendered.append(d); sets.append((d, [d]))
        if ifs: print(f"interface drawings: {len(ifs)} for {sum(len(d.ends) for d in ifs)} wires outside the harness drawings")
    if not no_render:
        render_many([cfg.out / f"{d.harness}.yml" for d in rendered], cfg.out)
        for d in rendered: add_footnotes(cfg.out / f"{d.harness}.html", d)
    cov = coverage(pr, rendered)
    (cfg.out / "coverage.json").write_text(json.dumps(cov, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (cfg.out / "coverage.txt").write_text(
        f"{cov['covered']} of {cov['total']} conductors in a drawing ({100 * cov['covered'] / max(cov['total'], 1):.1f} %)\n"
        + "".join(f"not drawn: {x}\n" for x in cov["uncovered"]), encoding="utf-8")
    write_index(pr, cfg.out, sets)
    print(f"coverage: {cov['covered']}/{cov['total']} conductors in a drawing")
    print(f"output in {cfg.out}")
    return sets
