"""Write the mock's example Workspace (frontend/src/mock/aircraft.json) from the real engine and examples/aircraft.

    PYTHONPATH=<repo> python frontend/e2e/make_mock.py

A stand-in until the server's /api/workspace exists (docs/api.md); the shapes follow that contract.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from schemagen.app.server import State  # noqa: E402

RANK = {"battery": 0, "dcdc": 0, "source": 0, "breaker": 1, "fuse": 1, "relay": 1, "switch": 1, "bus": 2, "ground": 2, "harness": 3}
SEV = {"error": 3, "warning": 2, "info": 1, "": 0}


def main(out: Path) -> None:
    st = State(ROOT / "examples" / "aircraft")
    ix = st.index()
    comps = {c["id"]: c for c in ix["components"]}
    kind = {k: c["kind"] for k, c in comps.items()}
    for cn in ix["connectors"]:  # harness connectors as components
        comps.setdefault(cn["id"], dict(id=cn["id"], name=cn["name"], kind="harness", zone=""))
        kind[cn["id"]] = "harness"
    splice = {k for k, v in kind.items() if v == "splice"}
    # a splice end folds into the components the splice joins
    by_splice: dict[str, set[str]] = defaultdict(set)
    for c in ix["conductors"]:
        for e, o in ((c["f"], c["t"]), (c["t"], c["f"])):
            if e[0] in splice and o[0] not in splice: by_splice[e[0]].add(o[0])
    wires, pins, subs = [], defaultdict(set), defaultdict(list)
    hex_cls = {h: k for k, h in reversed(list(ix["palette"].items()))}
    for c, mc in zip(ix["conductors"], st.m.conductors):
        ends = []
        for e, o in ((c["f"], c["t"]), (c["t"], c["f"])):
            ends.append(e[0] if e[0] not in splice else next(iter(sorted(by_splice[e[0]] - {o[0]})), o[0]))
        for e in (c["f"], c["t"]): pins[e[0]].add((e[1], e[2]))
        for x in ends: subs[x].append(mc.subsystem)
        cls = mc.cls or ("HV" if mc.kind == "400 V" else mc.kind)
        txt = lambda e: " ".join(x for x in (st.dname(e[0]), e[1], e[2]) if x)  # noqa: E731
        wires.append(dict(id=c["id"], label=c["label"], name=c["name"], **{"from": txt(c["f"])}, to=txt(c["t"]), a=ends[0], b=ends[1],
                          gauge=f"{c['gauge']} AWG" if re.fullmatch(r"\d+", str(c["gauge"] or "")) else str(c["gauge"] or ""),
                          voltage=c["bus"] or "", current=c["current"], cls=cls if cls in ix["palette"] else hex_cls.get(c["hex"], cls), hex=c["hex"], length=c["length"],
                          harness=c["harness"], protection=c["protection"], status=c["status"], notes="", sev=c["sev"]))
    used = {w[k] for w in wires for k in "ab"}
    sev: dict[str, str] = defaultdict(str)
    issues = []
    for i in ix["issues"]:
        for o in i["objects"]:
            t, _, oid = o.partition(":")
            oid = oid.split("/")[0]
            for x in ([oid] if t in ("component", "pin", "connector", "protective") else [w["a"] for w in wires if w["id"] == oid]):
                if SEV[i["severity"]] > SEV[sev[x]]: sev[x] = i["severity"]
        msg, title = i["message"], i["message"]
        if i["rule"] == "gauge-protection":  # a plain title, as the server's Issue.title will be
            w = next(w for w in wires if f"conductor:{w['id']}" in i["objects"])
            title = f"{w['name']} ({w['label']}) is too thin for its breaker"
        elif i["rule"] == "direction-unknown": title, msg = "3 antenna cables have no known signal direction", "An antenna and a radio have no one-way signal; nothing to fix."
        issues.append(dict(k=i["k"], rule=i["rule"], severity=i["severity"], title=title, message=msg if msg != title else "",
                           fix=i["fix"] or "", objects=i["objects"]))
    nodes = [dict(id=k, name=c["name"] or k, kind=c["kind"], zone=c.get("zone") or "", subsystem=c.get("zone") or "", pins=len(pins[k]),
                  rank=RANK.get(c["kind"], 4), sev=sev[k]) for k, c in comps.items() if k in used and k not in splice]
    rank = {n["id"]: n["rank"] for n in nodes}
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for w in wires:
        a, b = sorted((w["a"], w["b"]), key=lambda x: (rank.get(x, 4), x))
        groups[(a, b)].append(w)
    edges = []
    for (a, b), ws in groups.items():
        cls = list(dict.fromkeys(w["cls"] for w in ws))
        short = list(dict.fromkeys("CAN" if x.startswith("CAN") else x for x in cls))
        edges.append(dict(id=f"{a}~{b}", a=a, b=b, wires=[w["id"] for w in ws], cls=cls,
                          label=f"{len(ws)} × {short[0]}" if len(short) == 1 else f"{len(ws)} wires"))
    zones = defaultdict(list)  # subsystem: the one most of a component's wires belong to (buses with the power group)
    for n in nodes:
        if n["kind"] == "harness": continue
        ss = [x for x in subs[n["id"]] if x and x != "CAN bus"] or [x for x in subs[n["id"]] if x]
        z = "Power generation and storage" if n["kind"] == "bus" else max(set(ss), key=ss.count) if ss else ""
        n["zone"] = n["subsystem"] = z
        if z: zones[z].append(n["id"])
    ws = dict(project=dict(name="Kestrel E2", root="examples/aircraft", version=ix["project"]["version"], warnings=ix["project"]["warnings"]),
              components=nodes, edges=edges, conductors=wires, issues=issues,
              zones=[dict(id=re.sub(r"\W+", "-", z.lower()), name=z, members=m) for z, m in zones.items()], positions={}, sources=[], palette=ix["palette"])
    out.write_text(json.dumps(ws, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(nodes)} components, {len(wires)} wires, {len(edges)} bundles, {len(issues)} issues, {len(zones)} zones -> {out}")


if __name__ == "__main__":
    main(ROOT / "frontend" / "src" / "mock" / "aircraft.json")
