"""Files next to each drawing: cut list, continuity/insulation test sheet, checks, footnotes and the index page."""
import csv, html, json, re, shutil, subprocess
from collections import defaultdict
from importlib.resources import files

import yaml


def write_yaml(path, doc):
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")


def render(yml, out, name):
    """Render with the WireViz command-line tool. WireViz is GPL-3.0: it runs as a separate program, never imported."""
    exe = shutil.which("wireviz")
    if not exe: raise SystemExit("wireviz command not found: pip install wireviz==0.4.1 (and Graphviz), or use --no-render")
    r = subprocess.run([exe, "-f", "hpst", "-o", str(out), "-O", name, str(yml)], capture_output=True, text=True)
    if r.returncode: raise SystemExit(f"wireviz failed on {yml}:\n{r.stderr or r.stdout}")


def add_footnotes(page, dr):
    """Append the footnote table (full continuation and net ends) to WireViz's HTML page of a drawing."""
    if not dr.footnotes or not page.exists(): return
    rows = "".join(f"<tr><td>[{n}]</td><td><b>{html.escape(l)}</b></td><td>{html.escape(t)}</td></tr>" for n, l, t in dr.footnotes)
    block = (f'<div id="notes"><h2>Continues at</h2><table style="border-collapse:collapse;font-size:12px" border="1" cellpadding="3">'
             f"<tr><th>#</th><th>wire</th><th>next wires (place) | net ends</th></tr>{rows}</table></div>")
    s = page.read_text(encoding="utf-8")
    page.write_text(s.replace("</body>", block + "</body>", 1) if "</body>" in s else s + block, encoding="utf-8")


def _end(pr, w, e):
    d = w[f"p{e}"]
    return pr.device(d), pr.terminal(d, w[f"p{e}c"], w[f"p{e}p"])


def _term(pr, t):
    d, c, p = t
    return pr.device(d), pr.terminal(d, c, p)


def write_cutlist(pr, path, dr, lengths):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        cw = csv.writer(fh)
        cw.writerow(["label", "wire id", "name", "bundle", "from", "from terminal", "to", "to terminal",
                     "gauge", "colour", "function class", "length_m", "status", "continues at"])
        for w, e, f, sd in sorted(dr.ends, key=lambda t: t[0]["label"]):
            a, at = _end(pr, w, 1); b, bt = _end(pr, w, 2)
            cw.writerow([w["label"], w["id"], w["name"], w.get("_cable", ""), a, at, b, bt, w["gauge"], w["color"], w["kind"],
                         lengths.get(w["label"], "TBD"), w.get("st", ""), w.get("_cont", "")])


def pin_key(s):
    return (not s.isdigit(), int(s) if s.isdigit() else 0, s)


def _pins(keys):
    return sorted(keys, key=pin_key)


