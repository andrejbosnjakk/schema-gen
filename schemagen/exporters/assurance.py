"""The assurance report: one page that says, layer by layer, what is checked about the wiring, what fails and what is not yet known (D118).

1 the sheet agrees with itself (the rules), 2 every wire lands on a real pin of the right type (datasheet cards), 3 it works electrically (the
simulation's scenarios and fault sweep), 4 what is built matches the drawings (check-drawings, the continuity sheets). A layer passes only when it
has no error and nothing in it rests on an assumption.
"""
from __future__ import annotations

import html
import re
from typing import Any

from ..core.context import Ctx
from ..core.rules import RULES, run_rules

DATASHEET_RULES = ("pin-not-in-part", "pin-type-clash", "output-conflict", "power-ground", "required-pin", "contact-gauge", "contact-current",
                   "dsub-gauge", "can-terminators", "can-nodes")
NOT_DEVICES = ("splice", "bus", "harness")


def coverage(m: Any, ctx: Ctx) -> list[dict[str, Any]]:
    """Per device with wires: its card (if any), its wire ends, how many land on a pin the card describes, and the pins that are not described."""
    out = []
    for c in sorted(m.components, key=lambda c: c.id):
        if c.kind in NOT_DEVICES or not ctx.net.by_dev[c.raw]: continue
        ts = [m.conductors[i].end(e) for i, e in ctx.net.by_dev[c.raw]]
        p = ctx.part_of(c.raw)
        missing = sorted({f"{t.connector} {t.pin}".strip() for t in ts if not ctx.pin(t)})
        out.append(dict(id=c.id, name=c.name or c.id, kind=c.kind, card=(p.card or p.id) if p else "", ends=len(ts), checked=len(ts) - sum(
            1 for t in ts if not ctx.pin(t)), missing=missing))
    return out


def report(L: Any, simulate: bool = True) -> dict[str, Any]:
    """The four layers of a loaded project (core.load.load)."""
    m, cfg = L.model, L.cfg
    ctx = Ctx(m, cfg)
    issues = run_rules(m, cfg, ctx=ctx)
    sheet = [i for i in issues if i.rule not in DATASHEET_RULES and i.severity in ("error", "warning")]
    data = [i for i in issues if i.rule in DATASHEET_RULES and i.severity in ("error", "warning")]
    cov = coverage(m, ctx)
    ends, checked = sum(r["ends"] for r in cov), sum(r["checked"] for r in cov)
    rep: dict[str, Any] = dict(project=cfg.root.name, layers=[
        dict(n=1, title="The sheet agrees with itself", ok=not any(i.severity == "error" for i in sheet),
             findings=[(i.severity, i.rule, i.message) for i in sheet], known=f"{len(m.conductors)} wires, {len(RULES)} rules"),
        dict(n=2, title="Every wire lands on a real pin of the right type", ok=not any(i.severity == "error" for i in data) and checked == ends,
             findings=[(i.severity, i.rule, i.message) for i in data],
             known=f"{checked} of {ends} wire ends checked against a datasheet card; {sum(1 for r in cov if r['card'])} of {len(cov)} devices have one")])
    rep["coverage"] = cov
    rep["layers"].append(_electrical(L, ctx) if simulate else dict(n=3, title="It works electrically", ok=False, findings=[], known="not simulated"))
    rep["layers"].append(dict(n=4, title="What is built matches the drawings", ok=None, findings=[],
                              known="checked outside this report: `schemagen check-drawings` on the exported PDFs, then the continuity sheets on the aircraft"))
    return rep


