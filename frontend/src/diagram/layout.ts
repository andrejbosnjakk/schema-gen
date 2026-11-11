// Where the cards go. Each zone is a block with its own power-flow columns (Node.rank, left to right, tall columns
// wrapped to a few rows). The blocks are packed (skyline, sources and protection first) into a rectangle whose shape is
// searched for the largest fit-to-screen zoom, so the whole system reads at a glance on a wide screen. Card order inside
// a column follows the barycentre of its neighbours (fewer crossings). Plus the edge routes and the label pass.
import type { Edge, Node, Zone } from "../types";

export const CW = 204, CH = 30;           // card size (fixed: the edge geometry depends on it)
const GX = 28, GY = 6;                    // gap between columns (the edge channel), between rows
export const HEAD = 28, PAD = 8, GB = 10; // zone label room, zone padding, gap between zone blocks
export type XY = { x: number; y: number };

interface Block { members: string[]; groups: string[][]; key: number; w: number; h: number; x: number; y: number; rows: number; R: number; local: [string, number, number][] }

/** Top-left position of every card, before any user-dragged position is applied. `view` is the canvas size in px (its aspect and size steer the packing). */
export function layout(nodes: Node[], edges: Edge[], zones: Zone[], view = { w: 1066, h: 520 }): Map<string, XY> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const ranks = [...new Set(nodes.map((n) => n.rank))].sort((a, b) => a - b);
  const seen = new Set<string>(), blocks: Block[] = [];
  const mk = (ids: string[]) => {
    const ms = ids.filter((id) => byId.has(id) && !seen.has(id));
    ms.forEach((id) => seen.add(id));
    if (!ms.length) return;
    const groups = ranks.map((r) => ms.filter((id) => byId.get(id)!.rank === r).sort((a, b) => byId.get(a)!.name.localeCompare(byId.get(b)!.name)));
    blocks.push({ members: ms, groups, key: Math.min(...ms.map((id) => byId.get(id)!.rank)), w: 0, h: 0, x: 0, y: 0, rows: 0, R: 1, local: [] });
  };
  for (const z of zones) mk(z.members);
  mk(nodes.map((n) => n.id));  // components in no zone
  const adj = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) if (byId.has(e.a) && byId.has(e.b) && e.a !== e.b) { adj.get(e.a)!.push(e.b); adj.get(e.b)!.push(e.a); }

  /** Size every block for at most b.R rows per column: a rank is a column (split when taller than R); a short rank shares the column before it. */
  const shape = () => {
    for (const b of blocks) {
      const R = b.R;
      const cols: string[][] = [];
      for (const g of b.groups) {
        if (!g.length) continue;
        const k = Math.ceil(g.length / R), per = Math.ceil(g.length / k);
        for (let i = 0; i < k; i++) {
          const chunk = g.slice(i * per, (i + 1) * per), last = cols[cols.length - 1];
          if (last && last.length + chunk.length <= R) last.push(...chunk); else cols.push(chunk);
        }
      }
      b.local = cols.flatMap((c, x) => c.map((id, r): [string, number, number] => [id, x * (CW + GX), r]));
      b.rows = Math.max(...cols.map((c) => c.length));
      b.w = cols.length * CW + (cols.length - 1) * GX + 2 * PAD; b.h = b.rows * (CH + GY) - GY + HEAD + PAD;
    }
  };
  /** Skyline-style packing into a strip of width W: each block goes to the lowest, then leftmost, free spot. Returns the used box. */
  const pack = (W: number, sort = 0) => {
    const placed: Block[] = [];
    let bw = 0, bh = 0;
    for (const b of [...blocks].sort((p, q) => (sort > 2 ? 0 : p.key - q.key) || [q.h - p.h, q.w - p.w, q.w * q.h - p.w * p.h, q.h - p.h, q.w * q.h - p.w * p.h][sort])) {
      const xs = [0, ...placed.map((p) => p.x + p.w + GB)], ys = [0, ...placed.map((p) => p.y + p.h + GB)];
      let best: XY | null = null;
      for (const y of ys) for (const x of xs) {
        if (x + b.w > W && x > 0) continue;
        if (best && (y > best.y || (y === best.y && x >= best.x))) continue;
        if (placed.some((p) => x < p.x + p.w + GB && x + b.w + GB > p.x && y < p.y + p.h + GB && y + b.h + GB > p.y)) continue;
        best = { x, y };
      }
      b.x = best!.x; b.y = best!.y; placed.push(b);
      bw = Math.max(bw, b.x + b.w); bh = Math.max(bh, b.y + b.h);
    }
    return { w: bw, h: bh };
  };
  const zoomOf = (w: number, h: number) => Math.min((view.w - 76) / w, (view.h - 24) / h);

  // the row limit (first one for all blocks, then per block) and strip width whose packed box has the largest fit zoom (then the smaller area)
  const maxG = Math.max(1, ...blocks.flatMap((b) => b.groups.map((g) => g.length)));
  const Rs = [...new Set(Array.from({ length: Math.min(maxG, 24) - 2 }, (_, i) => i + 3).concat([32, 48, 80].filter((r) => r < maxG), maxG))];
  let best = { W: Infinity, sort: 0 }, bestScore = -Infinity;
  const widths = (steps: number) => { shape(); const wmin = Math.max(...blocks.map((b) => b.w)), wsum = blocks.reduce((s, b) => s + b.w + GB, 0); return Array.from({ length: steps + 1 }, (_, i) => Math.round(wmin + (wsum - wmin) * (i / steps) ** 1.5)); };
  const tryWidths = (steps: number) => {  // searches W and the packing order for the current block shapes; true when it found something better
    let up = false;
    for (const W of widths(steps)) for (let sort = 0; sort < 5; sort++) {
      const { w, h } = pack(W, sort), s = zoomOf(w, h) - (w * h) / 1e12;
      if (s > bestScore + 1e-9) { bestScore = s; best = { W, sort }; up = true; }
    }
    return up;
  };
  let bestR = maxG;
  for (const R of Rs) { const before = bestScore; blocks.forEach((b) => (b.R = R)); if (tryWidths(24) && bestScore > before) bestR = R; }
  blocks.forEach((b) => (b.R = bestR));
  for (let pass = 0; pass < 3; pass++) {
    let moved = false;
    for (const b of blocks) for (const R of Rs) {
      if (R === b.R) continue;
      const old = b.R; b.R = R; shape();
      const { w, h } = pack(best.W, best.sort), s = zoomOf(w, h) - (w * h) / 1e12;
      if (s > bestScore + 1e-9) { bestScore = s; moved = true; } else b.R = old;
    }
    shape(); if (tryWidths(24)) moved = true;
    if (!moved) break;
  }
  shape(); pack(best.W, best.sort);

  // barycentre sweeps: order cards in each column by their neighbours' height
  const pos = new Map<string, XY>();
  const set = () => { for (const b of blocks) for (const [id, lx, r] of b.local) pos.set(id, { x: b.x + PAD + lx, y: b.y + HEAD + r * (CH + GY) }); };
  for (let it = 0; it < 5; it++) {
    set();
    const bc = (id: string) => { const ns = adj.get(id)!; return ns.length ? ns.reduce((s, m) => s + pos.get(m)!.y, 0) / ns.length : pos.get(id)!.y; };
    for (const b of blocks) for (const g of b.groups) { const v = new Map(g.map((id) => [id, bc(id)])); g.sort((p, q) => v.get(p)! - v.get(q)!); }
    shape(); pack(best.W, best.sort);  // regroup the sorted columns, same packing
  }
  set();
  return pos;
}

