import { useMemo, useState } from "react";
import { useApp } from "../App";
import { href } from "../data";

const refLink = (o: string) => {
  const k = o.indexOf(":");
  const t = o.slice(0, k), id = o.slice(k + 1);
  const map: Record<string, string> = { conductor: "conductor", component: "component", connector: "connector", pin: "pin", net: "net", protective: "component" };
  if (t === "pin" && id.includes("//")) return <a key={o} href={href("connector", id.split("/")[0])}>{o}</a>; // harness pin: its connector
  return map[t] ? <a key={o} href={href(map[t], id)}>{o}</a> : <span key={o}>{o}</span>;
};

export function Issues() {
  const { ix } = useApp();
  const [sev, setSev] = useState<string>("all");
  const [rule, setRule] = useState<string>("all");
  const rules = useMemo(() => [...new Set(ix.issues.map((i) => i.rule))].sort(), [ix]);
  const shown = ix.issues.filter((i) => (sev === "all" || i.severity === sev) && (rule === "all" || i.rule === rule));
  const n = (s: string) => ix.issues.filter((i) => i.severity === s).length;
  return (
    <section className="issues-board">
      <h1>Issues <small>{ix.issues.length} findings, {ix.open_items.filter((o) => !/closed|done/i.test(o.status)).length} open items</small></h1>
      <div className="toolbar" role="group" aria-label="Filter findings">
        {["all", "error", "warning", "info"].map((s) => <button key={s} aria-pressed={sev === s} onClick={() => setSev(s)} className={`chip ${s}`}>
          {s}{s !== "all" ? ` ${n(s)}` : ""}</button>)}
        <label>Rule <select value={rule} onChange={(e) => setRule(e.target.value)} aria-label="Rule">
          <option value="all">all rules</option>{rules.map((r) => <option key={r}>{r}</option>)}</select></label>
      </div>
      <table className="grid" data-testid="issues-table">
        <thead><tr><th scope="col">severity</th><th scope="col">rule</th><th scope="col">finding</th><th scope="col">objects</th><th scope="col">fix</th></tr></thead>
        <tbody>{shown.slice(0, 1000).map((i) => (
          <tr key={i.k} className={i.severity}><td><span className={`badge ${i.severity}`}>{i.severity}</span></td><td>{i.rule}</td><td>{i.message}</td>
            <td className="refs">{i.objects.slice(0, 4).map(refLink)}</td><td>{i.fix}</td></tr>))}</tbody>
      </table>
      <h2>Open items</h2>
      <table className="grid"><thead><tr><th scope="col">id</th><th scope="col">item</th><th scope="col">status</th><th scope="col">owner</th><th scope="col">objects</th></tr></thead>
        <tbody>{ix.open_items.map((o) => <tr key={o.id}><td>{o.id}</td><td>{o.text}</td><td>{o.status}</td><td>{o.owner}</td>
          <td>{o.objects.map((x) => <a key={x} href={href("component", x)}>{x} </a>)}</td></tr>)}</tbody></table>
    </section>
  );
}
