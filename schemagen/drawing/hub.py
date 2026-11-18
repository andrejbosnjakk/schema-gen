"""Terminal strips (docs/drawing-model.md, Strips). A drawing whose wires cannot be laid out on one sheet as a net (a bus or ground bus with many legs, a
controller whose runs go through splices and harness connectors over a dozen columns) is drawn the way it is wired: every part, splice and harness pin on the
run is a box or a bar, every wire a short stub from its terminal carrying the wire text and ending in a flat flag that names the far end
(`to Battery 14 V, + terminal (drawing BAT, sheet 3)`). Nothing is routed across the sheet, so nothing crosses.
The bars are the hub itself, the splices and harness pins the runs go through, and a part's pin that carries other conductors too; a conductor between two
boxes or bars is drawn at both ends and each flag names the other end's sheet. Pages are filled in order, the wire table of a sheet included in what must
fit (or left to table sheets, whichever makes fewer sheets), and evened out so that no sheet but the last is thin."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from ..app.workspace import _natural
from . import index as I
from . import symbols as S
from . import table as T
from .route import label_text
from .style import GRID, SIZE, areas, ceil_to, text_w

Elem = dict[str, Any]
BARS = ("splice", "bus", "ground")
HUB_MIN = 12        # legs at a bar in scope from which it is drawn as a strip however small the drawing
FLAT = 5.0          # height of a flat flag: one line
ZONE = 5.0          # room beside a symbol for the wire text, besides the text's own width


def _owner(sc: Elem) -> dict[str, tuple[Elem, Elem, Elem]]:
    return {p["anchor"]: (it, b, p) for it in sc["items"] for b in it["blocks"] for p in b["pins"]}


def _mine(sc: Elem, it: Elem) -> bool:
    return it["role"] == "in_scope" or (it["role"] == "harness" and it["code"] in sc["scope"]["ids"])


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


def words(sc: Elem, ref: str) -> str:
    from .layout import _words
    return _words(sc, ref)


def _split(sc: Elem, tall: bool) -> dict[str, Elem]:
    """The units, key -> {kind: bar|block, item, rows}: a row is the end of a conductor at the unit, {cid, e, at, other, far (the unit at the other end), text}."""
    own = _owner(sc)
    flagged = {f["at"] for f in sc["flags"]}

    def key(a: str) -> tuple[str, str, Elem] | None:
        it, b, p = own[a]
        if it["symbol"] in BARS:
            return (it["id"], "bar", it) if _mine(sc, it) or it["symbol"] == "splice" else (a, "bar", it) if a in flagged else None
        if it["symbol"] == "harness" and (tall or not _mine(sc, it)): return f"{it['id']}/{p['n']}", "block", it      # a pin of a harness connector: both halves, one row
        if _mine(sc, it): return it["id"], "block", it
        return (a, "block", it) if a in flagged else None                 # a part's pin that carries a flagged conductor: a box of its own
    units: dict[str, Elem] = {}
    for w in sc["wires"]:
        for at, other in ((w["a"], w["b"]), (w["b"], w["a"])):
            u, v = key(at), key(other)
            if u: units.setdefault(u[0], dict(kind=u[1], item=u[2], rows=[]))["rows"].append(dict(cid=w["id"], e=w, at=at, other=other, far=v[0] if v else None))
    for f in sc["flags"]:
        u = key(f["at"])
        if u: units.setdefault(u[0], dict(kind=u[1], item=u[2], rows=[]))["rows"].append(dict(cid=f["model"].removeprefix("conductor:"), e=f, at=f["at"], other=f["target"],
                                                                                              far=None, text=f["text"].removeprefix("→ ")))
    for u in units.values():
        pos = {p["anchor"]: (j, i) for j, b in enumerate(u["item"]["blocks"]) for i, p in enumerate(b["pins"])}
        u["rows"].sort(key=lambda r: ((pos[r["at"]], _natural(r["e"]["label"])) if u["kind"] == "block" else (_natural(r["e"]["label"]), _natural(r["cid"])), r["at"]))
    return units


def _bar(sc: Elem, key: str, u: Elem) -> Elem:
    """The item drawn for a bar: the hub or splice itself, or a stand-in dot for a bus that is the far end of a flagged conductor."""
    it = u["item"]
    if key == it["id"]: return it
    ref = u["rows"][0]["at"]
    head = words(sc, ref)
    if len(head) > 40: head = words(dict(sc, items=[dict(it, name="")]), ref)       # a long name: the code stands for it above the bar
    return dict(it, id=f"node:{key}", model=u["rows"][0]["e"]["model"], symbol="splice", kind="splice", code=head, name="", attrs={})


def _taps(key: str, it: Elem, rows: list[Elem], tall: bool) -> list[dict[str, Any]]:
    """The taps of one chunk of a bar, alternately left and right, in the order of the rows (10 mm apart when the flags have two lines); a bus names the stud a wire is on."""
    return [dict(id=f"{r['at']}#{r['cid']}", model=r["at"], side="LR"[i % 2], pitch=S.FLAG_H if tall else FLAT,
                 text=next((p["n"] for b in it["blocks"] for p in b["pins"] if p["anchor"] == r["at"]), "") if key == it["id"] and it["symbol"] == "bus" else "") for i, r in enumerate(rows)]


def _block(it: Elem, rows: list[Elem], tall: bool) -> tuple[Elem, dict[str, str], dict[tuple[str, str], str]]:
    """The part with the pins these rows use (and the spare ones between them), a row per conductor where a pin carries several: the item to draw, the sides to
    draw the anchors on (tall: alternately left and right, so two-line flags do not meet) and the anchor id of every (pin ref, conductor)."""
    used = Counter(r["at"] for r in rows)
    tid = {(r["at"], r["cid"]): (f"{r['at']}#{r['cid']}" if used[r["at"]] > 1 else r["at"]) for r in rows}
    nums = [_natural(p["n"]) for b in it["blocks"] for p in b["pins"] if p["anchor"] in used]
    blocks = []
    for b in it["blocks"]:
        idx = [i for i, p in enumerate(b["pins"]) if p["anchor"] in used]
        if it["symbol"] == "harness": keep = [p for p in b["pins"] if min(nums) <= _natural(p["n"]) <= max(nums)]
        elif idx: keep = [p for i, p in enumerate(b["pins"]) if min(idx) <= i <= max(idx) and (p["anchor"] in used or p["spare"])]
        else: continue
        pins = [q for p in keep for q in ([dict(p, anchor=tid[(r["at"], r["cid"])]) for r in rows if r["at"] == p["anchor"]] if used[p["anchor"]] > 1 else [p])]
        if pins: blocks.append(dict(b, pins=pins))
    item = dict(it, blocks=blocks, role="in_scope", symbol="block" if it["symbol"] in ("breaker", "fuse", "switch", "relay", "terminator", "battery", "dcdc") else it["symbol"],
                partial=it["partial"] or sum(len(b["pins"]) for b in blocks) < sum(len(b["pins"]) for b in it["blocks"]))     # a part with terminals on two sides is drawn as a box, its terminals in a column
    return item, ({t: "LR"[i % 2] for i, t in enumerate(tid[(r["at"], r["cid"])] for r in rows)} if tall and it["symbol"] != "harness" else {}), tid


def _chunk(sc: Elem, key: str, u: Elem, rows: list[Elem], tall: bool, x: float, y: float) -> tuple[Elem, list[Elem], dict[int, Elem]]:
    """The symbol of a unit holding these rows at (x, y), its texts, and for every row (by position) the anchor its stub starts at."""
    if u["kind"] == "bar":
        taps = _taps(key, u["item"], rows, tall)
        sy, tx = S.build(_bar(sc, key, u), x, y, None, taps)
        by = {a["id"]: a for a in sy["anchors"]}
        return sy, tx, {i: by[t["id"]] for i, t in enumerate(taps)}
    item, sides, tid = _block(u["item"], rows, tall)
    sy, tx = S.build(dict(item, id=item["id"] if key == item["id"] else f"{item['id']}#{key}"), x, y, sides)     # a pin's box has an id of its own
    back = {t: ref for (ref, _), t in tid.items()}
    for a in sy["anchors"]: a["model"] = back.get(a["model"], a["model"])
    for t in tx: t["model"] = back.get(t["model"], t["model"])
    by = {a["id"]: a for a in sy["anchors"]}
    return sy, tx, {i: by[tid[(r["at"], r["cid"])]] for i, r in enumerate(rows)}


def _text(sc: Elem, r: Elem, where: I.Where, own_id: str, sheet: int) -> str:
    """What the flag of a row says: the scene's own text for a flagged conductor, else the far end by name with the drawing and sheet it is on (this
    drawing and `sheet` when the far end is another unit of it)."""
    if "text" in r: return "→ " + r["text"]
    if r["far"]: return "→ " + words(sc, r["other"]) + I.suffix(own_id, [sheet])
    it = _owner(sc)[r["other"]][0]
    return "→ " + words(sc, r["other"]) + I.suffix(it["code"], where(it["code"], r["cid"]))


def _layout(sc: Elem, units: dict[str, Elem], cur: list[tuple[str, Elem]], flatw: dict[tuple[str, str, str], float], zone: float, aw: float) -> tuple[bool, float]:
    """(tall, height of the strip) of a page holding these rows: flat one-line flags when they fit the width of the sheet, else two-line flags at a 10 mm pitch."""
    ch: dict[str, list[Elem]] = defaultdict(list)
    for k, r in cur: ch[k].append(r)
    for tall in (False, True):
        sy = [_chunk(sc, k, units[k], rs, tall, 0.0, 0.0)[0] for k, rs in ch.items()]
        right = max(flatw[(k, r["cid"], r["at"])] for k, r in cur)
        both = any(units[k]["kind"] == "bar" or units[k]["item"]["symbol"] == "harness" for k in ch)     # a bar or a harness connector has stubs on both sides, a box only on its right
        if tall or (2 if both else 1) * (zone + right) + max(y["w"] for y in sy) <= aw: break
    return tall, sum(y["h"] + GRID for y in sy)


def _plan(sc: Elem, units: dict[str, Elem], size: str, inline: bool, flatw: dict[tuple[str, str, str], float], zone: float) -> list[tuple[list[tuple[str, Elem]], bool]]:
    """The rows in order cut into pages (rows, tall): filled while the strip (and, when inline, its wire table) fits the sheet, then evened out."""
    ax, ay, aw, ah = areas(size)["area"]
    order = sorted(units, key=lambda k: (not _mine(sc, units[k]["item"]), _natural(k)))
    seq = [(k, r) for k in order for r in units[k]["rows"]]

    def height(cur: list[tuple[str, Elem]]) -> float:
        return _layout(sc, units, cur, flatw, zone, aw)[1] + (T.height(len({r["cid"] for _, r in cur})) if inline else 0.0)

    def fill(limit: int) -> list[list[tuple[str, Elem]]]:
        pgs: list[list[tuple[str, Elem]]] = [[]]
        for item in seq:
            cur = pgs[-1] + [item]
            if pgs[-1] and (len(cur) > limit or height(cur) > ah): pgs.append([item])
            else: pgs[-1] = cur
        return pgs
    first = fill(10 ** 9)
    pgs = fill(-(-len(seq) // len(first)))                       # as many pages as that needed, evenly filled
    return [(pg, _layout(sc, units, pg, flatw, zone, aw)[0]) for pg in (first if len(pgs) > len(first) else pgs)]


def pages(sc: Elem, size: str, where: I.Where) -> list[Elem]:
    """The pages of a strip drawing (layout.place draws them: `hub` is set)."""
    aw = areas(size)["area"][2]
    own_id = sc["scope"]["text"].partition(":")[2]
    units = _split(sc, False)
    rows = [r for u in units.values() for r in u["rows"]]
    zone = ceil_to(max([text_w(label_text(r["e"]), SIZE) for r in rows] + [0.0]) + ZONE)
    if any(u["item"]["symbol"] == "harness" and u["kind"] == "block" for u in units.values()):        # a harness box needs one-line flags everywhere
        top = max(S.flag("", "", "off_sheet", _text(sc, r, where, own_id, 44), "", None, h=FLAT)["w"] for r in rows)
        if 2 * (zone + top) + max(_chunk(sc, k, u, u["rows"], False, 0.0, 0.0)[0]["w"] for k, u in units.items()) > aw:
            units = _split(sc, True)                   # they do not fit both sides: a bar per pin instead
            rows = [r for u in units.values() for r in u["rows"]]
    flatw = {(k, r["cid"], r["at"]): S.flag("", "", "off_sheet", _text(sc, r, where, own_id, 44), "", None, h=FLAT)["w"] for k, u in units.items() for r in u["rows"]}
    plans = [_plan(sc, units, size, inline, flatw, zone) for inline in (True, False)]
    tab = lambda p: math.ceil(sum(len({r["cid"] for _, r in pg}) + 1 for pg, _ in p) / (int(areas(size)["area"][3] / T.ROW) - 1))   # noqa: E731
    pgs = plans[0] if len(plans[0]) <= len(plans[1]) + tab(plans[1]) else plans[1]
    where_row = {(k, r["cid"], r["at"]): n for n, (pg, _) in enumerate(pgs, 1) for k, r in pg}
    out = []
    for n, (pg, tall) in enumerate(pgs, 1):
        ch: dict[str, list[Elem]] = defaultdict(list)
        for k, r in pg: ch[k].append(r)
        used = {r["at"] for _, r in pg}
        flags = []
        for k, r in pg:
            f = dict(id=f"flag:{r['cid']}:{r['at']}", model=r["e"]["model"], kind="off_sheet", at=r["at"], target=r["other"], target_item="", label=r["e"]["label"], gauge=r["e"]["gauge"],
                     colour=r["e"]["colour"], hex=r["e"]["hex"], cls=r["e"].get("cls", ""), weight=r["e"]["weight"], tap=(k, r["cid"], r["at"]))
            f["text"] = _text(sc, r, where, own_id, where_row[(r["far"], r["cid"], r["other"])] if r["far"] else 0)
            if r["e"].get("covers"): f["covers"] = r["e"]["covers"]
            flags.append(f)
        items = [dict(it, blocks=[dict(b, pins=[p for p in b["pins"] if p["anchor"] in used]) for b in it["blocks"] if any(p["anchor"] in used for p in b["pins"])])
                 for it in sc["items"] if any(p["anchor"] in used for b in it["blocks"] for p in b["pins"])]
        out.append(dict(scope=sc["scope"], title=sc["title"], project=sc["project"], items=items, wires=[], flags=flags, n=n, hub=True, tall=tall,
                        chunks=[(k, units[k], rs) for k, rs in ch.items()]))
    return out


def place(page: Elem, size: str, reserve: float = 0.0) -> Elem:
    """Draws a strip page: the units stacked at the top of the area, a stub and a flat flag (two lines when `tall`) per row; flags stand in a column on each side."""
    ax, ay, aw, ah = areas(size)["area"]
    tall, h = page["tall"], (S.FLAG_H if page["tall"] else FLAT)
    flags_by = {f["tap"]: f for f in page["flags"]}
    fl = {t: S.flag("", f["model"], "off_sheet", f["text"], f["target"], None, h=h) for t, f in flags_by.items()}
    zone = ceil_to(max([text_w(label_text(r["e"]), SIZE) for _, _, rs in page["chunks"] for r in rs] + [0.0]) + ZONE)
    built = []
    for key, u, rs in page["chunks"]:
        sy, _, anc = _chunk(page, key, u, rs, tall, 0.0, 0.0)
        built.append((key, u, rs, sy["w"], [anc[i]["side"] if anc[i]["side"] in "LR" else "R" for i in range(len(rs))]))
    wide = max([b[3] for b in built] + [0.0])
    side_w = {s: max([fl[(k, r["cid"], r["at"])]["w"] for k, _, rs, _, sd in built for r, q in zip(rs, sd) if q == s] + [0.0]) for s in "LR"}
    left = (zone + side_w["L"]) if side_w["L"] else 0.0
    x0 = ax + left + max(0.0, (aw - left - wide - zone - side_w["R"]) // 2 // GRID * GRID)
    syms, texts, flags, wires = [], [], [], []
    y = ay
    for key, u, rs, w0, sd in built:
        sy, tx, anc = _chunk(page, key, u, rs, tall, x0, y)
        syms.append(sy); texts += tx
        for i, (r, s) in enumerate(zip(rs, sd)):
            a = anc[i]
            f0, w = flags_by[(key, r["cid"], r["at"])], fl[(key, r["cid"], r["at"])]["w"]
            fx = (x0 - zone - w) if s == "L" else x0 + wide + zone
            flags.append(S.flag(f0["id"], f0["model"], "off_sheet", f0["text"], f0["target"], None, fx, a["y"] - h / 2, "R" if s == "L" else "L", h=h))
            if f0.get("covers"): flags[-1]["covers"] = f0["covers"]
            ex = fx + w if s == "L" else fx
            wid = r["cid"] + ("~" if any(q["model"] == r["e"]["model"] for q in wires) else "")
            wires.append(dict(id=wid, model=r["e"]["model"], label=r["e"]["label"], gauge=r["e"]["gauge"], colour=r["e"]["colour"], hex=r["e"]["hex"], weight=r["e"]["weight"],
                              points=[[a["x"], a["y"]], [ex, a["y"]]], a=a["id"], b=f0["id"], pair=r["e"].get("pair", ""), shield=r["e"].get("shield", ""), fault=r["e"].get("fault")))
            if not f0.get("covers"): texts.append(S.text(label_text(r["e"]), (ex + 2.5) if s == "L" else (a["x"] + 2.5), a["y"] - 2.5, "left", "wire", model=r["e"]["model"]))   # a summary flag's stub is silent
        y += sy["h"] + GRID
    return dict(symbols=syms, wires=wires, texts=texts, flags=flags, w=aw, h=y - GRID - ay, bad=0)
