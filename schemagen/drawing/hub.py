"""Hubs drawn as a terminal strip (docs/drawing-model.md, Hubs). A bus, ground bus or splice with many legs that go to as many different parts cannot be
laid out as a net of wires without a page full of crossings; it is drawn the way it is built: a bar with one short stub per wire, the stub carrying the wire
text and ending in a flat flag that names the far end (`to Battery 14 V, + terminal (drawing BAT, sheet 3)`). Nothing is routed across the sheet.
Every node of the run that is not a part (the hub itself, the splices and harness pins it runs through, a part's pin that carries other conductors too) is
a small bar of its own with a stub per conductor; a conductor between two of them is drawn at both ends and each flag names the other one's sheet.
Pages are filled in order, the wire table of a sheet included in what must fit, and evened out so that no sheet but the last is thin."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..app.workspace import _natural
from . import index as I
from . import symbols as S
from . import table as T
from .route import label_text
from .style import GRID, SIZE, areas, ceil_to, text_w

Elem = dict[str, Any]
BARS = ("splice", "bus", "ground")
HUB_MIN = 12        # legs at the hub from which it is drawn as a strip
FLAT = 5.0          # height of a strip flag: one line
ZONE = 10.0         # room beside the bar for the wire text, besides the text's own width


def _owner(sc: Elem) -> dict[str, tuple[Elem, Elem, Elem]]:
    return {p["anchor"]: (it, b, p) for it in sc["items"] for b in it["blocks"] for p in b["pins"]}


def is_hub(sc: Elem) -> bool:
    """One bar in scope with at least HUB_MIN legs, whose far ends are mostly different parts."""
    if sc["scope"]["kind"] != "component": return False
    xs = [i for i in sc["items"] if i["role"] == "in_scope"]
    if len(xs) != 1 or xs[0]["symbol"] not in BARS: return False
    own = _owner(sc)
    mine = {p["anchor"] for b in xs[0]["blocks"] for p in b["pins"]}
    far = [own[w["b"] if w["a"] in mine else w["a"]][0]["id"] for w in sc["wires"] if w["a"] in mine or w["b"] in mine]
    far += [f["target"] for f in sc["flags"] if f["at"] in mine]
    return len(far) >= HUB_MIN and 2 * len(set(far)) >= len(far)


def _unit(own: dict[str, tuple[Elem, Elem, Elem]], a: str) -> tuple[str, Elem] | None:
    """The strip bar the end at anchor `a` belongs to: (key, item), or None when the end is simply a flag at the other side of a stub."""
    it, b, p = own[a]
    if it["role"] == "in_scope" or it["symbol"] == "splice": return it["id"], it
    if it["symbol"] == "harness": return f"{it['id']}/{p['n']}", it
    return None


def words(sc: Elem, ref: str) -> str:
    from .layout import _words
    return _words(sc, ref)


def _split(sc: Elem, where: I.Where) -> tuple[dict[str, Elem], list[Elem]]:
    """The bars (key -> {item, rows}) and, per row, the end of a conductor at a bar: {unit, cid, e, at, other, text, drawing}."""
    own = _owner(sc)
    units: dict[str, Elem] = {}
    rows: list[Elem] = []
    flagged = {f["at"] for f in sc["flags"]}

    def key(a: str) -> tuple[str, Elem] | None:
        u = _unit(own, a)
        if u or a not in flagged: return u
        return a, own[a][0]                                   # a part's pin that carries a flagged conductor: a node of its own
    for w in sc["wires"]:
        for at, other in ((w["a"], w["b"]), (w["b"], w["a"])):
            u, v = key(at), key(other)
            if u: rows.append(dict(unit=u[0], item=u[1], cid=w["id"], e=w, at=at, other=other, far=v[0] if v else None))
    for f in sc["flags"]:
        u = key(f["at"])
        if u: rows.append(dict(unit=u[0], item=u[1], cid=f["model"].removeprefix("conductor:"), e=f, at=f["at"], other=f["target"], text=f["text"].removeprefix("→ "), far=None))
    for r in rows: units.setdefault(r["unit"], dict(item=r["item"], rows=[]))["rows"].append(r)
    for u in units.values(): u["rows"].sort(key=lambda r: (_natural(r["e"]["label"]), _natural(r["cid"]), r["at"]))
    return units, rows


def _bar(sc: Elem, key: str, u: Elem) -> Elem:
    """The item drawn for a bar: the hub or splice itself, or a stand-in dot for a harness pin or a part's pin that carries several conductors."""
    it = u["item"]
    if key == it["id"]: return it
    ref = u["rows"][0]["at"]
    return dict(it, id=f"node:{key}", model=u["rows"][0]["e"]["model"], symbol="splice", kind="splice", code=words(sc, ref), name="", attrs={})


