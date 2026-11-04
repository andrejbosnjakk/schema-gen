"""Command handlers (argparse namespaces in, exit code out)."""
import difflib
import io
import json
import sys
from pathlib import Path

from ..core import changes as ch
from ..core import diff as df
from ..core import ledger
from ..core.config import load_config
from ..core.context import Ctx
from ..core.direction import analyse
from ..core.load import ledger_path, load, measured_lengths
from ..core.rules import RULES, run_rules


def _loaded(p, **kw):
    L = load(p, **kw)
    for w in L.warnings: print("warning:", w, file=sys.stderr)
    return L


def locate(L, issues):
    """Fill file/row of each issue from the first conductor it names."""
    where = {r.data.get("id"): r for r in L.records}
    for i in issues:
        for o in i.objects:
            if o.startswith("conductor:") and o[10:] in where:
                r = where[o[10:]]; i.file, i.row = r.file, r.row; break
    return issues


def sarif(issues, root):
    lv = {"error": "error", "warning": "warning", "info": "note"}
    rules = [dict(id=r.id, name=r.id, shortDescription=dict(text=r.title), defaultConfiguration=dict(level=lv[r.severity])) for r in RULES.values()]
    res = []
    for i in issues:
        x = dict(ruleId=i.rule, level=lv[i.severity], message=dict(text=f"{i.message}. Fix: {i.fix}" if i.fix else i.message),
                 properties=dict(objects=i.objects))
        if i.file:
            loc = dict(artifactLocation=dict(uri=i.file))
            if i.row: loc["region"] = dict(startLine=i.row)
            x["locations"] = [dict(physicalLocation=loc)]
        res.append(x)
    return dict(version="2.1.0", runs=[dict(tool=dict(driver=dict(name="schemagen", informationUri="https://github.com/", rules=rules)),
                                             results=res, originalUriBaseIds=dict(SRCROOT=dict(uri=root.as_uri() + "/")))],
                **{"$schema": "https://json.schemastore.org/sarif-2.1.0.json"})


def check(a):
    L = _loaded(a.config)
    issues = locate(L, run_rules(L.model, L.cfg, only=a.rule, measured=measured_lengths(L.cfg)))
    if a.format == "json": s = json.dumps([i.model_dump() for i in issues], ensure_ascii=False, indent=1)
    elif a.format == "sarif": s = json.dumps(sarif(issues, L.cfg.root), ensure_ascii=False, indent=1)
    else:
        lines = [f"{i.severity:7} {i.rule:18} {i.message}" + (f"\n        fix: {i.fix}" if i.fix else "") for i in issues]
        n = {s: sum(1 for i in issues if i.severity == s) for s in ("error", "warning", "info")}
        s = "\n".join(lines + [f"{n['error']} error(s), {n['warning']} warning(s), {n['info']} info"])
    if a.output: Path(a.output).write_text(s + "\n", encoding="utf-8")
    else: print(s)
    return 1 if any(i.severity == "error" for i in issues) else 0


def _wires_csv(m):
    from ..exporters import table as T
    head, rows = T.wires(m)
    buf = io.StringIO()
    import csv
    w = csv.writer(buf, lineterminator="\n"); w.writerow(head); w.writerows(rows)
    return buf.getvalue().splitlines(keepends=True)


def direction_changeset(L):
    """(change set, flips) that makes every conductor follow the direction convention."""
    flips = analyse(Ctx(L.model, L.cfg))
    recs = {r.data.get("id"): r for r in L.records}
    ops = [op for f in flips if f.id in recs for op in ch.flip_ops(recs[f.id])]
    return ch.new_set(f"direction convention: swap the ends of {len(flips)} conductor(s)", ops, slug="direction"), flips


def fix(a):
    L = _loaded(a.config)
    cs, flips = direction_changeset(L)
    if not flips: print("no direction findings: nothing to change"); return 0
    out = L.cfg.out / "changes"; out.mkdir(parents=True, exist_ok=True)
    p = out / "direction.json"
    p.write_text(json.dumps(cs.model_dump(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    import copy
    recs = copy.deepcopy(L.records)
    ch.apply(recs, [cs])
    m2 = L.rebuild(recs)
    patch = "".join(difflib.unified_diff(_wires_csv(L.model), _wires_csv(m2), "wires (before)", "wires (after)"))
    (out / "direction.diff").write_text(patch, encoding="utf-8")
    for f in flips: print(f"swap ends: {f.label} ({f.id}): {f.reason}")
    print(f"change set: {p}\ndiff:       {out / 'direction.diff'}")
    if a.apply:
        print(f"stored as {ch.save(L.cfg.root, cs)} (applied on every load; commit it, or undo with `schemagen changes --undo`)")
    else: print("review, then run again with --apply to store it in the project's changes/ folder")
    return 0


def pinout(a):
    from ..exporters import pinout as po
    L = _loaded(a.config)
    out = Path(a.output) if a.output else L.cfg.out / "pinout.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    ctx = Ctx(L.model, L.cfg)
    po.write_xlsx(L.model, out, ctx, a.page_breaks); po.write_html(L.model, out.with_suffix(".html"), ctx)
    print(f"pinout -> {out} and {out.with_suffix('.html')}")


def wirelist(a):
    from ..exporters.views import wirelist_xlsx
    from ..renderers.project import Project
    pr = Project(load_config(a.config))
    wirelist_xlsx(pr, Path(a.output)); print(f"{len(pr.wires)} wires -> {a.output}")


def template(a):
    from ..exporters.views import template_xlsx
    if a.config:
        L = _loaded(a.config); template_xlsx(L.model, Path(a.output), L.cfg)
    else: template_xlsx(None, Path(a.output))
    print(f"sheet template -> {a.output} (upload to Google Sheets or open in a spreadsheet; set source: {{path: ...}} to read it)")


def labels(a):
    L = _loaded(a.config)
    led = L.model.ledger
    if a.retire:
        led = ledger.retire(led, a.retire, a.reason or "retired by hand"); print(f"retired {a.retire}")
    if a.update or not a.retire:
        L.model.ledger = led
        led, msgs = ledger.update(L.model, a.reason)
        for m in msgs: print(m)
    ledger.save(led, ledger_path(L.cfg))
    print(f"ledger: {sum(e.status == 'active' for e in led.entries)} active, {sum(e.status == 'retired' for e in led.entries)} retired -> "
          f"{ledger_path(L.cfg)}")
    return 0


def _side(x, project):
    p = Path(x)
    if p.exists(): return load(p).model, x
    return load(df.checkout(x, Path(project))).model, x


def diff(a):
    ma, na = _side(a.a, a.project)
    mb, nb = _side(a.b, a.project)
    d = df.diff(ma, mb)
    s = df.dumps(d) if a.format == "json" else df.to_html(d, f"schemagen diff {na} → {nb}") if a.format == "html" else df.text(d)
    if a.output: Path(a.output).write_text(s, encoding="utf-8")
    else: sys.stdout.write(s)
    return 0


def changes(a):
    root = load_config(a.config).root
    if a.undo:
        p = ch.undo(root); print(f"removed {p}" if p else "no change sets"); return
    for cs in ch.load_all(root): print(f"{cs.id}: {cs.title} ({len(cs.ops)} ops, {cs.created})")


def sim(a):
    try:
        from ..sim import report
    except ImportError:
        raise SystemExit("the simulation needs scipy: pip install schema-gen") from None
    return report.run_cli(a)


def app(a):
    from ..app import server
    server.serve(a.config, a.host, a.port, open_browser=not a.no_browser)
