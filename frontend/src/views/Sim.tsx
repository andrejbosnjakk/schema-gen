import { useState } from "react";
import { useApp } from "../App";
import { api, href } from "../data";

interface Op {
  scenario: string; ok: boolean; converged: boolean; message: string; iterations: number; residual: number; seconds: number;
  expectations: { kind: string; ok: boolean; detail: string }[];
  tree: { id: string; voltage_V: number; feeds: { id: string; current_A: number; rating_A: number | null; loading: number | null; trips: boolean;
    loads: { id: string; voltage_V: number; powered: boolean; v_min: number }[] }[] }[];
  conductors: { id: string; label: string; current_A: number; loading: number | null }[];
  loads: { component: string; voltage_V: number; powered: boolean; off: boolean; v_min: number }[];
  assumptions: { what: string; provenance: string; note: string }[];
}
interface Sweep { rows: Record<string, unknown>[]; seconds: number }

const Bar = ({ x, label }: { x: number | null; label: string }) => (
  <span className="bar" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(100 * (x || 0))} aria-label={label}>
    <span style={{ width: `${Math.min(100, 100 * (x || 0))}%` }} className={(x || 0) > 1 ? "over" : (x || 0) > 0.8 ? "warn" : ""} />
  </span>);

export function Sim() {
  const { ix, toast } = useApp();
  const [sc, setSc] = useState(ix.project.scenarios[0] || "");
  const [op, setOp] = useState<Op | null>(null);
  const [sw, setSw] = useState<Sweep | null>(null);
  const [busy, setBusy] = useState("");
  const run = async () => {
    setBusy("run");
    try { setOp(await api<Op>("/api/sim/run", { method: "POST", body: JSON.stringify(sc ? { scenario: sc } : {}) })); }
    catch (e) { toast(`simulation failed: ${e}`); } finally { setBusy(""); }
  };
  const faults = async () => {
    setBusy("faults");
    try { setSw(await api<Sweep>("/api/sim/faults", { method: "POST", body: JSON.stringify(sc ? { scenario: sc } : {}) })); }
    catch (e) { toast(`fault sweep failed: ${e}`); } finally { setBusy(""); }
  };
  const failing = op ? op.loads.filter((l) => !l.powered && !l.off) : [];
  return (
    <section className="sim">
      <div className="toolbar"><h1>Simulation</h1>
        <label>Scenario <select value={sc} onChange={(e) => setSc(e.target.value)} aria-label="Scenario">
          {ix.project.scenarios.map((s) => <option key={s}>{s}</option>)}{!ix.project.scenarios.length ? <option value="">default</option> : null}</select></label>
        <button className="primary" onClick={run} disabled={!!busy}>{busy === "run" ? "Running…" : "Run scenario"}</button>
        <button onClick={faults} disabled={!!busy}>{busy === "faults" ? "Sweeping…" : "Fault sweep"}</button>
      </div>
      {op ? <>
        <p data-testid="sim-status" className={op.ok ? "pass" : "fail"}><b>{op.ok ? "PASS" : "FAIL"}</b> {op.scenario}: {op.converged ? "converged" : `not converged: ${op.message}`} in {op.iterations} iterations,
          KCL residual {op.residual.toExponential(1)} A, {(op.seconds * 1000).toFixed(0)} ms</p>
        <div className="cols">
          <section><h2>Expectations</h2><ul className="exp">{op.expectations.map((e, k) => <li key={k} className={e.ok ? "ok" : "bad"}>{e.ok ? "✓" : "✗"} {e.detail}</li>)}
            {!op.expectations.length ? <li className="muted">none</li> : null}</ul>
            <h2>Loads below their minimum voltage</h2><ul>{failing.map((l) => <li key={l.component}><a href={href("component", l.component)}>{l.component}</a>
              {" "}{l.voltage_V.toFixed(2)} V (min {l.v_min} V)</li>)}{!failing.length ? <li className="muted">none</li> : null}</ul>
            <h2>Most loaded wires</h2><table className="grid small"><tbody>{op.conductors.slice(0, 15).map((c) => <tr key={c.id}>
              <td><a href={href("conductor", c.id)}>{c.label}</a></td><td>{c.current_A.toFixed(2)} A</td><td><Bar x={c.loading} label={`${c.label} loading`} /></td></tr>)}</tbody></table>
          </section>
          <section><h2>Bus voltages and breaker loading</h2>
            <ul className="tree">{op.tree.map((b) => <li key={b.id}><b><a href={href("component", b.id)}>{b.id}</a></b> {b.voltage_V.toFixed(3)} V
              <ul>{b.feeds.map((f) => <li key={f.id}><a href={href("component", f.id)}>{f.id}</a> {f.current_A.toFixed(2)} A / {f.rating_A ?? "?"} A <Bar x={f.loading} label={`${f.id} loading`} />
                {f.trips ? <span className="badge error">trips</span> : null}
                <span className="muted"> {f.loads.map((l) => `${l.id} ${l.voltage_V.toFixed(2)} V`).join(", ")}</span></li>)}</ul></li>)}</ul>
            <h2>Assumptions</h2><ul className="small">{op.assumptions.map((a, k) => <li key={k}><b>{a.what}</b> ({a.provenance}): {a.note}</li>)}</ul>
          </section>
        </div></> : <p className="muted">Pick a scenario and run it. Results list every assumption they rest on.</p>}
      {sw ? <section><h2>Fault sweep <small>{sw.rows.length} nodes, {sw.seconds.toFixed(1)} s</small></h2>
        <table className="grid small" data-testid="sweep"><thead><tr><th>node</th><th>fault A</th><th>trips first</th><th>trip s</th><th>selective</th><th>wire survives</th><th>interrupt ok</th></tr></thead>
          <tbody>{sw.rows.slice(0, 500).map((r, k) => <tr key={k} className={!r.first_trip || r.selective === false || r.wire_survives === false ? "warning" : ""}>
            <td>{String(r.node)}</td><td>{Number(r.fault_current_A).toFixed(0)}</td><td>{String(r.first_trip || "none")}</td>
            <td>{r.trip_s == null ? "" : Number(r.trip_s).toFixed(3)}</td><td>{r.selective ? "yes" : "NO"}</td><td>{String(r.wire_survives ?? "")} {String(r.worst_wire ?? "")}</td>
            <td>{r.within_interrupt ? "yes" : "NO"}</td></tr>)}</tbody></table></section> : null}
    </section>
  );
}