def _taps(key: str, rows: list[Elem], pitch: float = FLAT) -> list[dict[str, Any]]:
    """The taps of one chunk of a bar, alternately left and right, in the order of the rows; a bus names the stud a wire is on."""
    return [dict(id=f"{r['at']}#{r['cid']}", model=r["at"], side="LR"[i % 2], pitch=pitch,
                 text=next((p["n"] for b in r["item"]["blocks"] for p in b["pins"] if p["anchor"] == r["at"]), "") if key == r["item"]["id"] and r["item"]["symbol"] == "bus" else "")
            for i, r in enumerate(rows)]


def _height(sc: Elem, chunks: list[tuple[str, Elem, list[Elem]]], ncid: int, pitch: float) -> float:
    """Height of the strip of a page with these chunks plus the wire table under it."""
    h = 0.0
    for key, u, rs in chunks:
        sy, _ = S.build(_bar(sc, key, u), 0.0, 0.0, None, _taps(key, rs, pitch))
        h += sy["h"] + GRID
    return h + T.height(ncid)


def _text(sc: Elem, r: Elem, where: I.Where, own_id: str, sheet: int) -> str:
    """What the flag of a row says: the scene's own text for a flagged conductor, else the far end by name with the drawing and sheet it is on (this
    drawing and `sheet` when the far end is another bar of it)."""
    if "text" in r: return "→ " + r["text"]
    if r["far"]: return "→ " + words(sc, r["other"]) + I.suffix(own_id, [sheet])
    it = _owner(sc)[r["other"]][0]
    return "→ " + words(sc, r["other"]) + I.suffix(it["code"], where(it["code"], r["cid"]))