/** Soft background regions: each zone's bounding box with padding and room for its label. */
export function regions(zones: Zone[], pos: Map<string, XY>) {
  const out: { id: string; name: string; x: number; y: number; w: number; h: number }[] = [];
  for (const z of zones) {
    const ps = z.members.map((m) => pos.get(m)).filter((p): p is XY => !!p);
    if (!ps.length) continue;
    const x0 = Math.min(...ps.map((p) => p.x)) - PAD, y0 = Math.min(...ps.map((p) => p.y)) - HEAD;
    out.push({ id: z.id, name: z.name, x: x0, y: y0, w: Math.max(...ps.map((p) => p.x)) + CW + PAD - x0, h: Math.max(...ps.map((p) => p.y)) + CH + PAD - y0 });
  }
  return out;
}

/** The orthogonal route of a bundle: out of the source's right edge, one vertical run in the channel before the target, into its left edge
 *  (or, when the target is not further right, round the right side and into the target's right edge). Points, corners rounded by `rounded`. */
export type Pts = [number, number][];
export function route(sx: number, sy: number, tx: number, ty: number): Pts {
  if (tx >= sx + 24) { const m = tx - 22; return sy === ty ? [[sx, sy], [tx, ty]] : [[sx, sy], [m, sy], [m, ty], [tx, ty]]; }
  const ex = tx + CW, m = Math.max(sx, ex) + 22;
  return [[sx, sy], [m, sy], [m, ty], [ex, ty]];
}
/** SVG path through the points with corners rounded to radius r. */
export function rounded(p: Pts, r = 8): string {
  let d = `M${p[0][0]},${p[0][1]}`;
  for (let i = 1; i < p.length - 1; i++) {
    const [x0, y0] = p[i - 1], [x1, y1] = p[i], [x2, y2] = p[i + 1];
    const a = Math.hypot(x1 - x0, y1 - y0), b = Math.hypot(x2 - x1, y2 - y1), k = Math.min(r, a / 2, b / 2);
    d += ` L${x1 - ((x1 - x0) / a) * k},${y1 - ((y1 - y0) / a) * k} Q${x1},${y1} ${x1 + ((x2 - x1) / b) * k},${y1 + ((y2 - y1) / b) * k}`;
  }
  return d + ` L${p[p.length - 1][0]},${p[p.length - 1][1]}`;
}
/** The point at fraction t of the route's length. */
export const at = (p: Pts, t: number): XY => {
  const L = p.slice(1).map((q, i) => Math.hypot(q[0] - p[i][0], q[1] - p[i][1]));
  let d = t * L.reduce((s, v) => s + v, 0);
  for (let i = 0; i < L.length; i++) {
    if (d <= L[i] || i === L.length - 1) { const f = L[i] ? Math.min(1, d / L[i]) : 0; return { x: p[i][0] + (p[i + 1][0] - p[i][0]) * f, y: p[i][1] + (p[i + 1][1] - p[i][1]) * f }; }
    d -= L[i];
  }
  return { x: p[0][0], y: p[0][1] };
};
export const ends = (a: XY, b: XY) => route(a.x + CW, a.y + CH / 2, b.x, b.y + CH / 2);
export const labelSize = (s: string) => ({ w: 14 + s.length * 6.4, h: 20 });

