// Where the cards go. Each zone is a block with its own power-flow columns (Node.rank, left to right, tall columns
// wrapped); blocks sit in macro columns by their lowest rank (sources left, loads right), stacked and split so the whole
// system fits a wide screen. Card order inside a column follows the barycentre of its neighbours (fewer crossings).
// Plus the edge curve and the label pass.
import type { Edge, Node, Zone } from "../types";

export const CW = 184, CH = 44;            // card size (fixed: the edge geometry depends on it)
const GX = 112, GSUB = 20, GY = 12;        // gap between rank columns, between wrapped sub-columns, between rows
const HEAD = 30, PAD = 16, GB = 28, GBX = 120;  // block label room, block padding, gap between stacked blocks, between block columns
export type XY = { x: number; y: number };

interface Block { members: string[]; groups: string[][]; key: number; w: number; h: number; x: number; y: number }

/** Top-left position of every card, before any user-dragged position is applied. */
export function layout(nodes: Node[], edges: Edge[], zones: Zone[], aspect = 2.4): Map<string, XY> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const ranks = [...new Set(nodes.map((n) => n.rank))].sort((a, b) => a - b);
  const seen = new Set<string>(), blocks: Block[] = [];
  const mk = (ids: string[]) => {
    const ms = ids.filter((id) => byId.has(id) && !seen.has(id));
    ms.forEach((id) => seen.add(id));
    if (!ms.length) return;
    const groups = ranks.map((r) => ms.filter((id) => byId.get(id)!.rank === r).sort((a, b) => byId.get(a)!.name.localeCompare(byId.get(b)!.name)));
    blocks.push({ members: ms, groups, key: Math.min(...ms.map((id) => byId.get(id)!.rank)), w: 0, h: 0, x: 0, y: 0 });
  };
  for (const z of zones) mk(z.members);
  mk(nodes.map((n) => n.id));  // components in no zone
  const adj = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) if (byId.has(e.a) && byId.has(e.b) && e.a !== e.b) { adj.get(e.a)!.push(e.b); adj.get(e.b)!.push(e.a); }

  const place = (R: number, H: number, pos: Map<string, XY>) => {
    for (const b of blocks) {  // inside a block: rank columns, each wrapped to at most R rows
      let x = 0, rows = 0;
      const local: [string, number, number][] = [];
      for (const g of b.groups) {
        if (!g.length) continue;
        const k = Math.ceil(g.length / R), per = Math.ceil(g.length / k);
        rows = Math.max(rows, per);
        g.forEach((id, i) => local.push([id, x + Math.floor(i / per) * (CW + GSUB), (i % per) - (Math.min(per, g.length - Math.floor(i / per) * per)) / 2]));
        x += k * CW + (k - 1) * GSUB + GX;
      }
      b.w = x - GX + 2 * PAD; b.h = rows * (CH + GY) - GY + HEAD + PAD;
      (b as Block & { local?: typeof local; rows?: number }).local = local; (b as Block & { rows?: number }).rows = rows;
    }
    // macro columns by lowest rank; a column taller than H splits into several
    let x = 0;
    for (const key of [...new Set(blocks.map((b) => b.key))].sort((a, b) => a - b)) {
      let y = 0, cw = 0;
      for (const b of blocks.filter((b) => b.key === key)) {
        if (y > 0 && y + b.h > H) { x += cw + GBX; y = 0; cw = 0; }
        b.x = x; b.y = y; y += b.h + GB; cw = Math.max(cw, b.w);
      }
      x += cw + GBX;
    }
    for (const b of blocks) {
      const { local, rows } = b as Block & { local: [string, number, number][]; rows: number };
      for (const [id, lx, r] of local) pos.set(id, { x: b.x + PAD + lx, y: b.y + HEAD + (rows / 2 + r) * (CH + GY) });
    }
  };
  const box = (pos: Map<string, XY>) => {
    let w = 0, h = 0;
    for (const p of pos.values()) { w = Math.max(w, p.x + CW); h = Math.max(h, p.y + CH); }
    return { w, h };
  };

  // the row limit and column height whose layout is closest to the screen's aspect (then the smaller one)
  const maxG = Math.max(1, ...blocks.flatMap((b) => b.groups.map((g) => g.length)));
  let best = { R: maxG, H: Infinity }, bestScore = Infinity;
  const tallest = Math.max(...blocks.map((b) => b.members.length)) * (CH + GY);
  for (let R = Math.min(maxG, 40); R >= 3; R--) for (const f of [0.5, 0.75, 1, 1.5, 2, 3, 5, 100]) {
    const H = Math.max(R * (CH + GY) + HEAD + PAD, tallest * f), pos = new Map<string, XY>();
    place(R, H, pos);
    const { w, h } = box(pos), s = Math.abs(Math.log(w / h / aspect)) + (w * h) / 4e8;
    if (s < bestScore) { bestScore = s; best = { R, H }; }
  }

  // barycentre sweeps: order cards in each column, and blocks in each macro column, by their neighbours' height
  const pos = new Map<string, XY>();
  for (let it = 0; it < 6; it++) {
    place(best.R, best.H, pos);
    const bc = (id: string) => { const ns = adj.get(id)!; return ns.length ? ns.reduce((s, m) => s + pos.get(m)!.y, 0) / ns.length : pos.get(id)!.y; };
    for (const b of blocks) for (const g of b.groups) { const v = new Map(g.map((id) => [id, bc(id)])); g.sort((p, q) => v.get(p)! - v.get(q)!); }
    const bv = new Map(blocks.map((b) => [b, b.members.reduce((s, id) => s + bc(id), 0) / b.members.length]));
    blocks.sort((p, q) => bv.get(p)! - bv.get(q)!);
  }
  place(best.R, best.H, pos);
  return pos;
}