def pages(sc: Elem, size: str, where: I.Where) -> list[Elem]:
    """The pages of a hub's drawing (layout.place draws them: `hub` is set)."""
    ah = areas(size)["area"][3]
    units, _ = _split(sc, where)
    order = sorted(units, key=lambda k: (units[k]["item"]["role"] != "in_scope", _natural(k)))
    seq = [(k, r) for k in order for r in units[k]["rows"]]
    own_id = sc["scope"]["text"].partition(":")[2]
    zone = ceil_to(max([text_w(label_text(r["e"]), SIZE) for _, r in seq] + [0.0]) + ZONE)
    flat = max([S.flag("", "", "off_sheet", _text(sc, r, where, own_id, 44), "", None, h=FLAT)["w"] for _, r in seq] + [0.0])
    pitch = FLAT if 2 * (zone + flat) + 40 <= areas(size)["area"][2] else S.FLAG_H     # one-line flags when both sides fit the sheet, else two lines

    def fill(limit: int) -> list[list[tuple[str, Elem]]]:
        pgs: list[list[tuple[str, Elem]]] = [[]]
        for k, r in seq:
            cur = pgs[-1] + [(k, r)]
            ch: dict[str, list[Elem]] = defaultdict(list)
            for kk, rr in cur: ch[kk].append(rr)
            full = pgs[-1] and (len(cur) > limit or _height(sc, [(kk, units[kk], rs) for kk, rs in ch.items()], len({rr["cid"] for _, rr in cur}), pitch) > ah)
            if full: pgs.append([(k, r)])
            else: pgs[-1] = cur
        return pgs
    first = fill(10 ** 9)
    pgs = fill(-(-len(seq) // len(first)))                       # as many pages as that needed, evenly filled
    if len(pgs) > len(first): pgs = first
    where_row: dict[tuple[str, str, str], int] = {}              # (bar, conductor, anchor) -> the page its stub is on
    for n, pg in enumerate(pgs, 1):
        for k, r in pg: where_row[(k, r["cid"], r["at"])] = n
    out = []
    for n, pg in enumerate(pgs, 1):
        ch: dict[str, list[Elem]] = defaultdict(list)
        for k, r in pg: ch[k].append(r)
        used = {r["at"] for _, r in pg}
        flags = []
        for k, r in pg:
            f = dict(id=f"flag:{r['cid']}:{r['at']}", model=r["e"]["model"], kind="off_sheet", at=r["at"], target=r["other"], target_item="", label=r["e"]["label"], gauge=r["e"]["gauge"],
                     colour=r["e"]["colour"], hex=r["e"]["hex"], cls=r["e"].get("cls", ""), weight=r["e"]["weight"], key=k, tap=(k, r["cid"], r["at"]))
            f["text"] = _text(sc, r, where, own_id, where_row[(r["far"], r["cid"], r["other"])] if r["far"] else 0)
            flags.append(f)
        items = [dict(it, blocks=[dict(b, pins=[p for p in b["pins"] if p["anchor"] in used]) for b in it["blocks"] if any(p["anchor"] in used for p in b["pins"])])
                 for it in sc["items"] if any(p["anchor"] in used for b in it["blocks"] for p in b["pins"])]
        out.append(dict(scope=sc["scope"], title=sc["title"], project=sc["project"], items=items, wires=[], flags=flags, n=n, hub=True,
                        chunks=[(k, units[k], rs) for k, rs in ch.items()], pitch=pitch))
    return out


def place(page: Elem, size: str, reserve: float = 0.0) -> Elem:
    """Draws a hub page: the bars stacked at the top of the area, centred on one axis, a stub and a flat flag per row."""
    ax, ay, aw, ah = areas(size)["area"]
    built = []
    h = page["pitch"]
    for key, u, rs in page["chunks"]:
        built.append((key, rs, _taps(key, rs, h), _bar(page, key, u)))
    flags_by = {f["tap"]: f for f in page["flags"]}
    zone = ceil_to(max([text_w(label_text(r["e"]), SIZE) for _, rs, _, _ in built for r in rs] + [0.0]) + ZONE)
    fl = {t: S.flag("", f["model"], "off_sheet", f["text"], f["target"], None, h=h) for t, f in flags_by.items()}
    maxw = {s: max([fl[(k, r["cid"], r["at"])]["w"] for k, rs, taps, _ in built for r, t in zip(rs, taps) if t["side"] == s] + [0.0]) for s in "LR"}
    syms, texts, flags, wires = [], [], [], []
    y = ay
    probes = [S.build(b, 0.0, 0.0, None, taps)[0]["w"] for _, _, taps, b in built]
    xc = ax + ceil_to(zone + maxw["L"]) + max(probes) / 2
    xc = xc + max(0.0, (aw - (2 * zone + maxw["L"] + maxw["R"] + max(probes))) // 2 // GRID * GRID)
    for key, rs, taps, bar in built:
        w0 = S.build(bar, 0.0, 0.0, None, taps)[0]["w"]
        sy, tx = S.build(bar, xc - w0 / 2, y, None, taps)
        syms.append(sy); texts += tx
        anc = {a["id"]: a for a in sy["anchors"]}
        for r, t in zip(rs, taps):
            a = anc[t["id"]]
            f0 = flags_by[(key, r["cid"], r["at"])]
            w = fl[(key, r["cid"], r["at"])]["w"]
            left = t["side"] == "L"
            fx = a["x"] - zone - w if left else a["x"] + zone
            fid = f0["id"]
            flags.append(S.flag(fid, f0["model"], "off_sheet", f0["text"], f0["target"], None, fx, a["y"] - h / 2, "R" if left else "L", h=h))
            ex = fx + w if left else fx
            wid = r["cid"] + ("~" if sum(1 for q in wires if q["model"] == r["e"]["model"]) else "")
            wires.append(dict(id=wid, model=r["e"]["model"], label=r["e"]["label"], gauge=r["e"]["gauge"], colour=r["e"]["colour"], hex=r["e"]["hex"], weight=r["e"]["weight"],
                              points=[[a["x"], a["y"]], [ex, a["y"]]], a=a["id"], b=fid, pair=r["e"].get("pair", ""), shield=r["e"].get("shield", ""), fault=r["e"].get("fault")))
            texts.append(S.text(label_text(r["e"]), (ex + 2.5) if left else (a["x"] + 2.5), a["y"] - 2.5, "left", "wire", model=r["e"]["model"]))
        y += sy["h"] + GRID
    return dict(symbols=syms, wires=wires, texts=texts, flags=flags, w=aw, h=y - GRID - ay, bad=0)
