"""Files next to each drawing: cut list, continuity/insulation test sheet, checks, and the index page."""
import csv, html, json, re
from collections import defaultdict
from importlib.resources import files

import yaml


def write_yaml(path, doc):
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")


def render(yml, out, name):
    from wireviz.wireviz import parse  # imported late so --no-render works without WireViz/Graphviz
    parse(yml, output_formats=("svg", "png", "html", "tsv"), output_dir=out, output_name=name)


def _end(pr, w, e):
    d = w[f"p{e}"]
    return pr.device(d), pr.terminal(d, w[f"p{e}c"], w[f"p{e}p"])


def write_cutlist(pr, path, dr, lengths):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        cw = csv.writer(fh)
        cw.writerow(["label", "wire id", "name", "bundle", "from", "from terminal", "to", "to terminal",
                     "gauge", "colour", "function class", "length_m", "status", "continues at"])
        for w, e, f, sd in sorted(dr.ends, key=lambda t: t[0]["label"]):
            a, at = _end(pr, w, 1); b, bt = _end(pr, w, 2)
            cw.writerow([w["label"], w["id"], w["name"], w.get("_cable", ""), a, at, b, bt, w["gauge"], w["color"], w["kind"],
                         lengths.get(w["label"], "TBD"), w.get("st", ""), w.get("_cont", "")])


def _pins(keys):
    return sorted(keys, key=lambda s: (not s.isdigit(), int(s) if s.isdigit() else 0, s))


def write_continuity(pr, path, dr):
    X = dr.designator
    with open(path, "w", newline="", encoding="utf-8") as fh:
        cw = csv.writer(fh)
        cw.writerow(["#", "test", "label(s)", "from", "from pin", "to", "to pin", "expected", "result ☐", "remarks"])
        i = 0
        for w, e, f, sd in sorted(dr.ends, key=lambda t: t[0]["label"]):
            i += 1
            a, at = _end(pr, w, 1); b, bt = _end(pr, w, 2)
            cw.writerow([i, "wire (connector unmated)", w["label"], a, at, b, bt, "continuity", "☐", ""])
        bypin = defaultdict(dict)
        for w, e, f, sd in dr.ends: bypin[w[f"p{e}p"]][sd] = (w, f)
        for p in _pins(bypin):
            if len(bypin[p]) < 2: continue
            (wn, fn), (wf, ff) = bypin[p]["near"], bypin[p]["far"]
            i += 1
            a, at = _end(pr, wn, fn); b, bt = _end(pr, wf, ff)
            cw.writerow([i, f"end to end through {X} pin {p} (mated)", f"{wn['label']} + {wf['label']}", a, at, b, bt,
                         "continuity", "☐", ""])
        # pins tied together inside the harness (same splice) are continuous on purpose
        spl = defaultdict(set)
        for w, e, f, sd in dr.ends:
            if pr.role(w[f"p{f}"]) == "splice": spl[w[f"p{f}"]].add(w[f"p{e}p"])
        for p in _pins(bypin):
            tied = sorted({q for g in spl.values() if p in g for q in g} - {p}, key=lambda s: int(s) if s.isdigit() else 999)
            i += 1
            to = "all other pins + shell" + (f", except pin {', '.join(tied)} (same splice)" if tied else "")
            cw.writerow([i, f"isolation {X} pin {p} (mated, harness ends disconnected from equipment)", "", X, f"pin {p}", X,
                         to, "no continuity (insulation)", "☐", "tied pins must show continuity" if tied else ""])


def write_checks(path, dr):
    path.write_text("\n".join(dr.checks) + "\n" if dr.checks else "no findings\n", encoding="utf-8")


def write_index(pr, out, drawings):
    cards, data, svgs = [], [], {}
    for dr in drawings:
        H = dr.harness
        link = lambda ext: f'<a href="{H}{ext}">{ext.lstrip("._")}</a>'
        cards.append(f'<div class="card"><b>{html.escape(H)}</b> <small>{html.escape(dr.name)}</small><br>{len(dr.ends)} wires · '
                     f'{len(dr.checks)} check finding(s)<br>'
                     + " · ".join(link(e) for e in (".svg", ".png", ".html", ".bom.tsv", "_cutlist.csv", "_continuity.csv", "_checks.txt", ".yml"))
                     + "</div>")
        svg = out / f"{H}.svg"
        svgs[H] = re.sub(r"^.*?(<svg)", r"\1", svg.read_text(encoding="utf-8"), flags=re.S) if svg.exists() else ""
        for w, e, f, sd in dr.ends:
            a, at = _end(pr, w, 1); b, bt = _end(pr, w, 2)
            data.append({"label": w["label"], "id": w["id"], "harness": H, "bundle": w.get("_cable", ""), "from": f"{a}, {at}",
                         "to": f"{b}, {bt}", "gauge": w["gauge"], "colour": w["color"], "func": w.get("func", ""), "cont": w.get("_cont", "")})
    js = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    page = (files("schemagen").joinpath("templates/index.html").read_text(encoding="utf-8")
            .replace("__CARDS__", "".join(cards)).replace("__DATA__", js(data)).replace("__SVGS__", js(svgs)))
    (out / "index.html").write_text(page, encoding="utf-8")