def _electrical(L: Any, ctx: Ctx) -> dict[str, Any]:
    """The scenarios in <project>/scenarios and a fault sweep, with every assumption they rest on."""
    lay: dict[str, Any] = dict(n=3, title="It works electrically", ok=False, findings=[], known="")
    try:
        import yaml

        from ..core.load import measured_lengths
        from ..sim import api
    except ImportError:
        lay["known"] = "not simulated: the simulation needs scipy"; return lay
    m, cfg = L.model, L.cfg
    meas = measured_lengths(cfg)
    files = sorted((cfg.root / "scenarios").glob("*.yml"))
    asm: dict[str, set[str]] = {}    # what is assumed ("load", "battery", "conductor lengths") -> the entries
    passed = 0
    for f in files:
        sc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        sc.setdefault("scenario", f.stem)
        op = api.operating_point(m, cfg, sc, meas, ctx)
        passed += op.ok
        for e in op.expectations:
            if not e["ok"]: lay["findings"].append(("error", "scenario", f"{api.scenario_name(sc)}: {e['detail']}"))
        for b in op.unpowered: lay["findings"].append(("error", "scenario", f"{api.scenario_name(sc)}: bus {b} has loads but no source reaches it"))
        for b in op.missing: lay["findings"].append(("error", "scenario", f"{api.scenario_name(sc)}: {b}"))
        for a in op.assumptions:
            if a.provenance in ("assumed", "estimated"): asm.setdefault(_topic(a.what), set()).add(f"{a.what}: {a.note}")
    sw = api.fault_sweep(m, cfg, None, meas, ctx)
    nc = [r["node"] for r in sw.rows if not r.get("first_trip") and r.get("fault_current_A")]
    dmg = [r["node"] for r in sw.rows if r.get("wire_survives") is False]
    lay["findings"] += [("error", "fault", f"a short to ground at {n} is cleared by no breaker or fuse") for n in nc]
    lay["findings"] += [("warning", "fault", f"a short to ground at {n} damages a wire before it is cleared") for n in dmg]
    lay["assumptions"] = [f"{k}: {len(v)} assumed" + (": " + "; ".join(sorted(v)) if len(v) <= 6 or k in ("battery", "source", "dcdc") else f", e.g. {sorted(v)[0]}")
                           for k, v in sorted(asm.items())]
    lay["known"] = (f"{passed} of {len(files)} scenarios pass" if files else "no scenarios written yet (scenarios/*.yml)") + \
                   f"; {len(sw.rows)} shorts to ground tried; {sum(map(len, asm.values()))} values assumed"
    lay["ok"] = bool(files) and passed == len(files) and not nc and not asm
    return lay


def _topic(what: str) -> str:
    """What an assumption is about: `DCHV enable relay (relay)` -> relay, `14-V-BATTERY battery` -> battery, `conductor lengths` as it is."""
    m, w = re.search(r"\((\w+)\)$", what), what.split()
    return m[1] if m else w[-1] if len(w) > 1 and w[0].isupper() else what


def to_html(rep: dict[str, Any]) -> str:
    """The report as one self-contained, printable page."""
    e = html.escape
    mark = {True: ("pass", "PASS"), False: ("open", "NOT YET"), None: ("na", "OUTSIDE")}
    out = [f"<!doctype html><meta charset=utf-8><title>Assurance: {e(rep['project'])}</title><style>{CSS}</style>",
           f"<h1>Is the wiring sound? <small>{e(rep['project'])}</small></h1>",
           "<p class=lead>Each layer passes only with no error and nothing resting on an assumption. A pass is evidence, not proof: "
           "an experienced review of the sheet and the power-up test on the aircraft remain.</p>"]
    for lay in rep["layers"]:
        cls, word = mark[lay["ok"]]
        out.append(f"<section><h2><span class='tag {cls}'>{word}</span> {lay['n']}. {e(lay['title'])}</h2><p>{e(lay['known'])}</p>")
        if lay["findings"]:
            out.append("<table><tr><th></th><th>check</th><th>finding</th></tr>" + "".join(
                f"<tr class={s}><td>{s}</td><td>{e(r)}</td><td>{e(msg)}</td></tr>" for s, r, msg in lay["findings"]) + "</table>")
        if lay.get("assumptions"):
            out.append("<p>Rests on assumed data:</p><ul>" + "".join(f"<li>{e(a)}</li>" for a in lay["assumptions"]) + "</ul>")
        if lay["n"] == 2:
            out.append("<details><summary>Datasheet coverage per device</summary><table><tr><th>device</th><th>card</th><th>wire ends checked</th>"
                       "<th>pins without datasheet data</th></tr>" + "".join(
                           f"<tr class={'pass' if r['checked'] == r['ends'] else 'open'}><td>{e(r['name'])}</td><td>{e(r['card']) or '-'}</td>"
                           f"<td>{r['checked']} / {r['ends']}</td><td>{e(', '.join(r['missing']))}</td></tr>" for r in rep["coverage"]) + "</table></details>")
        out.append("</section>")
    return "\n".join(out) + "\n"


CSS = ("body{font:14px/1.45 system-ui,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#111}h1 small{color:#666;font-weight:400}"
       ".lead{color:#444}section{border-top:1px solid #ddd;padding-top:8px;margin-top:16px}table{border-collapse:collapse;width:100%;font-size:13px}"
       "td,th{text-align:left;padding:3px 6px;border-bottom:1px solid #eee;vertical-align:top}tr.error td:first-child{color:#b00}"
       "tr.warning td:first-child{color:#a60}tr.open td:nth-child(3){color:#a60}.tag{font-size:12px;padding:2px 6px;border-radius:3px;color:#fff}"
       ".tag.pass{background:#287a3e}.tag.open{background:#b35c00}.tag.na{background:#777}")
