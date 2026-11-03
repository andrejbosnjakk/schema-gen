"""`schemagen app <project>`: a local server (FastAPI + uvicorn) and the bundled frontend. Nothing leaves the machine:
the server binds to 127.0.0.1 by default, the frontend is served from the wheel, no CDN, no telemetry.

Edits are stored as change sets in <project>/changes/ (git-friendly; undo removes the last one).
"""
from __future__ import annotations

import subprocess
import threading
import webbrowser
from collections import Counter, defaultdict
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..core import changes as ch
from ..core import diff as df
from ..core.config import load_config
from ..core.context import Ctx
from ..core.load import Loaded, load, measured_lengths
from ..core.model import Terminal
from ..core.rules import run_rules
from ..palette import HEX
from ..importers.records import text as text_of

EDITABLE = {"label", "name", "awg", "colour", "cls", "st", "length", "amps", "notes", "func", "bus", "zone", "harn", "prot",
            "p1", "p1c", "p1p", "p1side", "p2", "p2c", "p2p", "p2side", "subsystem"}


class State:
    """The loaded project and everything derived from it; rebuilt after every change set."""

    def __init__(self, project: str | Path, background: bool = False):
        self.cfg = load_config(project)
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.error = ""
        self._json: bytes | None = None
        if background: threading.Thread(target=self._first_load, daemon=True).start()
        else: self.reload(); self.ready.set()

    def _first_load(self) -> None:
        try: self.reload(); self.index_json()
        except BaseException as e:  # noqa: BLE001  (shown to the user instead of a hung page)
            self.error = str(e)
        self.ready.set()

    def wait(self) -> None:
        self.ready.wait()
        if self.error: raise HTTPException(500, f"could not load the project: {self.error}")

    def index_json(self) -> bytes:
        """The index, serialised once per reload."""
        if self._json is None:
            import json
            self._json = json.dumps(self.index(), ensure_ascii=False, separators=(",", ":")).encode()
        return self._json

    def reload(self) -> None:
        L = load(self.cfg)
        self.L: Loaded = L
        self.m = L.model
        self.ctx = Ctx(self.m, self.cfg)
        self.measured = measured_lengths(self.cfg)
        self.issues = run_rules(self.m, self.cfg, measured=self.measured, ctx=self.ctx)
        self.nets = self.ctx.net.nets()
        self.net_of = {i: n.id for n in self.nets for i in n.conductors}
        self._index: dict[str, Any] | None = None
        self._json = None
        self._graph: dict[str, Any] | None = None
        self._history: dict[str, list[dict[str, str]]] = {}

    # ---------------------------------------------------------------- refs
    def cid(self, raw: str) -> str:
        c = self.ctx.comp.get(raw)
        return c.id if c else raw

    def pin_id(self, t: Terminal) -> str:
        return f"{self.cid(t.device)}/{t.connector}/{t.pin}"

    def index(self) -> dict[str, Any]:
        """Everything the frontend needs at start: compact rows for every object."""
        if self._index is not None: return self._index
        m = self.m
        per: dict[str, list[int]] = defaultdict(list)
        for k, iss in enumerate(self.issues):
            for o in iss.objects: per[o].append(k)
        conds = []
        for i, c in enumerate(m.conductors):
            refs = per.get(f"conductor:{c.id}", [])
            conds.append(dict(i=i, id=c.id, label=c.label, name=c.name, f=[self.cid(c.from_.device), c.from_.connector, c.from_.pin, c.from_.side],
                              t=[self.cid(c.to.device), c.to.connector, c.to.pin, c.to.side], func=c.func, bus=c.bus, cls=c.cls, kind=c.kind,
                              gauge=c.gauge, colour=c.colour_code, hex=HEX.get(c.colour_code[:2], "#888"), length=c.length_m,
                              current=c.current_a, status=c.status, harness=c.harness, protection=c.protection, zone=c.zone,
                              net=self.net_of.get(i, ""), sev=min((str(self.issues[k].severity) for k in refs), key=lambda x: SEV.get(x, 9)) if refs else ""))
        comps = [dict(id=x.id, name=x.name, kind=x.kind, part=x.part, zone=x.zone) for x in m.components]
        cons = [dict(id=x.id, name=x.name, halves=[[h.name, h.side, h.guessed] for h in x.halves], pins=x.pin_count) for x in m.connectors]
        nets = [dict(id=n.id, name=n.name, kind=n.kind, c=n.conductors) for n in self.nets]
        from ..exporters.views import lists
        self._index = dict(
            project=dict(root=str(self.cfg.root), name=self.cfg.root.name, version=__version__, warnings=self.L.warnings,
                         changes=[dict(id=cs.id, title=cs.title, created=cs.created, ops=len(cs.ops)) for cs in ch.load_all(self.cfg.root)],
                         scenarios=sorted(p.name for p in (self.cfg.root / "scenarios").glob("*.yml"))),
            conductors=conds, components=comps, connectors=cons, harnesses=[dict(id=h.id, n=len(h.conductors)) for h in m.harnesses],
            nets=nets, issues=[dict(k=k, **i.model_dump(include={"rule", "severity", "message", "objects", "fix"})) for k, i in enumerate(self.issues)],
            open_items=[o.model_dump() for o in m.open_items], protective=[p.model_dump() for p in m.protective_devices],
            lists=lists(m, self.cfg), palette={k: HEX.get(v[:2], "#888") for k, v in self.cfg.colours.items()})
        return self._index

    # ---------------------------------------------------------------- object pages
    def history(self, key: str) -> list[dict[str, str]]:
        """Commits that mention the object (git log -S), newest first; empty outside a git repository."""
        if key in self._history: return self._history[key]
        try:
            r = subprocess.run(["git", "-C", str(self.cfg.root), "log", "-n", "15", "--format=%h%x09%ad%x09%an%x09%s", "--date=short",
                                f"-S{key}", "--", "."], capture_output=True, text=True, timeout=10)
            out = [dict(zip(("commit", "date", "author", "subject"), line.split("\t", 3))) for line in r.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.SubprocessError):
            out = []
        self._history[key] = out
        return out

    def issues_for(self, refs: list[str]) -> list[dict[str, Any]]:
        rs = set(refs)
        return [dict(k=k, **i.model_dump(include={"rule", "severity", "message", "fix"})) for k, i in enumerate(self.issues)
                if any(o in rs or any(o.startswith(r + "/") for r in rs if r.startswith("pin:")) for o in i.objects)]

    def obj(self, typ: str, oid: str) -> dict[str, Any]:
        m, ctx = self.m, self.ctx
        conds = m.conductors
        link = lambda t, i, label=None: dict(type=t, id=i, label=label or i)  # noqa: E731
        if typ == "conductor":
            i = next((k for k, c in enumerate(conds) if c.id == oid), None)
            if i is None: raise HTTPException(404, f"no conductor {oid}")
            c = conds[i]
            src = self.L.records[i] if i < len(self.L.records) else None
            links = [link("pin", self.pin_id(c.from_), f"from {self.pin_id(c.from_)}"), link("pin", self.pin_id(c.to), f"to {self.pin_id(c.to)}"),
                     link("component", self.cid(c.from_.device)), link("component", self.cid(c.to.device)),
                     link("net", self.net_of.get(i, ""), f"net {self.net_of.get(i, '')}")]
            if c.harness: links.append(link("harness", c.harness))
            if c.protection: links.append(link("component", c.protection, f"protected by {c.protection}"))
            props = c.model_dump(by_alias=True, exclude={"extra", "sources", "from_", "to"})
            return dict(type=typ, id=oid, title=f"{c.label} {c.name}", props=dict(props, **{"from": self.pin_id(c.from_), "to": self.pin_id(c.to)}),
                        extra=c.extra, sources=[s.text() for s in c.sources], links=links, issues=self.issues_for([f"conductor:{c.id}"]),
                        origin=dict(file=src.file, row=src.row) if src else None, history=self.history(c.id), conductors=[i])
        if typ == "pin":
            cidv, con, pin = (oid.split("/") + ["", ""])[:3]
            comp = ctx.comp_by_id.get(cidv)
            if comp is None: raise HTTPException(404, f"no component {cidv}")
            t = Terminal(device=comp.raw, connector=con, pin=pin)
            at = [(i, e) for i, e in ctx.net.by_dev[comp.raw] if conds[i].end(e).connector == con and conds[i].end(e).pin == pin]
            d = ctx.pin(t)
            props = dict(component=comp.id, connector=con, pin=pin, **(d.model_dump(exclude={"extra", "n", "type"}) if d else {}), type=ctx.pin_type(t) or "")
            links = [link("component", comp.id)] + [link("conductor", conds[i].id, f"{conds[i].label} → {self.pin_id(conds[i].end(3 - e))}") for i, e in at]
            if at: links.append(link("net", self.net_of[at[0][0]], f"net {self.net_of[at[0][0]]}"))
            return dict(type=typ, id=oid, title=f"{comp.id} {con} {pin}".strip(), props=props, links=links, issues=self.issues_for([f"pin:{oid}"]),
                        history=[], sources=[], conductors=sorted({i for i, _ in at}))
        if typ in ("component", "connector"):
            comp = ctx.comp_by_id.get(oid)
            if comp is None: raise HTTPException(404, f"no {typ} {oid}")
            ends = ctx.net.by_dev[comp.raw]
            pins = sorted({self.pin_id(conds[i].end(e)) for i, e in ends})
            cprops: dict[str, Any] = comp.model_dump(exclude={"extra"})
            pd = next((p for p in m.protective_devices if p.id == comp.id), None)
            if pd: cprops.update(rating_A=pd.rating_a, panel=pd.panel, loads=", ".join(pd.loads), trip_curve=pd.trip_curve)
            hc = next((x for x in m.connectors if x.id == comp.id), None)
            if hc: cprops.update(halves=", ".join(f"{h.name}: {h.side}{' (guessed)' if h.guessed else ''}" for h in hc.halves), pin_count=hc.pin_count)
            links = [link("pin", p) for p in pins] + ([link("part", comp.part)] if comp.part else [])
            if pd and pd.id in ctx.protected_by:
                links += [link("conductor", conds[i].id, f"protects {conds[i].label}") for i in ctx.protected_by[pd.id][:50]]
            return dict(type="connector" if comp.kind == "harness" else "component", id=oid, title=f"{comp.id} {comp.name}", props=cprops, extra=comp.extra,
                        links=links, issues=self.issues_for([f"component:{oid}", f"connector:{oid}", f"protective:{oid}", f"pin:{oid}"]),
                        history=self.history(comp.id), sources=[], conductors=sorted({i for i, _ in ends}))
        if typ == "harness":
            h = next((x for x in m.harnesses if x.id == oid), None)
            if h is None: raise HTTPException(404, f"no harness {oid}")
            idx = [i for i, c in enumerate(conds) if c.harness == oid]
            return dict(type=typ, id=oid, title=f"harness {oid}", props=dict(id=oid, conductors=len(idx)), history=self.history(oid),
                        links=[link("conductor", conds[i].id, conds[i].label) for i in idx], issues=[], sources=[], conductors=idx)
        if typ == "net":
            n = next((x for x in self.nets if x.id == oid), None)
            if n is None: raise HTTPException(404, f"no net {oid}")
            comps = sorted({self.cid(conds[i].end(e).device) for i in n.conductors for e in (1, 2)})
            return dict(type=typ, id=oid, title=f"net {n.name}", props=dict(id=n.id, name=n.name, function_class=n.kind, conductors=len(n.conductors)),
                        links=[link("component", c) for c in comps] + [link("conductor", conds[i].id, conds[i].label) for i in n.conductors],
                        issues=self.issues_for([oid]), history=[], sources=[], conductors=n.conductors)
        if typ == "part":
            p = ctx.parts.get(oid)
            if p is None: raise HTTPException(404, f"no part {oid}")
            users = [c.id for c in m.components if c.part == oid]
            return dict(type=typ, id=oid, title=f"part {oid}", props=p.model_dump(exclude={"connectors", "extra"}),
                        links=[link("component", u) for u in users], issues=[], history=[], sources=[p.card] if p.card else [], conductors=[],
                        pins=[dict(connector=c.id, **pin.model_dump(exclude={"extra"})) for c in p.connectors for pin in c.pins])
        raise HTTPException(404, f"unknown object type {typ}")

    # ---------------------------------------------------------------- graph
    def graph(self) -> dict[str, Any]:
        """System graph: components, buses, breakers and harness connectors; edges where conductors join them
        (through splices)."""
        if self._graph is not None: return self._graph
        conds, ctx = self.m.conductors, self.ctx
        edges: Counter[tuple[str, str]] = Counter()
        for n in self.nets:
            comps = sorted({self.cid(conds[i].end(e).device) for i in n.conductors for e in (1, 2)
                            if ctx.comp.get(conds[i].end(e).device) and ctx.comp[conds[i].end(e).device].kind != "splice"})
            buses = [c for c in comps if ctx.comp_by_id[c].kind == "bus"] if comps else []
            hub = buses[0] if buses else (comps[0] if comps else None)
            for c in comps:
                if hub and c != hub: edges[tuple(sorted((hub, c)))] += len(n.conductors)  # type: ignore[index]
        nodes = sorted({x for e in edges for x in e} | {c.id for c in self.m.components if c.kind not in ("splice",)})
        self._graph = dict(nodes=[dict(id=n, kind=ctx.comp_by_id[n].kind if n in ctx.comp_by_id else "device",
                                       name=ctx.comp_by_id[n].name if n in ctx.comp_by_id else n) for n in nodes],
                           edges=[dict(a=a, b=b, w=w) for (a, b), w in sorted(edges.items())])
        return self._graph

    # ---------------------------------------------------------------- editing
    def edit(self, edits: list[dict[str, Any]], title: str = "") -> ch.ChangeSet:
        recs = {text_of(r.data.get("id")): r for r in self.L.records}
        ops = []
        for e in edits:
            cid, field, new = str(e["id"]), str(e["field"]), e.get("value")
            if field not in EDITABLE: raise HTTPException(400, f"field {field} cannot be edited here")
            r = recs.get(cid)
            if r is None: raise HTTPException(404, f"no conductor {cid}")
            old = text_of(r.data.get(field))
            if text_of(new) == old: continue
            ops.append(ch.Op(op="set", id=cid, field=field, old=old, new=new))
        if not ops: raise HTTPException(400, "nothing changed")
        cs = ch.new_set(title or f"edit {len(ops)} field(s) in the app", ops, author="app", slug="app-edit")
        with self.lock:
            ch.save(self.cfg.root, cs)
            self.reload()
        return cs


