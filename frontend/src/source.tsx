// "+ Source": a small dialog that adds a battery, DC-DC converter or bench supply to a bus or component (POST /api/sources).
import { useState } from "react";
import { post } from "./api";
import type { Node, Workspace } from "./types";
import { Dialog } from "./ui";

type Kind = "battery" | "dcdc" | "bench";
const TYPES: [Kind, string][] = [["battery", "Battery"], ["dcdc", "DC-DC converter"], ["bench", "Bench supply"]];

/** The voltage class of the wires on a component, when they agree on one ("14 V" gives 14). */
export function classVoltage(ws: Workspace, id: string): number | null {
  const n = new Map<number, number>();
  for (const w of ws.conductors) {
    if (w.a !== id && w.b !== id) continue;
    const m = /^(\d+(?:\.\d+)?)\s*V$/i.exec(w.voltage.trim());
    if (m && Number(m[1]) > 0) n.set(Number(m[1]), (n.get(Number(m[1])) ?? 0) + 1);
  }
  return [...n].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
}

const num = (s: string) => (s.trim() === "" ? null : Number(s));
const valid = (s: string, strict = true) => { const v = num(s); return v === null || (strict ? v > 0 : v >= 0); };

export function SourceDialog({ at, volt, onClose, onSaved, onError }: {
  at: Node; volt: number | null; onClose: () => void; onSaved: (w: Workspace, what: string) => void; onError: (e: unknown, retry?: () => void) => void }) {
  const [type, setType] = useState<Kind>("battery"), [v, setV] = useState(volt === null ? "" : String(volt));
  const [r, setR] = useState(""), [lim, setLim] = useState(""), [cap, setCap] = useState(""), [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const bat = type === "battery";
  const ok = num(v) !== null && valid(v) && valid(r) && valid(lim) && valid(cap);
  const save = () => {
    setBusy(true);
    const body: Record<string, unknown> = { attach: at.id, type, nominal_V: num(v) };
    if (bat && num(r) !== null) body.r_int_ohm = num(r);
    if (!bat && num(lim) !== null) body.i_limit_A = num(lim);
    if (num(cap) !== null) body.capacity_Ah = num(cap);
    if (name.trim()) body.name = name.trim();
    post<Workspace>("/api/sources", body).then((w) => onSaved(w, "Source added"), (e) => { setBusy(false); onError(e, save); });
  };
  const submit = (e: React.FormEvent) => { e.preventDefault(); if (ok && !busy) save(); };
  return <Dialog title="Add a source" onClose={onClose} className="source-dialog" tour="source-dialog" focus="input"
    footer={<><span className="spacer" /><button type="button" className="btn" onClick={onClose}>Cancel</button>
      <button type="submit" form="source-form" className="btn btn-primary" disabled={!ok || busy} aria-busy={busy}>Add source</button></>}>
    <form id="source-form" onSubmit={submit}>
      <p className="card-kind"><span className="faint">Attached to</span><strong>{at.name || at.id}</strong></p>
      <div className="fields">
        <label className="field"><span>Type</span><select className="input" value={type} onChange={(e) => setType(e.target.value as Kind)}>
          {TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field"><span>Nominal voltage (V)</span><input className="input" inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} aria-invalid={!valid(v) || num(v) === null} /></label>
        {bat ? <label className="field"><span>Internal resistance (Ω)</span><input className="input" inputMode="decimal" placeholder="0.01" value={r} onChange={(e) => setR(e.target.value)} aria-invalid={!valid(r)} /></label>
          : <label className="field"><span>Current limit (A)</span><input className="input" inputMode="decimal" placeholder="no limit" value={lim} onChange={(e) => setLim(e.target.value)} aria-invalid={!valid(lim)} /></label>}
        <label className="field"><span>Capacity (Ah, optional)</span><input className="input" inputMode="decimal" value={cap} onChange={(e) => setCap(e.target.value)} aria-invalid={!valid(cap)} /></label>
        <label className="field wide"><span>Name (optional)</span><input className="input" placeholder={`${TYPES.find((t) => t[0] === type)![1]} ${v || ""}${v ? " V" : ""}`.trim()} value={name} onChange={(e) => setName(e.target.value)} /></label>
      </div>
      <p className="faint note">Your wire sheet is not changed. The source is kept in the project as a change set.</p>
    </form>
  </Dialog>;
}
