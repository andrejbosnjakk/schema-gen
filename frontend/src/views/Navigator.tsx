import { useMemo, useState } from "react";
import { Icon, IconName } from "@blueprintjs/core";
import { useApp } from "../App";

const GROUPS: [string, string, IconName][] = [["harness", "Harness connectors", "inheritance"], ["device", "Devices", "box"],
  ["breaker", "Breakers", "flash"], ["fuse", "Fuses", "flash"], ["relay", "Relays", "exchange"], ["switch", "Switches", "segmented-control"],
  ["bus", "Buses", "column-layout"], ["splice", "Splices", "git-merge"]];
const MAX = 300;  // items listed per open group; the filter narrows the rest

/** The project tree: components by kind (a filter, groups closed until opened); a click selects for the inspector. */
export function Navigator() {
  const { ix, sel, select } = useApp();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const groups = useMemo(() => {
    const t = q.trim().toLowerCase();
    const by = new Map<string, typeof ix.components>();
    for (const c of ix.components) {
      if (t && !`${c.id} ${c.name}`.toLowerCase().includes(t)) continue;
      const k = GROUPS.some((g) => g[0] === c.kind) ? c.kind : "device";
      const l = by.get(k); if (l) l.push(c); else by.set(k, [c]);
    }
    return GROUPS.filter(([k]) => by.has(k)).map(([k, title, icon]) => ({ k, title, icon, items: by.get(k)! }));
  }, [ix, q]);
  const flip = (k: string) => setOpen((o) => { const n = new Set(o); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  return (
    <aside className="navigator" aria-label="Navigator">
      <h2 className="panel-title">Project</h2>
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter components" aria-label="Filter components" />
      <ul className="navtree">
        {groups.map((g) => {
          const isOpen = open.has(g.k) || !!q.trim();
          return (
            <li key={g.k}>
              <button className="group" aria-expanded={isOpen} onClick={() => flip(g.k)}>
                <Icon icon={isOpen ? "caret-down" : "caret-right"} size={12} /> <Icon icon={g.icon} size={14} /> {g.title} <span className="muted">{g.items.length}</span>
              </button>
              {isOpen ? <ul>
                {g.items.slice(0, MAX).map((c) => (
                  <li key={c.id}>
                    <button className="item" aria-current={sel?.id === c.id ? "true" : undefined} title={`${c.name} (${c.id})`}
                            onClick={() => select({ type: c.kind === "harness" ? "connector" : "component", id: c.id })}>
                      {c.name || c.id} <span className="muted">{c.name && !c.name.includes(c.id) ? c.id : ""}</span>
                    </button>
                  </li>))}
                {g.items.length > MAX ? <li className="muted more">{g.items.length - MAX} more: filter to narrow</li> : null}
              </ul> : null}
            </li>);
        })}
      </ul>
    </aside>
  );
}
