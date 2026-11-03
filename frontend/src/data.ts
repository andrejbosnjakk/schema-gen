// Data from the local server, and what the UI derives from it (pins, search entries, net lookups).

export type End = [string, string, string, string]; // component id, connector, pin, side
export interface Conductor {
  i: number; id: string; label: string; name: string; f: End; t: End; func: string; bus: string; cls: string; kind: string;
  gauge: string; colour: string; hex: string; length: number | null; current: number | null; status: string; harness: string;
  protection: string; zone: string; net: string; sev: string;
}
export interface Component { id: string; name: string; kind: string; part: string; zone: string }
export interface Issue { k: number; rule: string; severity: "error" | "warning" | "info"; message: string; objects: string[]; fix: string }
export interface Net { id: string; name: string; kind: string; c: number[] }
export interface Index {
  project: { root: string; name: string; version: string; warnings: string[]; scenarios: string[];
             changes: { id: string; title: string; created: string; ops: number }[] };
  conductors: Conductor[]; components: Component[]; connectors: { id: string; name: string; halves: [string, string, boolean][]; pins: number | null }[];
  harnesses: { id: string; n: number }[]; nets: Net[]; issues: Issue[];
  open_items: { id: string; text: string; status: string; owner: string; objects: string[] }[];
  protective: { id: string; rating_a: number | null; panel: string }[];
  lists: Record<string, string[]>; palette: Record<string, string>;
}

export type ObjType = "conductor" | "pin" | "component" | "connector" | "harness" | "net" | "part";
export interface SearchEntry { type: ObjType; id: string; title: string; sub: string; key: string }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { "content-type": "application/json" }, ...init });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const j = await r.json(); msg = j.detail || msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const pinId = (e: End) => `${e[0]}/${e[1]}/${e[2]}`;

const TYPE_ORDER: Record<string, number> = { component: 0, connector: 1, harness: 2, conductor: 3, net: 4, part: 5, pin: 6 };

export class Derived {
  byId = new Map<string, Conductor>();
  netById = new Map<string, Net>();
  comp = new Map<string, Component>();
  pins = new Map<string, number[]>(); // pin id -> conductor indices
  issuesByConductor = new Map<string, Issue[]>();
  search: SearchEntry[] = [];

  constructor(public ix: Index) {
    for (const c of ix.conductors) {
      this.byId.set(c.id, c);
      for (const e of [c.f, c.t]) {
        const p = pinId(e);
        const l = this.pins.get(p); if (l) l.push(c.i); else this.pins.set(p, [c.i]);
      }
    }
    for (const n of ix.nets) this.netById.set(n.id, n);
    for (const c of ix.components) this.comp.set(c.id, c);
    for (const i of ix.issues) for (const o of i.objects) {
      if (!o.startsWith("conductor:")) continue;
      const k = o.slice(10); const l = this.issuesByConductor.get(k); if (l) l.push(i); else this.issuesByConductor.set(k, [i]);
    }
    const s: SearchEntry[] = [];
    const add = (type: ObjType, id: string, title: string, sub: string) => s.push({ type, id, title, sub, key: `${title} ${id} ${sub}`.toLowerCase() });
    for (const c of ix.conductors) add("conductor", c.id, `${c.label} ${c.name}`, `wire ${c.id} · ${pinId(c.f)} → ${pinId(c.t)}`);
    for (const c of ix.components) add(c.kind === "harness" ? "connector" : "component", c.id, `${c.id} ${c.name}`, c.kind);
    for (const h of ix.harnesses) add("harness", h.id, `harness ${h.id}`, `${h.n} wires`);
    for (const n of ix.nets) add("net", n.id, `net ${n.name}`, `${n.kind} · ${n.c.length} wires`);
    for (const p of this.pins.keys()) add("pin", p, `pin ${p.replace(/\//g, " ").trim()}`, `${this.pins.get(p)!.length} wire(s)`);
    for (const p of new Set(ix.components.map((c) => c.part).filter(Boolean))) add("part", p, `part ${p}`, "part library");
    this.search = s;
  }

  find(q: string, limit = 50): SearchEntry[] {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    const words = t.split(/\s+/);
    const hits: [number, SearchEntry][] = [];
    for (const e of this.search) {
      if (!words.every((w) => e.key.includes(w))) continue;
      const title = e.title.toLowerCase(), id = e.id.toLowerCase();
      // exact id, then the phrase at the start of the title, then anywhere in the title; objects before pins
      const score = (id === t ? 0 : title.startsWith(t) ? 10 : title.includes(t) ? 20 : 30) + (TYPE_ORDER[e.type] ?? 9);
      hits.push([score, e]);
      if (hits.length > 5000) break;
    }
    return hits.sort((a, b) => a[0] - b[0]).slice(0, limit).map((h) => h[1]);
  }
}

export const href = (type: string, id: string) => `#/object/${type}/${encodeURIComponent(id)}`;
