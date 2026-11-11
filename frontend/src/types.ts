// The server contract (docs/api.md), as TypeScript types.

export type Sev = "" | "error" | "warning" | "info";
export interface ProjectInfo { name: string; root: string; version: string; warnings: string[] }
export interface Recent { name: string; path: string; opened: string }
export interface Session { project: ProjectInfo | null; recent: Recent[]; tour_done: boolean; theme: "light" | "dark" }

export interface Node { id: string; name: string; kind: string; zone: string; subsystem: string; pins: number; rank: number; sev: Sev }
export interface Edge { id: string; a: string; b: string; wires: string[]; cls: string[]; label: string }
export interface Wire {
  id: string; label: string; name: string; from: string; to: string; a: string; b: string;
  gauge: string; voltage: string; current: number | null; cls: string; hex: string;
  length: number | null; harness: string; protection: string; status: string; notes: string; sev: Sev;
}
export interface Issue { k: number; rule: string; severity: "error" | "warning" | "info"; title: string; message: string; fix: string; objects: string[] }
export interface Zone { id: string; name: string; members: string[] }
export interface Source { id: string; name: string; attach: string; type: string; nominal_V: number; r_int_ohm: number | null; i_limit_A: number | null; capacity_Ah: number | null }
export interface Workspace {
  project: ProjectInfo; components: Node[]; edges: Edge[]; conductors: Wire[]; issues: Issue[];
  zones: Zone[]; positions: Record<string, [number, number]>; sources: Source[]; palette: Record<string, string>;
}
export interface OverlayItem { status: "ok" | "warn" | "error"; reason: string }
export interface SimGroup { title: string; objects: string[]; status: "ok" | "warn" | "error" }
export interface Overlay {
  ok: boolean; summary: { problems: number; trips: number; unpowered: number; text: string; groups: SimGroup[] };
  buses: { id: string; voltage_V: number; nominal_V: number | null; powered: boolean }[];
  breakers: { id: string; current_A: number; rating_A: number | null; loading: number | null; trips: boolean }[];
  items: Record<string, OverlayItem>; assumptions: string[];
}
export interface ExportResult { folder: string; files: string[] }

export interface Pin { pin: string; wire: string; wire_label: string; name: string; other: string; gauge: string }
export interface ComponentCard {
  id: string; name: string; kind: string; location: string; rating_A: number | null;
  connectors: { id: string; pins: Pin[] }[]; issues: Issue[]; sim?: OverlayItem;
}
export interface WireCard {
  id: string; label: string; name: string; from: string; to: string; gauge: string; voltage: string; current: number | null;
  length: number | null; colour: string; hex: string; harness: string; protection: string; status: string; notes: string;
  issues: Issue[]; sim?: OverlayItem;
}
export type CardTarget = { type: "component" | "wire"; id: string };
