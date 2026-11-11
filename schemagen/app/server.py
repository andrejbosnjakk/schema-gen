"""`schemagen app [<project>]`: a local server (FastAPI + uvicorn) and the bundled frontend. Nothing leaves the machine:
the server binds to 127.0.0.1 by default, the frontend is served from the wheel, no CDN, no telemetry.

Without a project it starts on the start screen (open the example, import a sheet, or a recent project). The 1.0 API
is docs/api.md; every error is {"error": {code, message, retry}} (app/errors.py), causes go to the log file.
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
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
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
from ..exporters.palette import HEX
from ..importers.records import text as text_of
from . import userdata
from . import workspace as ws
from .errors import AppError, body, convert, install

EDITABLE = {"label", "name", "awg", "colour", "cls", "st", "length", "amps", "notes", "func", "bus", "zone", "harn", "prot",
            "p1", "p1c", "p1p", "p1side", "p2", "p2c", "p2p", "p2side", "subsystem"}


class State:
    """The loaded project and everything derived from it; rebuilt after every change set."""

    def __init__(self, project: str | Path, background: bool = False):
        self.cfg = load_config(project)
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.error = ""
        self.failure: AppError | None = None
        self._json: bytes | None = None
        if background: threading.Thread(target=self._first_load, daemon=True).start()
        else: self.reload(); self.ready.set()

    def _first_load(self) -> None:
        try: self.reload(); self.index_json()
        except BaseException as e:  # noqa: BLE001  (shown to the user instead of a hung page)
            self.failure = convert(e, f"loading {self.cfg.root}"); self.error = self.failure.message
        self.ready.set()

    def wait(self) -> None:
        self.ready.wait()
        if self.failure: raise self.failure

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
        self.sources = ch.app_sources(ch.load_all(self.cfg.root))
        self._ws: dict[str, Any] | None = None
        self.overlay: dict[str, Any] | None = None

    def save(self, cs: ch.ChangeSet) -> None:
        """Store a change set and reload."""
        with self.lock:
            ch.save(self.cfg.root, cs)
            self.reload()

    # ---------------------------------------------------------------- refs
    def cid(self, raw: str) -> str:
        c = self.ctx.comp.get(raw)
        return c.id if c else raw

    def pin_id(self, t: Terminal) -> str:
        return f"{self.cid(t.device)}/{t.connector}/{t.pin}"

    def dname(self, cid: str) -> str:
        """A component's display name, with its code when the name does not contain it; the code when there is none."""
        c = self.ctx.comp_by_id.get(cid)
        n = (c.name if c else "") or cid
        return n if cid in n else f"{n} ({cid})"

    def pin_text(self, t: Terminal) -> str:
        return " ".join(x for x in (self.dname(self.cid(t.device)), t.connector, t.pin) if x)

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
            links = [link("pin", self.pin_id(c.from_), f"from {self.pin_text(c.from_)}"), link("pin", self.pin_id(c.to), f"to {self.pin_text(c.to)}"),
                     link("component", self.cid(c.from_.device), self.dname(self.cid(c.from_.device))),
                     link("component", self.cid(c.to.device), self.dname(self.cid(c.to.device))),
                     link("net", self.net_of.get(i, ""), f"net {self.net_of.get(i, '')}")]
            if c.harness: links.append(link("harness", c.harness))
            if c.protection: links.append(link("component", c.protection, f"protected by {self.dname(c.protection)}"))
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
            links = [link("component", comp.id, self.dname(comp.id))] + [link("conductor", conds[i].id, f"{conds[i].label} → {self.pin_text(conds[i].end(3 - e))}")
                                                                      for i, e in at]
            if at: links.append(link("net", self.net_of[at[0][0]], f"net {self.net_of[at[0][0]]}"))
            return dict(type=typ, id=oid, title=self.pin_text(t), props=props, links=links, issues=self.issues_for([f"pin:{oid}"]),
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
            links = [link("pin", p, " ".join(x for x in (self.dname(comp.id), *p.split("/")[1:]) if x)) for p in pins]
            links += [link("part", comp.part)] if comp.part else []
            if pd and pd.id in ctx.protected_by:
                links += [link("conductor", conds[i].id, f"protects {conds[i].label}") for i in ctx.protected_by[pd.id][:50]]
            return dict(type="connector" if comp.kind == "harness" else "component", id=oid, title=self.dname(comp.id), props=cprops, extra=comp.extra,
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
WIRE_FIELDS = {"label": "label", "name": "name", "gauge": "awg", "current": "amps", "notes": "notes"}
SOURCE_TYPES = ("battery", "dcdc", "bench")
OPEN_PATHS = ("/api/health", "/api/session", "/api/settings", "/api/open", "/api/import")


class Session:
    """The open project (or none: the start screen)."""

    def __init__(self) -> None:
        self.st: State | None = None

    def cur(self) -> State:
        if self.st is None: raise AppError("no-project", "No project is open. Open the example or import a wire sheet.")
        self.st.wait()
        return self.st

    def start(self, path: str | Path, background: bool = False) -> State:
        p = Path(path).expanduser()
        if p.is_file() and p.suffix.lower() in (".yml", ".yaml"): p = p.parent
        if not (p / "schemagen.yml").is_file(): raise AppError("not-found", f"There is no schemagen.yml in {p}.")
        st = State(p, background)
        if not background: st.wait()
        self.st = st
        userdata.add_recent(st.cfg.root.name, st.cfg.root)
        return st


def _open_folder(p: Path) -> None:
    """Show a folder in the file manager."""
    import os, sys
    if os.name == "nt": os.startfile(str(p))  # type: ignore[attr-defined]  # noqa: S606
    else: subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _num(v: Any, what: str, positive: bool = True) -> float | None:
    if v is None or v == "": return None
    try: x = float(v)
    except (TypeError, ValueError): raise AppError("bad-request", f"{what} must be a number, not '{v}'.") from None
    if positive and x <= 0: raise AppError("bad-request", f"{what} must be more than 0.")
    return x


def _keys(body: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(body, dict): raise AppError("bad-request", "The request body must be a JSON object.")
    extra = set(body) - allowed
    if extra: raise AppError("bad-request", f"Unknown field(s): {', '.join(sorted(extra))}.")
    return body


def create_app(project: str | Path | None = None, background: bool = False) -> FastAPI:
    S = Session()
    import inspect
    kw: dict[str, Any] = {}
    if "telemetry" in inspect.signature(FastAPI.__init__).parameters:  # FastAPI >= 0.16x: no traces, metrics or logs, never exported
        kw["telemetry"] = dict(tracing=False, metrics=False, logs=False, operation_spans=False, auto_configure=False, exclude=lambda scope: True)
    app = FastAPI(title="schemagen", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, **kw)
    install(app)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    from ..renderers.wireviz import graphviz
    app.state.graphviz = graphviz()  # checked once at start
    lg = userdata.log()
    lg.info("schemagen %s starting; graphviz: %s", __version__, app.state.graphviz)
    if project is not None: S.start(project, background)
    app.state.session = S

    @app.middleware("http")
    async def ready(request: Any, call_next: Any) -> Any:
        if request.url.path.startswith("/api/") and request.url.path not in OPEN_PATHS and S.st is not None:
            import anyio
            try: await anyio.to_thread.run_sync(S.st.wait)
            except AppError as e: return body(e.code, e.message, e.retry)
        return await call_next(request)

    def cur() -> State:
        return S.cur()

    # ---------------------------------------------------------------- 1.0: session and projects
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return dict(ready=S.st is None or S.st.ready.is_set(), version=__version__, graphviz=app.state.graphviz,
                    error=S.st.error if S.st else "")

    def info(st: State) -> dict[str, Any]:
        return dict(name=st.cfg.root.name, root=str(st.cfg.root), version=__version__, warnings=st.L.warnings if st.ready.is_set() and not st.failure else [])

    @app.get("/api/session")
    def session() -> dict[str, Any]:
        s = userdata.settings()
        recent = [r for r in s["recent"] if isinstance(r, dict) and Path(str(r.get("path", ""))).joinpath("schemagen.yml").is_file()]
        st = S.st
        return dict(project=info(st) if st and st.ready.is_set() and not st.failure else None, recent=recent, tour_done=bool(s["tour_done"]),
                    theme=s["theme"] if s["theme"] in ("light", "dark") else "light")

    @app.post("/api/settings")
    def settings(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        b = _keys(body, {"tour_done", "theme"})
        if "tour_done" in b and not isinstance(b["tour_done"], bool): raise AppError("bad-request", "tour_done must be true or false.")
        if "theme" in b and b["theme"] not in ("light", "dark"): raise AppError("bad-request", "theme must be light or dark.")
        userdata.save_settings(**b)
        return dict(ok=True)

    @app.post("/api/open")
    def open_(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        b = _keys(body, {"path", "example"})
        if b.get("example") is True:
            try: path = userdata.example()
            except FileNotFoundError as e: raise AppError("not-found", "The example project is missing from this installation.", detail=str(e)) from None
        elif isinstance(b.get("path"), str) and b["path"].strip(): path = Path(b["path"].strip())
        else: raise AppError("bad-request", "Give a project folder (path) or example: true.")
        return ws.workspace(S.start(path))

    @app.post("/api/import")
    async def import_(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        name = file.filename or "sheet.xlsx"
        if Path(name).suffix.lower() not in (".xlsx", ".csv"): raise AppError("bad-request", f"{name} is not a wire sheet: choose an .xlsx or .csv file.")
        data = await file.read()
        if not data: raise AppError("import-failed", f"{name} is empty.")
        import anyio

        def do() -> dict[str, Any]:
            try: folder = userdata.new_import(name, data)
            except ValueError as e: raise AppError("import-failed", f"{e}.") from None
            try: return ws.workspace(S.start(folder))
            except BaseException:
                import shutil
                shutil.rmtree(folder, ignore_errors=True)
                raise
        try: return await anyio.to_thread.run_sync(do)
        except AppError: raise
        except BaseException as e:  # noqa: BLE001
            a = convert(e, f"import {name}")
            raise AppError("import-failed", f"{name} could not be read: {a.message}" if a.code == "internal" else a.message) from None

    @app.get("/api/workspace")
    def workspace() -> dict[str, Any]:
        return ws.workspace(cur())

    # ---------------------------------------------------------------- 1.0: cards and edits
    @app.get("/api/card/component/{cid:path}")
    def card_component(cid: str) -> dict[str, Any]:
        out = ws.component_card(cur(), cid)
        if out is None: raise AppError("not-found", f"There is no component {cid}.")
        return out

    @app.get("/api/card/wire/{wid:path}")
    def card_wire(wid: str) -> dict[str, Any]:
        out = ws.wire_card(cur(), wid)
        if out is None: raise AppError("not-found", f"There is no wire {wid}.")
        return out

    @app.post("/api/component/{cid:path}")
    def edit_component(cid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        st = cur()
        b = _keys(body, {"name", "kind", "rating_A"})
        c = st.ctx.comp_by_id.get(cid)
        if c is None: raise AppError("not-found", f"There is no component {cid}.")
        from ..core.model import KINDS
        pd = next((p for p in st.m.protective_devices if p.id == cid), None)
        ops = []
        if "name" in b:
            if not isinstance(b["name"], str) or not b["name"].strip(): raise AppError("bad-request", "The name cannot be empty.")
            if b["name"].strip() != c.name: ops.append(ch.Op(op="component", id=cid, field="name", old=c.name, new=b["name"].strip(), row={"device": c.raw}))
        kind = c.kind
        if "kind" in b:
            if b["kind"] not in KINDS or b["kind"] == "harness": raise AppError("bad-request", f"kind must be one of {', '.join(k for k in KINDS if k != 'harness')}.")
            if c.kind == "harness": raise AppError("bad-request", f"{cid} is a harness connector; its kind comes from the project settings.")
            kind = b["kind"]
            if kind != c.kind: ops.append(ch.Op(op="component", id=cid, field="kind", old=c.kind, new=kind, row={"device": c.raw}))
        if "rating_A" in b:
            r = _num(b["rating_A"], "rating_A")
            if kind not in ("breaker", "fuse"): raise AppError("bad-request", f"{cid} is not a breaker or fuse, so it has no rating.")
            if r != (pd.rating_a if pd else None): ops.append(ch.Op(op="component", id=cid, field="rating_A", old=pd.rating_a if pd else None, new=r))
        if ops: st.save(ch.new_set(f"edit {cid} in the app", ops, author="app", slug="app-component"))
        return ws.workspace(st)

    @app.post("/api/wire/{wid:path}")
    def edit_wire(wid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        st = cur()
        b = _keys(body, set(WIRE_FIELDS))
        r = next((x for x in st.L.records if text_of(x.data.get("id")) == wid), None)
        if r is None: raise AppError("not-found", f"There is no wire {wid}.")
        if "current" in b: b["current"] = _num(b["current"], "current", positive=False)
        if "gauge" in b and not isinstance(b["gauge"], (str, int)): raise AppError("bad-request", "gauge must be text such as 20 or 20 AWG.")
        ops = []
        for k, v in b.items():
            f, new = WIRE_FIELDS[k], "" if v is None else v
            if text_of(new) != text_of(r.data.get(f)): ops.append(ch.Op(op="set", id=wid, field=f, old=text_of(r.data.get(f)), new=new))
        if ops: st.save(ch.new_set(f"edit {wid} in the app", ops, author="app", slug="app-edit"))
        return ws.workspace(st)

    @app.post("/api/positions")
    def positions(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        b = _keys(body, {"positions"})
        if not isinstance(b.get("positions"), dict): raise AppError("bad-request", "positions must be an object {id: [x, y]}.")
        try: ws.save_positions(cur(), b["positions"])
        except ValueError as e: raise AppError("bad-request", f"{e}.") from None
        return dict(ok=True)

    # ---------------------------------------------------------------- 1.0: simulate and app sources
    @app.post("/api/simulate")
    def simulate(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:  # noqa: B008
        st = cur()
        from ..sim.overlay import overlay
        try: st.overlay = overlay(st.m, st.cfg, st.sources, st.measured, st.ctx)
        except Exception as e:  # noqa: BLE001
            convert(e, "simulate")  # logs the cause
            raise AppError("sim-failed", "The simulation failed. The details are in the log file.", retry=True) from None
        return st.overlay

    @app.post("/api/sources")
    def add_source(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        st = cur()
        b = _keys(body, {"attach", "type", "nominal_V", "r_int_ohm", "i_limit_A", "capacity_Ah", "name"})
        if str(b.get("attach", "")) not in st.ctx.comp_by_id: raise AppError("not-found", f"There is no component {b.get('attach')} to attach the source to.")
        typ = b.get("type", "battery")
        if typ not in SOURCE_TYPES: raise AppError("bad-request", f"type must be one of {', '.join(SOURCE_TYPES)}.")
        v = _num(b.get("nominal_V"), "nominal_V")
        if v is None: raise AppError("bad-request", "nominal_V is needed (the source's voltage).")
        taken = {s["id"] for s in st.sources} | set(st.ctx.comp_by_id)
        sid = next(f"SRC-{k}" for k in range(1, 10_000) if f"SRC-{k}" not in taken)
        row = dict(name=str(b.get("name") or f"{ {'battery': 'Battery', 'dcdc': 'DC/DC', 'bench': 'Bench supply'}[typ]} {v:g} V"), attach=str(b["attach"]),
                   type=typ, nominal_V=v, r_int_ohm=_num(b.get("r_int_ohm"), "r_int_ohm") or 0.01, i_limit_A=_num(b.get("i_limit_A"), "i_limit_A"),
                   capacity_Ah=_num(b.get("capacity_Ah"), "capacity_Ah"))
        st.save(ch.new_set(f"add source {sid} in the app", [ch.Op(op="add-source", id=sid, row=row)], author="app", slug="app-source"))
        return ws.workspace(st)

    @app.delete("/api/sources/{sid}")
    def delete_source(sid: str) -> dict[str, Any]:
        st = cur()
        if sid not in {s["id"] for s in st.sources}: raise AppError("not-found", f"There is no source {sid}.")
        st.save(ch.new_set(f"delete source {sid} in the app", [ch.Op(op="delete-source", id=sid)], author="app", slug="app-source"))
        return ws.workspace(st)

    # ---------------------------------------------------------------- 1.0: export
    @app.post("/api/export")
    def export(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        st = cur()
        b = _keys(body, {"kind"})
        kind, out = b.get("kind"), st.cfg.out
        import contextlib, io
        before = {p: p.stat().st_mtime for p in out.rglob("*") if p.is_file()} if out.exists() else {}
        out.mkdir(parents=True, exist_ok=True)
        if kind == "drawings":
            from ..renderers.wireviz import GRAPHVIZ_MISSING, find_dot
            if not find_dot(): raise AppError("graphviz-missing", GRAPHVIZ_MISSING)
            from ..cli.draw import draw
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): draw(st.cfg.root, all_=True)
        elif kind == "pinout":
            from ..exporters import pinout as po
            po.write_xlsx(st.m, out / "pinout.xlsx", st.ctx); po.write_html(st.m, out / "pinout.html", st.ctx)
        elif kind == "faults":
            from ..sim import report
            report.run(st.cfg.root, faults=True, out=out / "faults", infer=True)
        elif kind == "wirelist":
            from ..exporters.views import wirelist_xlsx
            from ..renderers.project import Project
            wirelist_xlsx(Project(st.cfg), out / "wirelist.xlsx")
        else: raise AppError("bad-request", "kind must be drawings, pinout, faults or wirelist.")
        files = sorted(str(p.relative_to(out)).replace("\\", "/") for p in out.rglob("*") if p.is_file() and before.get(p) != p.stat().st_mtime)
        return dict(folder=str(out), files=files)

    @app.post("/api/reveal")
    def reveal(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        b = _keys(body, {"path"})
        if not isinstance(b.get("path"), str): raise AppError("bad-request", "Give the path to show.")
        p = Path(b["path"]).resolve()
        roots = [userdata.home().resolve()] + ([S.st.cfg.root.resolve()] if S.st else [])
        if not any(p == r or r in p.parents for r in roots): raise AppError("bad-request", "Only folders of the open project can be shown.")
        if not p.exists(): raise AppError("not-found", f"{p} does not exist.")
        _open_folder(p if p.is_dir() else p.parent)
        return dict(ok=True)

    # ---------------------------------------------------------------- 0.7 (CLI tests and power users)
    @app.get("/api/index")
    def index() -> Response:
        return Response(cur().index_json(), media_type="application/json")

    @app.get("/api/object")
    def obj(type: str, id: str) -> dict[str, Any]:  # noqa: A002
        return cur().obj(type, id)

    @app.get("/api/graph")
    def graph() -> dict[str, Any]:
        return cur().graph()

    @app.post("/api/edit")
    def edit(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        st = cur()
        cs = st.edit(body.get("edits", []), body.get("title", ""))
        return dict(changeset=cs.model_dump(), index=st.index())

    @app.post("/api/undo")
    def undo() -> dict[str, Any]:
        st = cur()
        with st.lock:
            p = ch.undo(st.cfg.root)
            st.reload()
        return dict(removed=p.name if p else None, index=st.index())

    @app.get("/api/fix/direction")
    def fix_preview() -> dict[str, Any]:
        from ..cli.commands import direction_changeset
        cs, flips = direction_changeset(cur().L)
        return dict(flips=[dict(id=f.id, label=f.label, reason=f.reason) for f in flips], ops=[o.model_dump() for o in cs.ops])

    @app.post("/api/fix/direction")
    def fix_apply() -> dict[str, Any]:
        from ..cli.commands import direction_changeset
        st = cur()
        cs, flips = direction_changeset(st.L)
        if not flips: raise HTTPException(400, "nothing to fix")
        st.save(cs)
        return dict(applied=len(flips), index=st.index())

    @app.get("/api/diff")
    def diff(rev: str = "HEAD") -> dict[str, Any]:
        st = cur()
        try: other = load(df.checkout(rev, st.cfg.root)).model
        except subprocess.CalledProcessError as e: raise HTTPException(400, f"git revision {rev!r} not found: {e.stderr!s}") from None
        except SystemExit as e: raise HTTPException(400, str(e)) from None
        d = df.diff(other, st.m)
        return dict(rev=rev, diff=d, text=df.text(d))

    @app.get("/api/sim/scenarios")
    def scenarios() -> list[str]:
        return cur().index()["project"]["scenarios"]

    @app.post("/api/sim/run")
    def sim_run(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
        from ..sim import api as sim
        from ..sim.report import _jsonable
        st = cur()
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
        st = cur()
        name = body.get("scenario")
        sc = yaml.safe_load((st.cfg.root / "scenarios" / str(name)).read_text(encoding="utf-8")) if name else None
        sw = sim.fault_sweep(st.m, st.cfg, sc, st.measured, st.ctx)
        return dict(_jsonable(sw))

    @app.get("/api/drawings")
    def drawings() -> list[dict[str, str]]:
        out = cur().cfg.out
        return [dict(name=p.stem) for p in sorted(out.glob("*.svg"))] if out.exists() else []

    @app.post("/api/drawings/render")
    def render(body: dict[str, Any] = Body(default={})) -> list[dict[str, str]]:  # noqa: B008
        import contextlib, io
        from ..cli.draw import draw
        with contextlib.redirect_stdout(io.StringIO()):
            draw(cur().cfg.root, all_=True, no_render=bool(body.get("no_render")))
        return drawings()

    @app.get("/api/drawing/{name}")
    def drawing(name: str) -> FileResponse:
        out = cur().cfg.out
        p = (out / f"{name}.svg").resolve()
        if p.parent != out.resolve() or not p.exists(): raise HTTPException(404, "no such drawing")
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


def serve(project: str | Path | None, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import uvicorn
    app = create_app(project, background=True)  # listen at once; the project loads while the browser fetches the page
    url = f"http://{host}:{port}/"
    print(f"schemagen app: {url}  (Ctrl-C to stop)" + ("" if project else ", start screen: no project given"))
    gv = app.state.graphviz
    if not gv["found"]: print(f"note: {gv['message']}")
    if open_browser: threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
