import { useMemo } from "react";
import { useApp } from "../App";
import { href } from "../data";

/** Properties of the selection (a wire table row, a navigator item, a problem); its full page is one click away. */
export function Inspector() {
  const { ix, d, sel } = useApp();
  const body = useMemo(() => {
    if (!sel) return null;
    if (sel.type === "conductor") {
      const c = d.byId.get(sel.id);
      if (!c) return null;
      const iss = d.issuesByConductor.get(c.id) || [];
      return { title: `${c.label} ${c.name}`, rows: [["from", d.pinText(c.f)], ["to", d.pinText(c.t)], ["gauge", c.gauge], ["colour", c.colour],
        ["class", c.cls || c.kind], ["status", c.status], ["length m", c.length == null ? "" : String(c.length)], ["harness", c.harness],
        ["protection", c.protection], ["findings", iss.map((i) => `${i.severity} ${i.rule}`).join(", ")]] as [string, string][] };
    }
    if (sel.type === "component" || sel.type === "connector") {
      const c = d.comp.get(sel.id);
      if (!c) return null;
      const n = ix.conductors.filter((x) => x.f[0] === c.id || x.t[0] === c.id).length;
      const iss = ix.issues.filter((i) => i.objects.some((o) => o.endsWith(`:${c.id}`) || o.includes(`:${c.id}/`))).length;
      return { title: d.dn(c.id), rows: [["code", c.id], ["kind", c.kind], ["part", c.part], ["zone", c.zone], ["wires", String(n)],
        ["findings", String(iss)]] as [string, string][] };
    }
    return { title: `${sel.type} ${sel.id}`, rows: [] as [string, string][] };
  }, [sel, d, ix]);
  return (
    <aside className="inspector" aria-label="Inspector">
      <h2 className="panel-title">Inspector</h2>
      {body && sel ? <>
        <h3>{body.title}</h3>
        <dl className="props">{body.rows.filter(([, v]) => v).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
        <a href={href(sel.type, sel.id)}>Open the {sel.type} page</a>
      </> : <p className="muted">Select a wire, a component or a problem.</p>}
    </aside>
  );
}
