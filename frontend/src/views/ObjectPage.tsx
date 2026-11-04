import { useEffect, useState } from "react";
import { useApp } from "../App";
import { api, href } from "../data";

interface Obj {
  type: string; id: string; title: string; props: Record<string, unknown>; extra?: Record<string, unknown>;
  links: { type: string; id: string; label: string }[]; sources: string[];
  issues: { rule: string; severity: string; message: string; fix: string }[];
  history: { commit: string; date: string; author: string; subject: string }[];
  origin?: { file: string; row: number } | null; conductors: number[];
  pins?: Record<string, unknown>[];
}

const fmt = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));
const TYPE_NAME: Record<string, string> = { conductor: "Wire", pin: "Pin", component: "Component", connector: "Harness connector",
  harness: "Harness", net: "Net", part: "Part" };

export function ObjectPage({ type, id }: { type: string; id: string }) {
  const { ix, highlight, net } = useApp();
  const [o, setO] = useState<Obj | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setO(null); setErr("");
    api<Obj>(`/api/object?type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`).then(setO).catch((e) => setErr(String(e)));
  }, [type, id, ix]);
  if (err) return <section><h1>{TYPE_NAME[type] || type} {id}</h1><p role="alert">{err}</p></section>;
  if (!o) return <section aria-busy="true"><p>Loading…</p></section>;
  const netId = o.type === "net" ? o.id : (o.links.find((l) => l.type === "net")?.id ?? (o.conductors.length ? ix.conductors[o.conductors[0]].net : ""));
  const groups: Record<string, typeof o.links> = {};
  for (const l of o.links) (groups[l.type] ||= []).push(l);
  return (
    <article className="object">
      <header>
        <p className="kind">{TYPE_NAME[o.type] || o.type}</p>
        <h1>{o.title}</h1>
        {netId ? <button onClick={() => highlight(netId)} aria-pressed={net === netId}>{net === netId ? "Clear net highlight" : "Highlight net"}</button> : null}
        {o.type === "conductor" ? <a className="btn" href={`#/table`}>Edit in the wire table</a> : null}
      </header>
      <div className="cols">
        <section aria-labelledby="props-h">
          <h2 id="props-h">Properties</h2>
          <dl className="props">
            {Object.entries(o.props).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{fmt(v)}</dd></div>)}
            {o.extra ? Object.entries(o.extra).map(([k, v]) => <div key={k}><dt>{k} <small>(extra)</small></dt><dd>{fmt(v)}</dd></div>) : null}
          </dl>
          {o.pins ? <><h2>Pins</h2><table className="grid small"><thead><tr><th>connector</th><th>pin</th><th>name</th><th>type</th><th>AWG</th><th>I max</th></tr></thead>
            <tbody>{o.pins.map((p, k) => <tr key={k}><td>{fmt(p.connector)}</td><td>{fmt(p.n)}</td><td>{fmt(p.name)}</td><td>{fmt(p.type)}</td>
              <td>{p.awg_min ? `${p.awg_min}–${p.awg_max}` : "—"}</td><td>{fmt(p.i_max)}</td></tr>)}</tbody></table></> : null}
        </section>
        <section aria-labelledby="links-h">
          <h2 id="links-h">Links</h2>
          {Object.entries(groups).map(([t, ls]) => (
            <div key={t}><h3>{TYPE_NAME[t] || t} <small>{ls.length}</small></h3>
              <ul className="links">{ls.slice(0, 200).map((l) => <li key={l.type + l.id + l.label}><a href={href(l.type, l.id)}>{l.label}</a></li>)}</ul></div>))}
          <h2>Sources</h2>
          {o.sources.length ? <ul>{o.sources.map((s) => <li key={s}>{s}</li>)}</ul> : <p className="muted">none recorded</p>}
          {o.origin ? <p className="muted">from {o.origin.file}, row {o.origin.row}</p> : null}
        </section>
        <section aria-labelledby="iss-h">
          <h2 id="iss-h">Issues</h2>
          {o.issues.length ? <ul className="issues">{o.issues.map((i, k) => <li key={k} className={i.severity}><b>{i.severity}</b> {i.rule}: {i.message}
            {i.fix ? <div className="fix">fix: {i.fix}</div> : null}</li>)}</ul> : <p className="muted">no findings</p>}
          <h2>History</h2>
          {o.history.length ? <ul className="history">{o.history.map((h) => <li key={h.commit}><code>{h.commit}</code> {h.date} {h.author}: {h.subject}</li>)}</ul>
            : <p className="muted">no commits mention it (or the project is not in git)</p>}
        </section>
      </div>
    </article>
  );
}