SEV = {"error": 0, "warning": 1, "info": 2}


def create_app(project: str | Path, background: bool = False) -> FastAPI:
    st = State(project, background)
    import inspect
    kw: dict[str, Any] = {}
    if "telemetry" in inspect.signature(FastAPI.__init__).parameters:  # FastAPI >= 0.16x: no traces, metrics or logs, never exported
        kw["telemetry"] = dict(tracing=False, metrics=False, logs=False, operation_spans=False, auto_configure=False, exclude=lambda scope: True)
    app = FastAPI(title="schemagen", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, **kw)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.state.st = st

    @app.middleware("http")
    async def ready(request: Any, call_next: Any) -> Any:
        if request.url.path.startswith("/api/") and request.url.path != "/api/health":
            import anyio
            await anyio.to_thread.run_sync(st.wait)
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return dict(ready=st.ready.is_set(), error=st.error)

    @app.get("/api/index")
    def index() -> Response:
        return Response(st.index_json(), media_type="application/json")

    @app.get("/api/object")
    def obj(type: str, id: str) -> dict[str, Any]:  # noqa: A002
        return st.obj(type, id)

    @app.get("/api/graph")
    def graph() -> dict[str, Any]:
        return st.graph()

    @app.post("/api/edit")
    def edit(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        cs = st.edit(body.get("edits", []), body.get("title", ""))
        return dict(changeset=cs.model_dump(), index=st.index())

    @app.post("/api/undo")
    def undo() -> dict[str, Any]:
        with st.lock:
            p = ch.undo(st.cfg.root)
            st.reload()
        return dict(removed=p.name if p else None, index=st.index())

    @app.get("/api/fix/direction")
    def fix_preview() -> dict[str, Any]:
        from ..cli.commands import direction_changeset
        cs, flips = direction_changeset(st.L)
        return dict(flips=[dict(id=f.id, label=f.label, reason=f.reason) for f in flips], ops=[o.model_dump() for o in cs.ops])

    @app.post("/api/fix/direction")
    def fix_apply() -> dict[str, Any]:
        from ..cli.commands import direction_changeset
        cs, flips = direction_changeset(st.L)
        if not flips: raise HTTPException(400, "nothing to fix")
        with st.lock:
            ch.save(st.cfg.root, cs); st.reload()
        return dict(applied=len(flips), index=st.index())

    @app.get("/api/diff")
    def diff(rev: str = "HEAD") -> dict[str, Any]:
        try: other = load(df.checkout(rev, st.cfg.root)).model
        except subprocess.CalledProcessError as e: raise HTTPException(400, f"git revision {rev!r} not found: {e.stderr!s}") from None
        except SystemExit as e: raise HTTPException(400, str(e)) from None
        d = df.diff(other, st.m)
        return dict(rev=rev, diff=d, text=df.text(d))

    @app.get("/api/sim/scenarios")
    def scenarios() -> list[str]:
        return st.index()["project"]["scenarios"]

    @app.post("/api/sim/run")
    def sim_run(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        from ..sim import api as sim
        from ..sim.report import _jsonable
        name = body.get("scenario")
        sc = yaml.safe_load((st.cfg.root / "scenarios" / str(name)).read_text(encoding="utf-8")) if name else body.get("inline")
        op = sim.operating_point(st.m, st.cfg, sc, st.measured, st.ctx)
        out = _jsonable(op)
        out["ok"] = op.ok
        out.pop("nodes", None)
        out["tree"] = bus_tree(st, op)
        out["conductors"] = sorted(out["conductors"], key=lambda c: -(c["loading"] or 0))[:40]
        return out

    @app.post("/api/sim/faults")
    def sim_faults(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:  # noqa: B008
        from ..sim import api as sim
        from ..sim.report import _jsonable
        name = body.get("scenario")
        sc = yaml.safe_load((st.cfg.root / "scenarios" / str(name)).read_text(encoding="utf-8")) if name else None
        sw = sim.fault_sweep(st.m, st.cfg, sc, st.measured, st.ctx)
        return dict(_jsonable(sw))

    @app.get("/api/drawings")
    def drawings() -> list[dict[str, str]]:
        out = st.cfg.out
        return [dict(name=p.stem) for p in sorted(out.glob("*.svg"))] if out.exists() else []

    @app.post("/api/drawings/render")
    def render(body: dict[str, Any] = Body(default={})) -> list[dict[str, str]]:  # noqa: B008
        import contextlib, io
        from ..cli.draw import draw
        with contextlib.redirect_stdout(io.StringIO()):
            draw(st.cfg.root, all_=True, no_render=bool(body.get("no_render")))
        return drawings()

    @app.get("/api/drawing/{name}")
    def drawing(name: str) -> FileResponse:
        p = (st.cfg.out / f"{name}.svg").resolve()
        if p.parent != st.cfg.out.resolve() or not p.exists(): raise HTTPException(404, "no such drawing")
        return FileResponse(p, media_type="image/svg+xml")

    static = files("schemagen.app").joinpath("static")
    if static.is_dir() and static.joinpath("index.html").is_file():
        app.mount("/assets", StaticFiles(directory=str(static.joinpath("assets"))), name="assets")

        @app.get("/", response_class=HTMLResponse)
        def page() -> HTMLResponse:
            return HTMLResponse(static.joinpath("index.html").read_text(encoding="utf-8"))
    else:
        @app.get("/", response_class=HTMLResponse)
        def nopage() -> HTMLResponse:
            return HTMLResponse("<!doctype html><title>schemagen</title><p>The frontend is not built: run <code>npm run build</code> in frontend/.</p>")
    return app


def bus_tree(st: State, op: Any) -> list[dict[str, Any]]:
    """Bus -> the protective devices fed from it (loading) -> the loads they protect (voltage)."""
    ctx, conds = st.ctx, st.m.conductors
    loads = {ld["component"]: ld for ld in op.loads}
    prot = {p["id"]: p for p in op.protective}
    volt = {b["id"]: b["voltage_V"] for b in op.buses}
    out = []
    for b in st.m.buses:
        if b.function_class == "GND": continue
        feeds = []
        for i, e in ctx.net.at.get((b.raw,), []):
            far = conds[i].end(3 - e)
            c = ctx.comp.get(far.device)
            if c and c.kind in ("breaker", "fuse") and c.id in prot:
                region = ctx.protected_by.get(c.id, [])
                kids = sorted({st.cid(conds[j].end(k).device) for j in region for k in (1, 2)} & set(loads))
                feeds.append(dict(id=c.id, **{k: prot[c.id][k] for k in ("current_A", "rating_A", "loading", "trips")},
                                  loads=[dict(id=k, voltage_V=loads[k]["voltage_V"], powered=loads[k]["powered"], v_min=loads[k]["v_min"]) for k in kids]))
        out.append(dict(id=b.id, voltage_V=volt.get(b.id, 0.0), feeds=sorted(feeds, key=lambda f: f["id"])))
    return out


def serve(project: str | Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import uvicorn
    app = create_app(project, background=True)  # listen at once; the project loads while the browser fetches the page
    url = f"http://{host}:{port}/"
    print(f"schemagen app: {url}  (Ctrl-C to stop)")
    if open_browser: threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