/** Soft background regions: each zone's bounding box with padding and room for its label. */
export function regions(zones: Zone[], pos: Map<string, XY>) {
  const out: { id: string; name: string; x: number; y: number; w: number; h: number }[] = [];
  for (const z of zones) {
    const ps = z.members.map((m) => pos.get(m)).filter((p): p is XY => !!p);
    if (!ps.length) continue;
    const x0 = Math.min(...ps.map((p) => p.x)) - 16, y0 = Math.min(...ps.map((p) => p.y)) - 28;
    out.push({ id: z.id, name: z.name, x: x0, y: y0, w: Math.max(...ps.map((p) => p.x)) + CW + 16 - x0, h: Math.max(...ps.map((p) => p.y)) + CH + 12 - y0 });
  }
  return out;
}

/** The cubic curve of a bundle, from the source card's right edge to the target's left (or right, when the target is not further right). */
export function curve(sx: number, sy: number, tx: number, ty: number): number[] {
  if (tx >= sx + 24) { const d = Math.max(32, (tx - sx) / 2); return [sx, sy, sx + d, sy, tx - d, ty, tx, ty]; }
  const ex = tx + CW, m = Math.max(sx, ex) + 36 + Math.min(120, Math.abs(ty - sy) * 0.2);
  return [sx, sy, m, sy, m, ty, ex, ty];
}
export const at = (c: number[], t: number): XY => {
  const u = 1 - t, a = u * u * u, b = 3 * u * u * t, d = 3 * u * t * t, e = t * t * t;
  return { x: a * c[0] + b * c[2] + d * c[4] + e * c[6], y: a * c[1] + b * c[3] + d * c[5] + e * c[7] };
};
export const ends = (a: XY, b: XY) => curve(a.x + CW, a.y + CH / 2, b.x, b.y + CH / 2);
export const labelSize = (s: string) => ({ w: 14 + s.length * 6.4, h: 20 });

const TS = [0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74];
/** Where along its curve each bundle's label sits (t), or null when every spot would overlap a card or another label. */
export function placeLabels(edges: Edge[], pos: Map<string, XY>): Map<string, number | null> {
  const CELL = 160, grid = new Map<string, number[][]>();
  const cells = (x0: number, y0: number, x1: number, y1: number) => {
    const ks: string[] = [];
    for (let i = Math.floor(x0 / CELL); i <= Math.floor(x1 / CELL); i++) for (let j = Math.floor(y0 / CELL); j <= Math.floor(y1 / CELL); j++) ks.push(`${i},${j}`);
    return ks;
  };
  const put = (r: number[]) => { for (const k of cells(r[0], r[1], r[2], r[3])) { const l = grid.get(k); if (l) l.push(r); else grid.set(k, [r]); } };
  const free = (r: number[]) => cells(r[0], r[1], r[2], r[3]).every((k) => !(grid.get(k) ?? []).some((o) => r[0] < o[2] && r[2] > o[0] && r[1] < o[3] && r[3] > o[1]));
  for (const p of pos.values()) put([p.x - 4, p.y - 4, p.x + CW + 4, p.y + CH + 4]);
  const out = new Map<string, number | null>();
  for (const e of [...edges].sort((p, q) => q.wires.length - p.wires.length)) {
    const a = pos.get(e.a), b = pos.get(e.b);
    out.set(e.id, null);
    if (!a || !b) continue;
    const c = ends(a, b), { w, h } = labelSize(e.label);
    for (const t of TS) {
      const m = at(c, t), r = [m.x - w / 2 - 3, m.y - h / 2 - 3, m.x + w / 2 + 3, m.y + h / 2 + 3];
      if (free(r)) { put(r); out.set(e.id, t); break; }
    }
  }
  return out;
}