def write_continuity(pr, net, path, dr):
    """Tests between reachable terminals only (connector pins, studs, device pins): splices are sleeved, so a test
    walks through them. Three levels: each connector half to its equipment (unmated), end to end through the mated
    connector, and pin-to-pin insulation (pins tied on purpose through a splice are excepted)."""
    X = dr.designator
    hdev = dr.ends[0][0][f"p{dr.ends[0][1]}"] if dr.ends else ""
    same = lambda t: pr.role(t[0]) == "harness" and t[0].startswith(dr.code)  # another pin of this connector
    reach = defaultdict(lambda: {"near": [], "far": []})  # pin -> side -> [(terminal, labels)]
    halfname = {}
    for w, e, f, sd in dr.ends:
        p = w[f"p{e}p"]
        halfname[(p, sd)] = w[f"p{e}c"]
        reach[p][sd] += net.reach(w, f)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        cw = csv.writer(fh)
        cw.writerow(["#", "test", "wire(s)", "from", "from terminal", "to", "to terminal", "expected", "result ☐", "remarks"])
        i, tied = 0, defaultdict(set)
        for p in _pins(reach):
            for sd in ("near", "far"):
                for t, path in reach[p][sd]:
                    if same(t):
                        tied[p].add(t[2])
                        if pin_key(t[2]) < pin_key(p): continue  # tied pair already listed from the lower pin
                    i += 1
                    b, bt = (X, pr.terminal(*t)) if same(t) else _term(pr, t)
                    cw.writerow([i, "connector half to equipment (unmated)", " + ".join(path), X,
                                 pr.terminal(hdev, halfname[(p, sd)], p), b, bt, "continuity", "☐",
                                 "tied pin (same splice)" if same(t) else ""])
        for p in _pins(reach):
            nr = [x for x in reach[p]["near"] if not same(x[0])]
            fr = [x for x in reach[p]["far"] if not same(x[0])]
            for (tn, pn) in nr:
                for (tf, pf) in fr:
                    i += 1
                    a, at = _term(pr, tn); b, bt = _term(pr, tf)
                    par = sorted(tied[p], key=pin_key)
                    cw.writerow([i, f"end to end through {X} pin {p} (mated)", " + ".join(pn[::-1] + pf), a, at, b, bt,
                                 "continuity", "☐", f"parallel with pin {', '.join(par)}: proves the group, not each contact "
                                 "(the unmated tests do)" if par else ""])
        for p in _pins(reach):
            ex = sorted(tied[p], key=pin_key)
            i += 1
            to = "all other pins + shell" + (f", except pin {', '.join(ex)} (same splice)" if ex else "")
            cw.writerow([i, f"isolation {X} pin {p} (mated, harness ends disconnected from equipment)", "", X, f"pin {p}", X,
                         to, "no continuity (insulation)", "☐", "tied pins must show continuity" if ex else ""])


def write_checks(path, dr):
    path.write_text("\n".join(dr.checks) + "\n" if dr.checks else "no findings\n", encoding="utf-8")


def write_index(pr, out, sets):
    """sets: [(full drawing, [rendered drawings])]."""
    cards, data, svgs, notes = [], [], {}, {}
    for full, parts in sets:
        H = full.harness
        link = lambda name, ext: f'<a href="{name}{ext}">{ext.lstrip("._")}</a>'
        draw_links = "<br>".join(f'{html.escape(d.harness)}: ' + " · ".join(link(d.harness, e) for e in (".svg", ".png", ".html", ".bom.tsv", ".yml"))
                                 for d in parts)
        cards.append(f'<div class="card"><b>{html.escape(H)}</b> <small>{html.escape(full.name)}</small><br>{len(full.ends)} wires · '
                     f'{len(full.checks)} check finding(s)<br>{draw_links}<br>'
                     + " · ".join(link(H, e) for e in ("_cutlist.csv", "_continuity.csv", "_checks.txt")) + "</div>")
        for d in parts:
            svg = out / f"{d.harness}.svg"
            svgs[d.harness] = re.sub(r"^.*?(<svg)", r"\1", svg.read_text(encoding="utf-8"), flags=re.S) if svg.exists() else ""
            notes[d.harness] = d.footnotes
            for w, e, f, sd in d.ends:
                a, at = _end(pr, w, 1); b, bt = _end(pr, w, 2)
                data.append({"label": w["label"], "id": w["id"], "harness": d.harness, "bundle": w.get("_cable", ""), "from": f"{a}, {at}",
                             "to": f"{b}, {bt}", "gauge": w["gauge"], "colour": w["color"], "func": w.get("func", ""), "cont": w.get("_cont", "")})
    js = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    page = (files("schemagen").joinpath("templates/index.html").read_text(encoding="utf-8")
            .replace("__CARDS__", "".join(cards)).replace("__DATA__", js(data)).replace("__SVGS__", js(svgs))
            .replace("__NOTES__", js(notes)))
    (out / "index.html").write_text(page, encoding="utf-8")