const TS = [0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74, 0.18, 0.82];
/** Where along its route each bundle's label sits (t), or null when every spot would overlap a card or another label. */
export function placeLabels(edges: Edge[], pos: Map<string, XY>, zones: { x: number; y: number; w: number }[] = []): Map<string, number | null> {
  const CELL = 160, grid = new Map<string, number[][]>();
  const cells = (x0: number, y0: number, x1: number, y1: number) => {
    const ks: string[] = [];
    for (let i = Math.floor(x0 / CELL); i <= Math.floor(x1 / CELL); i++) for (let j = Math.floor(y0 / CELL); j <= Math.floor(y1 / CELL); j++) ks.push(`${i},${j}`);
    return ks;
  };
  const put = (r: number[]) => { for (const k of cells(r[0], r[1], r[2], r[3])) { const l = grid.get(k); if (l) l.push(r); else grid.set(k, [r]); } };
  const free = (r: number[]) => cells(r[0], r[1], r[2], r[3]).every((k) => !(grid.get(k) ?? []).some((o) => r[0] < o[2] && r[2] > o[0] && r[1] < o[3] && r[3] > o[1]));
  for (const p of pos.values()) put([p.x - 4, p.y - 4, p.x + CW + 4, p.y + CH + 4]);
  for (const z of zones) put([z.x, z.y, z.x + z.w, z.y + HEAD - 4]);  // zone names stay readable
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
