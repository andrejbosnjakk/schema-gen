import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../App";
import { href } from "../data";

export function Search({ onClose }: { onClose: () => void }) {
  const { d } = useApp();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inp = useRef<HTMLInputElement>(null);
  useEffect(() => inp.current?.focus(), []);
  const res = useMemo(() => d.find(q, 40), [d, q]);
  const go = (k: number) => { const r = res[k]; if (r) { location.hash = href(r.type, r.id); onClose(); } };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search every object" onClick={(e) => e.stopPropagation()}>
        <input ref={inp} type="search" value={q} aria-label="Search wires, pins, components, connectors, harnesses, nets, parts"
               placeholder="Search wires, pins, components, connectors, harnesses, nets, parts…" aria-controls="search-results"
               aria-activedescendant={res[sel] ? `sr-${sel}` : undefined}
               onChange={(e) => { setQ(e.target.value); setSel(0); }}
               onKeyDown={(e) => {
                 if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, res.length - 1)); }
                 if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
                 if (e.key === "Enter") go(sel);
                 if (e.key === "Escape") onClose();
               }} />
        <ul id="search-results" role="listbox" aria-label="Results">
          {res.map((r, k) => (
            <li key={r.type + r.id} id={`sr-${k}`} role="option" aria-selected={k === sel} className={k === sel ? "sel" : ""}
                onMouseEnter={() => setSel(k)} onClick={() => go(k)}>
              <span className={`tag ${r.type}`}>{r.type}</span> <b>{r.title}</b> <span className="muted">{r.sub}</span>
            </li>))}
          {q && !res.length ? <li className="muted">no match</li> : null}
        </ul>
      </div>
    </div>
  );
}
