// The simulation overlay's summary (top of the canvas) and what the diagram needs from the result.
import { useMemo } from "react";
import type { Overlay, SimGroup } from "./types";
import { Glyph } from "./ui";

/** What a diagram card shows: its status ring, a bus voltage badge, a breaker loading bar. */
export interface CardSim { status?: "warn" | "error"; volt?: { v: number; low: boolean }; load?: { f: number; text: string } }

const fmtV = (v: number) => `${(Math.round(v * 10) / 10).toFixed(1)} V`;

/** Per component id, per bundle-of-wires id (conductors with something to say): what the overlay draws. */
export function useSim(o: Overlay | null) {
  return useMemo(() => {
    const cards = new Map<string, CardSim>(), wires = new Map<string, "warn" | "error">();
    if (!o) return { cards, wires };
    const at = (id: string) => { let c = cards.get(id); if (!c) cards.set(id, c = {}); return c; };
    for (const [k, it] of Object.entries(o.items)) {
      const i = k.indexOf(":"), t = k.slice(0, i), id = k.slice(i + 1);
      if (it.status === "ok") continue;
      if (t === "component") at(id).status = it.status;
      else if (t === "conductor") wires.set(id, it.status);
    }
    for (const b of o.buses) at(b.id).volt = { v: b.voltage_V, low: !b.powered || (b.nominal_V !== null && b.voltage_V < 0.9 * b.nominal_V) };
    for (const b of o.breakers) if (b.loading !== null && b.rating_A) {
      const f = b.trips ? Math.max(b.loading, 1) : b.loading;
      at(b.id).load = { f, text: b.trips ? `Trips: ${b.current_A.toFixed(1)} A on a ${b.rating_A} A breaker` : `${Math.round(b.loading * 100)} % of ${b.rating_A} A (${b.current_A.toFixed(1)} A)` };
    }
    return { cards, wires };
  }, [o]);
}

export const voltText = fmtV;

/** The summary: a chip in the top bar next to Simulate (problem count, error dot, chevron, Clear); open, its list drops down over the canvas. */
export function SimSummary({ o, stale, open, onOpen, onGroup, onClear }: { o: Overlay; stale: boolean; open: boolean; onOpen: (v: boolean) => void; onGroup: (g: SimGroup) => void; onClear: () => void }) {
  const groups = o.summary.groups ?? [];
  const n = groups.length, chip = (o.ok ? "No problems" : n ? `${n} problem${n === 1 ? "" : "s"}` : "Problems found") + (stale ? " (out of date)" : "");
  return <section className={`sim-summary${stale ? " stale" : ""}`} aria-label="Simulation results" data-tour="sim-summary">
    <header>
      <button className="sim-toggle" aria-expanded={open} onClick={() => onOpen(!open)} title={open ? "Collapse the summary" : "Show the summary"}>
        <span className={`dot ${o.ok ? "" : "error"}`} aria-hidden="true" /><strong className="sim-chip">{chip}</strong><Glyph name={open ? "up" : "down"} size={14} />
      </button>
      <button className="btn btn-ghost btn-sm" onClick={onClear}><Glyph name="x" size={14} />Clear</button>
    </header>
    {open && <div className="sim-panel anim-slide">
      <p className="sim-text">{o.summary.text || (o.ok ? "No problems" : "Problems found")}</p>
      {stale && <p className="sim-stale" role="status">Results are out of date, simulate again</p>}
      {groups.length > 0 && <ul>{groups.map((g, i) => <li key={`${i}-${g.title}`}>
        <button className="sim-group" onClick={() => onGroup(g)} disabled={!g.objects.length}>
          <span className={`dot ${g.status === "error" ? "error" : g.status === "warn" ? "warning" : ""}`} aria-hidden="true" /><span>{g.title}</span></button></li>)}</ul>}
    </div>}
  </section>;
}
