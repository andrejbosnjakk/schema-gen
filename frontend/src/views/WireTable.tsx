import { useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useApp } from "../App";
import { api, Conductor, href, Index, pinId } from "../data";

type Edit = Record<string, Record<string, string>>; // conductor id -> field -> new value
const FIELD: Record<string, keyof Conductor> = { name: "name", awg: "gauge", cls: "cls", st: "status", length: "length" };
const COLS = ["name", "from", "to", "gauge", "colour", "class", "status", "length m", "findings"];
const KEY = "schemagen.wiretable.hidden";

function loadHidden(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(KEY) || "[]") as string[]); } catch { return new Set(); }
}

export function WireTable() {
  const { ix, d, net, highlight, setIndex, toast, sel: selected, select } = useApp();
  const cur = selected?.type === "conductor" ? selected.id : "";
  const [q, setQ] = useState("");
  const [edits, setEdits] = useState<Edit>({});
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(loadHidden);
  const show = (col: string) => !hidden.has(col);
  const toggle = (col: string) => setHidden((h) => {
    const n = new Set(h); if (n.has(col)) n.delete(col); else n.add(col);
    try { localStorage.setItem(KEY, JSON.stringify([...n])); } catch { /* storage blocked: the choice lasts for this page */ }
    return n;
  });
  const parent = useRef<HTMLDivElement>(null);
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return ix.conductors;
    return ix.conductors.filter((c) => `${c.label} ${c.id} ${c.name} ${pinId(c.f)} ${pinId(c.t)} ${d.pinText(c.f)} ${d.pinText(c.t)} ${c.gauge} ${c.kind} ${c.status}`
      .toLowerCase().includes(t));
  }, [ix, d, q]);
  const v = useVirtualizer({ count: rows.length, getScrollElement: () => parent.current, estimateSize: () => 32, overscan: 12 });
  const netSet = useMemo(() => new Set(net ? d.netById.get(net)?.c ?? [] : []), [net, d]);
  const nEdits = Object.values(edits).reduce((a, e) => a + Object.keys(e).length, 0);

  const val = (c: Conductor, f: string) => edits[c.id]?.[f] ?? String(c[FIELD[f]] ?? "");
  const set = (c: Conductor, f: string, value: string) => setEdits((e) => {
    const cur = { ...(e[c.id] || {}) };
    if (value === String(c[FIELD[f]] ?? "")) delete cur[f]; else cur[f] = value;
    const out = { ...e, [c.id]: cur };
    if (!Object.keys(cur).length) delete out[c.id];
    return out;
  });
  const save = async () => {
    setBusy(true);
    try {
      const list = Object.entries(edits).flatMap(([id, fs]) => Object.entries(fs).map(([field, value]) => ({ id, field, value })));
      const r = await api<{ changeset: { id: string }; index: Index }>("/api/edit", { method: "POST", body: JSON.stringify({ edits: list }) });
      setEdits({}); setIndex(r.index); toast(`saved ${list.length} change(s) as a change set in changes/`);
    } catch (e) { toast(`save failed: ${e}`); } finally { setBusy(false); }
  };
  const undo = async () => {
    setBusy(true);
    try {
      const r = await api<{ removed: string | null; index: Index }>("/api/undo", { method: "POST" });
      setIndex(r.index); toast(r.removed ? `undone: ${r.removed}` : "nothing to undo");
    } catch (e) { toast(`undo failed: ${e}`); } finally { setBusy(false); }
  };
  const items = v.getVirtualItems();
  const top = items.length ? items[0].start : 0;
  const bottom = items.length ? v.getTotalSize() - items[items.length - 1].end : 0;
  const pinCell = (c: Conductor, e: Conductor["f"]) => (
    <td className="pin">
      <button className="link" title={`${d.pinText(e)} (${pinId(e)}): highlight this net`} onClick={() => highlight(c.net)} data-pin={pinId(e)}>{d.pinText(e)}</button>
      {e[3] ? <span className="side">{e[3]}</span> : null}
    </td>);
  const text = (c: Conductor, f: string) => <span className={edits[c.id]?.[f] !== undefined ? "dirty" : ""}>{val(c, f)}</span>;
  const sel = (c: Conductor, f: string, list: string[], label: string) => c.id !== cur ? text(c, f) : (
    <select aria-label={`${label} of ${c.label}`} value={val(c, f)} onChange={(ev) => set(c, f, ev.target.value)} className={edits[c.id]?.[f] !== undefined ? "dirty" : ""}>
      {[...new Set(["", val(c, f), ...list])].map((x) => <option key={x} value={x}>{x || "—"}</option>)}
    </select>);
  return (
    <section className="wiretable">
      <div className="toolbar">
        <h1>Wires <small>{rows.length} of {ix.conductors.length}</small></h1>
        <label>Filter <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="label, device, pin, gauge…" aria-label="Filter wires" /></label>
        <button onClick={save} disabled={!nEdits || busy} className="primary">Save {nEdits ? `(${nEdits})` : ""}</button>
        <button onClick={() => setEdits({})} disabled={!nEdits || busy}>Discard</button>
        <button onClick={undo} disabled={busy || !ix.project.changes.length} title="remove the last change set">Undo last change set</button>
        <details className="columns"><summary>Columns</summary>
          <fieldset><legend>Show columns</legend>
            {COLS.map((col) => <label key={col}><input type="checkbox" checked={show(col)} onChange={() => toggle(col)} /> {col}</label>)}
          </fieldset></details>
      </div>
      <div className="scroll" ref={parent} data-testid="wire-scroll">
        <table className="grid">
          <thead><tr><th scope="col">label</th>{COLS.filter(show).map((col) => <th scope="col" key={col}>{col}</th>)}</tr></thead>
          <tbody>
            {top > 0 ? <tr style={{ height: top }} aria-hidden="true"><td colSpan={11} /></tr> : null}
            {items.map((it) => {
              const c = rows[it.index];
              const iss = d.issuesByConductor.get(c.id) || [];
              return (
                <tr key={c.id} className={[netSet.has(c.i) ? "hl" : "", c.id === cur ? "selected" : ""].join(" ")} data-id={c.id} style={{ height: 32 }}
                    aria-selected={c.id === cur} onClick={(e) => { if (!(e.target as HTMLElement).closest("a,button,input,select")) select({ type: "conductor", id: c.id }); }}>
                  <th scope="row"><a href={href("conductor", c.id)}>{c.label}</a>
                    {c.id !== cur ? <button className="edit" aria-label={`edit ${c.label}`} title="edit this row (or click the row)"
                                            onClick={() => select({ type: "conductor", id: c.id })}>✎</button> : null}</th>
                  {show("name") ? <td title={val(c, "name")}>{c.id !== cur ? text(c, "name") : <input aria-label={`name of ${c.label}`} value={val(c, "name")}
                             onChange={(e) => set(c, "name", e.target.value)} className={edits[c.id]?.name !== undefined ? "dirty" : ""} />}</td> : null}
                  {show("from") ? pinCell(c, c.f) : null}{show("to") ? pinCell(c, c.t) : null}
                  {show("gauge") ? <td>{sel(c, "awg", ix.lists.gauge, "gauge")}</td> : null}
                  {show("colour") ? <td><span className="swatch" style={{ background: c.hex }} aria-hidden="true" /> {c.colour}</td> : null}
                  {show("class") ? <td>{sel(c, "cls", ix.lists["function class"], "function class")}<span className="muted"> {c.cls ? "" : c.kind}</span></td> : null}
                  {show("status") ? <td>{sel(c, "st", ix.lists.status, "status")}</td> : null}
                  {show("length m") ? <td>{c.id !== cur ? text(c, "length") : <input aria-label={`length of ${c.label}`} inputMode="decimal" value={val(c, "length")} size={5}
                             onChange={(e) => set(c, "length", e.target.value)} className={edits[c.id]?.length !== undefined ? "dirty" : ""} />}</td> : null}
                  {show("findings") ? <td>{iss.length ? <a href={href("conductor", c.id)} className={`badge ${c.sev}`} title={iss.map((i) => `${i.rule}: ${i.message}`).join("\n")}>
                    {iss.length} {c.sev}</a> : null}</td> : null}
                </tr>);
            })}
            {bottom > 0 ? <tr style={{ height: bottom }} aria-hidden="true"><td colSpan={11} /></tr> : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
