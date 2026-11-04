import { useState } from "react";
import { useApp } from "../App";
import { api, href, Index } from "../data";

export function DiffView() {
  const { ix, setIndex, toast } = useApp();
  const [rev, setRev] = useState("HEAD");
  const [text, setText] = useState<string | null>(null);
  const [fix, setFix] = useState<{ flips: { id: string; label: string; reason: string }[]; ops: unknown[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const diff = async () => {
    setBusy(true);
    try { setText((await api<{ text: string }>(`/api/diff?rev=${encodeURIComponent(rev)}`)).text); } catch (e) { setText(null); toast(`diff failed: ${e}`); }
    finally { setBusy(false); }
  };
  const preview = async () => setFix(await api("/api/fix/direction"));
  const apply = async () => {
    setBusy(true);
    try { const r = await api<{ applied: number; index: Index }>("/api/fix/direction", { method: "POST" }); setIndex(r.index); setFix(null); toast(`direction fixed on ${r.applied} wire(s), stored as a change set`); }
    catch (e) { toast(`${e}`); } finally { setBusy(false); }
  };
  const undo = async () => { const r = await api<{ removed: string | null; index: Index }>("/api/undo", { method: "POST" }); setIndex(r.index); toast(r.removed ? `undone: ${r.removed}` : "nothing to undo"); };
  return (
    <section className="diff">
      <h1>Changes &amp; diff</h1>
      <div className="cols">
        <section>
          <h2>Diff against a git revision</h2>
          <div className="toolbar"><label>Revision <input value={rev} onChange={(e) => setRev(e.target.value)} aria-label="Git revision" size={12} /></label>
            <button onClick={diff} disabled={busy}>Show diff</button></div>
          {text !== null ? <pre className="difftext" data-testid="diff-text">{text.split("\n").map((l, k) => <span key={k} className={l[0] === "+" ? "add" : l[0] === "-" ? "del" : l[0] === "~" ? "chg" : ""}>{l + "\n"}</span>)}</pre> : null}
        </section>
        <section>
          <h2>Fix the wire direction convention</h2>
          <button onClick={preview}>Preview fix</button>
          {fix ? <div data-testid="fix-preview">{fix.flips.length ? <><p>{fix.flips.length} wire(s) would swap their ends (labels stay):</p>
            <ul>{fix.flips.map((f) => <li key={f.id}><a href={href("conductor", f.id)}>{f.label}</a> — {f.reason}</li>)}</ul>
            <button className="primary" onClick={apply} disabled={busy}>Apply as a change set</button></> : <p>No direction findings: nothing to change.</p>}</div> : null}
          <h2>Stored change sets <small>{ix.project.changes.length}</small></h2>
          <ul>{ix.project.changes.map((c) => <li key={c.id}><code>{c.id}</code> {c.title} <span className="muted">{c.ops} ops, {c.created}</span></li>)}</ul>
          <button onClick={undo} disabled={!ix.project.changes.length}>Undo last change set</button>
        </section>
      </div>
    </section>
  );
}
