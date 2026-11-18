"""What the wire list says, for the verifier: every conductor with its two ends, gauge and colour, the components and their connector names, and the
conductors a drawing of a scope must show. Reads the project only through schemagen.core (model, net, importer); nothing of the drawing engine."""
from __future__ import annotations

import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.config import load_config
from ..core.context import Ctx
from ..core.load import load

Term = tuple[str, str, str]   # component id, connector, pin


@dataclass
class Cond:
    i: int
    id: str
    label: str
    gauge: str
    colour: str
    a: Term
    b: Term


@dataclass
class Expected:
    conds: list[Cond]
    kind: dict[str, str]                      # component id -> model kind
    conns: dict[str, set[str]]                # component id -> connector names its conductors use
    ctx: Any
    source: dict[str, str] = field(default_factory=dict)   # name, sha256 of the source file(s)
    names: list[tuple[str, str]] = field(default_factory=list)   # (lower-case printed form, component id), longest first: id, display name, both, raw device string

    def lead(self, text: str) -> tuple[str | None, str]:
        """The component a text starts with (its id or display name, longest match; a leading `ground bus`, `bus` or `splice` is skipped) and the rest of the text."""
        raw = " ".join(text.split())
        for t in (raw, re.sub(r"^(ground bus|bus|splice)\s+", "", raw, flags=re.I)):   # `bus strip` can be a name; `bus BB1` is how the table says a bus
            r = self._lead(t)
            if r[0]: return r
        return self._lead(raw)

    def _lead(self, t: str) -> tuple[str | None, str]:
        low = t.lower()
        for k, cid in self.names:
            if low == k: return cid, ""
            if low.startswith(k) and not low[len(k)].isalnum() and not (low[len(k)] == "-" and low[len(k) + 1:len(k) + 2].isalnum()): return cid, t[len(k):].strip(" ,")
        cut = low[:-2].rstrip() if low.endswith("..") else low   # a name cut short (`..`) or given without its bracket: the one component whose name starts so
        hit = {cid for k, cid in self.names if (len(cut) >= 12 or low.endswith("..")) and len(cut) >= 6 and k.startswith(cut)}
        return (hit.pop(), "") if len(hit) == 1 else (None, t)

    def scope(self, text: str) -> set[int] | None:
        """Indices of the conductors a drawing of `text` must show (a wire or an off-sheet flag); None for a scope kind the verifier does not know."""
        kind, _, rest = text.partition(":")
        ids = [x for x in rest.replace("+", ",").split(",") if x]
        ctx, net, conds = self.ctx, self.ctx.net, self.ctx.m.conductors
        if text == "system": comps = list(ctx.m.components)
        elif kind in ("component", "harness", "selection") and ids and all(i in ctx.comp_by_id for i in ids): comps = [ctx.comp_by_id[i] for i in ids]
        else: return None
        start = {net.node(i, e) for c in comps for i, e in net.by_dev[c.raw]}
        nodes, todo = set(start), deque(start)
        while todo:   # a run goes through splices and harness pins until it lands on anything else
            n = todo.popleft()
            for j, k in net.at[n]:
                far = net.node(j, 3 - k)
                if far not in nodes:
                    nodes.add(far)
                    if net.role(conds[j].end(3 - k).device) in ("splice", "harness"): todo.append(far)
        return {i for i in range(len(conds)) if net.node(i, 1) in nodes or net.node(i, 2) in nodes}

    def reach(self, c: Cond, end: int) -> set[str]:
        """Component ids on the run that leaves end 1 or 2 of a conductor: the end itself, then through splices and harness pins until devices."""
        net, conds = self.ctx.net, self.ctx.m.conductors
        seen: set[Any] = set()
        out: set[str] = set()
        todo = deque([(c.i, end)])
        while todo:
            i, e = todo.popleft()
            t = conds[i].end(e)
            out.add(self.ctx.comp[t.device].id if t.device in self.ctx.comp else t.device)
            if net.role(t.device) in ("splice", "harness") and (i, e) not in seen:
                seen.add((i, e))
                for j, k in net.at[net.node(i, e)]:
                    if (j, k) != (i, e): todo.append((j, 3 - k))
        return out


def gauge(g: str) -> str:
    """A gauge as a drawing prints it, without the unit word."""
    return re.sub(r"\s*awg\s*", "", str(g or ""), flags=re.I).strip()


def source_digest_of(path: Path) -> dict[str, str]:
    """Name and sha256 of a given source file."""
    return dict(name=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def source_digest(cfg: Any) -> dict[str, str]:
    """Name and sha256 of the file the wire list comes from (the spreadsheet), else of the wirelist folder's files together."""
    src = getattr(cfg, "source", None) or {}
    if src.get("path"):
        f = Path(cfg.root) / src["path"]
        return dict(name=f.name, sha256=hashlib.sha256(f.read_bytes()).hexdigest())
    h = hashlib.sha256()
    files = sorted(p for p in Path(cfg.wirelist).rglob("*") if p.is_file() and p.suffix in (".py", ".json", ".yml", ".csv", ".xlsx"))
    for p in files: h.update(p.name.encode()); h.update(p.read_bytes())
    return dict(name=Path(cfg.wirelist).name, sha256=h.hexdigest())


def read(project: str | Path) -> Expected:
    """Loads the project (as `schemagen check` does) and lists its conductors."""
    cfg = load_config(project)
    L = load(cfg)
    ctx = Ctx(L.model, cfg)
    cid = lambda t: (ctx.comp[t.device].id if t.device in ctx.comp else t.device, t.connector, t.pin)  # noqa: E731
    conds = [Cond(i, c.id, c.label, gauge(c.gauge), c.colour_code or c.colour, cid(c.from_), cid(c.to)) for i, c in enumerate(L.model.conductors)]
    conns: dict[str, set[str]] = {}
    for c in conds:
        for t in (c.a, c.b): conns.setdefault(t[0], set()).add(t[1])
    names: dict[str, str] = {}
    for m in L.model.components:
        for k in (m.id, m.name, f"{m.id} {m.name}", m.raw, re.sub(r"\s*\([^)]*\)", "", m.name)): names.setdefault(" ".join(k.lower().split()), m.id)   # the last: a name without its bracket
    names.pop("", None)
    return Expected(conds, {c.id: c.kind for c in L.model.components}, conns, ctx, source_digest(cfg), sorted(names.items(), key=lambda kv: -len(kv[0])))
