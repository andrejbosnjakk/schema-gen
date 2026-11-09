// The Issues panel (left) and the Wires drawer (bottom).
import { useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Issue, Wire } from "./types";
import { Glyph } from "./ui";

const GROUPS: [Issue["severity"], string][] = [["error", "Errors"], ["warning", "Warnings"], ["info", "Notes"]];

export function Issues({ issues, loading, onPick, onClose }: { issues: Issue[] | null; loading: boolean; onPick: (i: Issue) => void; onClose: () => void }) {
  return (
    <aside className="issues anim-panel" data-tour="issues" aria-labelledby="issues-h">
      <header className="panel-head">
        <h2 id="issues-h">Issues {issues && <span className="count">{issues.length}</span>}</h2>
        <button className="icon-btn sm" onClick={onClose} aria-label="Hide issues" title="Hide issues"><Glyph name="left" /></button>
      </header>
      <div className="issues-body">
        {loading || !issues ? <SkeletonRows n={6} tall /> : issues.length === 0 ? <p className="empty">Nothing to report. Every rule passed.</p> :
          GROUPS.map(([sev, name]) => {
            const list = issues.filter((i) => i.severity === sev);
            if (!list.length) return null;
            return <section key={sev} className="issue-group" aria-label={`${name}: ${list.length}`}>
              <h3><span className={`dot ${sev}`} aria-hidden="true" />{name}<span className="count">{list.length}</span></h3>
              <ul>{list.map((i) => <li key={i.k}>
                <button className="issue" onClick={() => onPick(i)} disabled={!i.objects.length} title={i.objects.length ? "Show on the diagram" : undefined}>
                  <span className="issue-title">{i.title || i.message}</span>
                  {i.title && i.message && <span className="issue-msg">{i.message}</span>}
                </button></li>)}</ul>
            </section>;
          })}
      </div>
    </aside>);
}

export function SkeletonRows({ n, tall }: { n: number; tall?: boolean }) {
  return <div className="skel-rows" aria-hidden="true">{Array.from({ length: n }, (_, i) =>
    <div key={i} className={`skeleton${tall ? " tall" : ""}`} style={{ width: `${92 - (i % 3) * 14}%` }} />)}</div>;
}

const COLS = ["Label", "Name", "From", "To", "Gauge", "Voltage", "Current"];
const fmtA = (a: number | null) => (a === null || a === undefined ? "" : `${a} A`);

export function Wires({ wires, open, loading, sel, onToggle, onPick }: {
  wires: Wire[] | null; open: boolean; loading: boolean; sel: string | null; onToggle: () => void; onPick: (w: Wire) => void }) {
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const ws = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!wires || !ws.length) return wires ?? [];
    return wires.filter((w) => { const s = `${w.label} ${w.name} ${w.from} ${w.to} ${w.gauge} ${w.voltage}`.toLowerCase(); return ws.every((x) => s.includes(x)); });
  }, [wires, q]);
  const scroller = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({ count: rows.length, getScrollElement: () => scroller.current, estimateSize: () => 33, overscan: 12 });
  const count = wires ? (q ? `${rows.length.toLocaleString()} of ${wires.length.toLocaleString()}` : wires.length.toLocaleString()) : "";
  return (
    <section className={`wires${open ? " open anim-drawer" : ""}`} aria-label="Wires">
      <header className="drawer-head">
        <button className="drawer-handle" onClick={onToggle} aria-expanded={open} data-tour="wires">
          <Glyph name={open ? "down" : "up"} /><span className="drawer-title">Wires</span><span className="count">{count}</span>
        </button>
        {open && <label className="filter"><Glyph name="search" size={14} />
          <input type="search" placeholder="Filter wires" aria-label="Filter wires" value={q} onChange={(e) => setQ(e.target.value)} /></label>}
      </header>
      {open && <div className="table" role="table" aria-label="Wire list" aria-rowcount={rows.length + 1}>
        <div className="tr th" role="row">{COLS.map((c) => <span key={c} role="columnheader">{c}</span>)}</div>
        {loading || !wires ? <SkeletonRows n={5} /> : rows.length === 0 ? <p className="empty">{q ? "No wire matches the filter." : "This project has no wires yet."}</p> :
          <div className="tbody" ref={scroller} role="rowgroup">
            <div style={{ height: v.getTotalSize(), position: "relative" }}>
              {v.getVirtualItems().map((it) => {
                const w = rows[it.index];
                return <div key={w.id} ref={v.measureElement} data-index={it.index} data-id={w.id} role="row" tabIndex={0}
                  className={`tr${w.id === sel ? " sel" : ""}`} style={{ transform: `translateY(${it.start}px)` }} aria-rowindex={it.index + 2}
                  onClick={() => onPick(w)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(w); } }}>
                  <span role="cell" className="c-label">{w.sev && <span className={`dot ${w.sev}`} aria-label={w.sev} role="img" />}{w.label || w.id}</span>
                  <span role="cell" title={w.name}>{w.name}</span>
                  <span role="cell" title={w.from}>{w.from}</span>
                  <span role="cell" title={w.to}>{w.to}</span>
                  <span role="cell">{w.gauge}</span>
                  <span role="cell"><span className="swatch" style={{ "--c": w.hex } as React.CSSProperties} aria-hidden="true" />{w.voltage}</span>
                  <span role="cell" className="num">{fmtA(w.current)}</span>
                </div>;
              })}
            </div>
          </div>}
      </div>}
    </section>);
}
