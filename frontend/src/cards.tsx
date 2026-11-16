// The popup card for one component or one wire: what it is, its pins, its issues, a few edit fields (docs/api.md, Cards).
import { useEffect, useState } from "react";
import { DrawingRows } from "./drawing";
import type { Drawing } from "./types";
import { canRetry, del, get, post, say } from "./api";
import { SkeletonRows } from "./panels";
import { KindIcon } from "./theme";
import type { CardTarget, ComponentCard, Issue, OverlayItem, Source, Wire, WireCard, Workspace } from "./types";
import { Dialog, DialogFooter, DialogTitle } from "./ui";

const KINDS = ["device", "load", "sensor", "controller", "switch", "relay", "battery", "dcdc", "breaker", "fuse", "terminator", "splice", "bus"];
const text = (v: string | number | null | undefined) => (v === null || v === undefined ? "" : String(v));

/** One fetch with a reload: the card for `path`, or the plain message that explains why not. */
export function useCard<T>(path: string) {
  const [s, set] = useState<{ data: T | null; err: unknown }>({ data: null, err: null });
  const [n, bump] = useState(0);
  useEffect(() => {
    let live = true;
    set({ data: null, err: null });
    get<T>(path).then((data) => live && set({ data, err: null }), (err) => live && set({ data: null, err }));
    return () => { live = false; };
  }, [path, n]);
  return [s.data, s.err, () => bump((x) => x + 1)] as const;
}

function Status({ sim, stale }: { sim?: OverlayItem; stale: boolean }) {
  if (!sim) return null;
  return <p className={`card-status ${sim.status}${stale ? " stale" : ""}`} role="status">
    <span className={`dot ${sim.status === "error" ? "error" : sim.status === "warn" ? "warning" : ""}`} aria-hidden="true" />
    <span>{sim.reason}{stale && " (out of date)"}</span></p>;
}

function Issues({ list }: { list: Issue[] }) {
  if (!list.length) return null;
  return <ul className="card-issues" aria-label="Issues">{list.map((i) => <li key={i.k}>
    <span className={`dot ${i.severity}`} aria-hidden="true" /><span><strong>{i.title || i.message}</strong>{i.title && i.message && <span className="faint issue-more">{i.message}</span>}</span></li>)}</ul>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

interface Props {
  target: CardTarget; ws: Workspace; stale: boolean; onClose: () => void; onSwitch: (t: CardTarget) => void;
  onSaved: (w: Workspace, what: string) => void; onError: (e: unknown, retry?: () => void) => void; onDiagram: (scope: string) => void;
}

export function CardDialog(p: Props) {
  const key = `${p.target.type}:${p.target.id}:${p.target.type === "link" ? p.target.to : ""}`;
  const src = p.target.type === "component" ? p.ws.sources.find((s) => s.id === p.target.id) : undefined;
  return <Dialog onClose={p.onClose} tour="card" className="card-dialog" focusKey={key}>
    {p.target.type === "link" ? <LinkView key={key} {...p} /> : p.target.type === "wire" ? <WireView key={key} {...p} /> : src ? <SourceView key={key} src={src} {...p} /> : <ComponentView key={key} {...p} />}
  </Dialog>;
}

export function Failed({ err, retry }: { err: unknown; retry: () => void }) {
  return <div className="card-failed" role="alert"><p>{say(err)}</p>{canRetry(err) && <button className="btn" onClick={retry}>Retry</button>}</div>;
}

/** The title and footer go to the dialog's own header and footer; the children are the body. */
function Shell({ title, footer, children }: { title: React.ReactNode; footer?: React.ReactNode; children: React.ReactNode }) {
  return <><DialogTitle>{title}</DialogTitle><DialogFooter>{footer}</DialogFooter>{children}</>;
}

const titleSkel = <span className="skeleton" style={{ width: 160, height: 16, display: "inline-block", verticalAlign: "middle" }} />;

/** Edit mode keeps the card's own fields: the footer shows Edit until then, Cancel and Save after. */
function EditFooter({ edit, setEdit, reset, save, dirty, bad, busy }: { edit: boolean; setEdit: (v: boolean) => void; reset: () => void; save: () => void; dirty: boolean; bad: boolean; busy: boolean }) {
  return edit ? <><span className="spacer" /><button className="btn" onClick={() => { reset(); setEdit(false); }}>Cancel</button>
    <button className="btn btn-primary" onClick={save} disabled={!dirty || bad || busy} aria-busy={busy}>Save</button></>
    : <><span className="spacer" /><button className="btn" onClick={() => setEdit(true)}>Edit</button></>;
}

function LinkView({ target, onSwitch, onDiagram }: Props) {
  const to = target.type === "link" ? target.to : "";
  const [d, err, reload] = useCard<Drawing>(`/api/drawing/${encodeURIComponent(target.id)}?to=${encodeURIComponent(to)}`);
  return <Shell title={d ? `${d.name} to ${d.to?.name ?? to}` : titleSkel} footer={d && <><button className="btn" onClick={() => onDiagram(`connection:${target.id}~${to}`)}>Wiring diagram</button><span className="spacer" /></>}>
    {err ? <Failed err={err} retry={reload} /> : !d ? <div className="card-skel" aria-busy="true"><SkeletonRows n={5} /></div> : <DrawingRows d={d} onSwitch={onSwitch} />}
  </Shell>;
}

function ComponentView({ target, stale, onSwitch, onSaved, onError, onDiagram }: Props) {
  const [c, err, reload] = useCard<ComponentCard>(`/api/card/component/${encodeURIComponent(target.id)}`);
  const [d] = useCard<Drawing>(`/api/drawing/${encodeURIComponent(target.id)}`);   // its wiring, drawn: replaces the pin table
  const [name, setName] = useState(""), [kind, setKind] = useState(""), [rating, setRating] = useState("");
  const [busy, setBusy] = useState(false), [edit, setEdit] = useState(false);
  const reset = () => { if (c) { setName(c.name); setKind(c.kind); setRating(text(c.rating_A)); } };
  useEffect(reset, [c]);  // eslint-disable-line react-hooks/exhaustive-deps

  const protective = kind === "breaker" || kind === "fuse";
  const ratingNum = rating.trim() === "" ? null : Number(rating);
  const bad = !name.trim() || (protective && ratingNum !== null && !(ratingNum > 0));
  const changes: Record<string, unknown> = {};
  if (c) {
    if (name.trim() !== c.name) changes.name = name.trim();
    if (kind !== c.kind) changes.kind = kind;
    if (protective && ratingNum !== null && ratingNum !== c.rating_A) changes.rating_A = ratingNum;
  }
  const dirty = Object.keys(changes).length > 0;
  const save = () => {
    setBusy(true);
    post<Workspace>(`/api/component/${encodeURIComponent(target.id)}`, changes).then((w) => onSaved(w, c?.name || target.id),
      (e) => { setBusy(false); onError(e, save); });
  };
  const fixedKind = !!c && c.kind === "harness";

  return <Shell title={c ? c.name || c.id : titleSkel} footer={c && <>{!edit && d && <button className="btn" onClick={() => onDiagram(`component:${target.id}`)}>Wiring diagram</button>}<EditFooter {...{ edit, setEdit, reset, save, dirty, bad, busy }} /></>}>
    {err ? <Failed err={err} retry={reload} /> : !c ? <div className="card-skel" aria-busy="true"><SkeletonRows n={3} /><SkeletonRows n={5} /></div> : <>
      <p className="card-kind"><span className="kind-chip"><KindIcon kind={c.kind} size={14} />{c.kind}</span>
        <span className="faint">{c.id}{c.location ? ` · ${c.location}` : ""}</span></p>
      <Status sim={c.sim} stale={stale} />
      <Issues list={c.issues} />
      {edit && <div className="fields">
        <Field label="Name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} aria-invalid={!name.trim()} autoFocus /></Field>
        <Field label="Kind"><select className="input" value={kind} onChange={(e) => setKind(e.target.value)} disabled={fixedKind}>
          {!KINDS.includes(c.kind) && <option value={c.kind}>{c.kind}</option>}{KINDS.map((k) => <option key={k} value={k}>{k}</option>)}</select></Field>
        {protective && <Field label="Rating (A)"><input className="input" inputMode="decimal" value={rating} onChange={(e) => setRating(e.target.value)} aria-invalid={ratingNum !== null && !(ratingNum > 0)} /></Field>}
      </div>}
      {d ? <DrawingRows d={d} onSwitch={onSwitch} /> : <SkeletonRows n={5} />}
    </>}
  </Shell>;
}

function WireView({ target, ws, stale, onSwitch, onSaved, onError }: Props) {
  const [c, err, reload] = useCard<WireCard>(`/api/card/wire/${encodeURIComponent(target.id)}`);
  const [f, setF] = useState({ label: "", name: "", gauge: "", current: "", notes: "" });
  const [busy, setBusy] = useState(false), [edit, setEdit] = useState(false);
  const reset = () => { if (c) setF({ label: c.label, name: c.name, gauge: c.gauge, current: text(c.current), notes: c.notes }); };
  useEffect(reset, [c]);  // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF((x) => ({ ...x, [k]: e.target.value }));
  const cur = f.current.trim() === "" ? null : Number(f.current);
  const bad = cur !== null && !(cur >= 0);
  const changes: Record<string, unknown> = {};
  if (c) {
    if (f.label !== c.label) changes.label = f.label;
    if (f.name !== c.name) changes.name = f.name;
    if (f.gauge !== c.gauge) changes.gauge = f.gauge;
    if (cur !== c.current && !bad) changes.current = cur;
    if (f.notes !== c.notes) changes.notes = f.notes;
  }
  const dirty = Object.keys(changes).length > 0;
  const save = () => {
    setBusy(true);
    post<Workspace>(`/api/wire/${encodeURIComponent(target.id)}`, changes).then((w) => onSaved(w, c?.label || target.id), (e) => { setBusy(false); onError(e, save); });
  };
  const w: Wire | undefined = ws.conductors.find((x) => x.id === target.id);
  const ends = w ? [w.a, w.b].filter((id, i, l) => l.indexOf(id) === i && ws.components.some((n) => n.id === id)) : [];
  const meta = (c ? [["Label", c.label], ["Name", c.name], ["From", c.from], ["To", c.to], ["Gauge", c.gauge], ["Voltage", c.voltage], ["Current", c.current === null ? "" : `${c.current} A`],
    ["Length", c.length === null ? "" : `${c.length} m`], ["Harness", c.harness], ["Protection", c.protection], ["Status", c.status], ["Notes", c.notes]] : []).filter(([, v]) => v);

  return <Shell title={c ? <><span className="swatch swatch-lg" style={{ "--c": c.hex } as React.CSSProperties} aria-hidden="true" />{c.label || c.id}</> : titleSkel}
    footer={c && <EditFooter {...{ edit, setEdit, reset, save, dirty, bad, busy }} />}>
    {err ? <Failed err={err} retry={reload} /> : !c ? <div className="card-skel" aria-busy="true"><SkeletonRows n={3} /><SkeletonRows n={5} /></div> : <>
      <p className="card-kind"><span className="kind-chip">wire</span><span className="faint">{c.id}{c.colour ? ` · ${c.colour}` : ""}</span></p>
      <Status sim={c.sim} stale={stale} />
      {edit && <div className="fields">
        <Field label="Label"><input className="input" value={f.label} onChange={set("label")} autoFocus /></Field>
        <Field label="Name"><input className="input" value={f.name} onChange={set("name")} /></Field>
        <Field label="Gauge"><input className="input" value={f.gauge} onChange={set("gauge")} /></Field>
        <Field label="Current (A)"><input className="input" inputMode="decimal" value={f.current} onChange={set("current")} aria-invalid={bad} /></Field>
        <Field label="Notes"><textarea className="input" rows={2} value={f.notes} onChange={set("notes")} /></Field>
      </div>}
      <dl className="meta">{meta.map(([k, v]) => <div key={k} className={k === "Notes" ? "wide" : undefined}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      <Issues list={c.issues} />
      {ends.length > 0 && <p className="card-ends"><span className="faint">Ends</span>{ends.map((id) => <button key={id} className="link" onClick={() => onSwitch({ type: "component", id })}>
        {ws.components.find((n) => n.id === id)?.name || id}</button>)}</p>}
    </>}
  </Shell>;
}

const SRC_TYPE: Record<string, string> = { battery: "Battery", dcdc: "DC-DC converter", bench: "Bench supply" };

/** A source added in the app: not part of the wire sheet, so no fetch; it can be removed. */
function SourceView({ src, ws, onClose, onSaved, onError }: Props & { src: Source }) {
  const [busy, setBusy] = useState(false);
  const remove = () => {
    setBusy(true);
    del<Workspace>(`/api/sources/${encodeURIComponent(src.id)}`).then((w) => onSaved(w, `Removed ${src.name}`), (e) => { setBusy(false); onError(e, remove); });
  };
  const at = ws.components.find((n) => n.id === src.attach);
  const rows: [string, string][] = [["Attached to", at?.name || src.attach], ["Voltage", `${src.nominal_V} V`]];
  if (src.r_int_ohm !== null) rows.push(["Internal resistance", `${src.r_int_ohm} Ω`]);
  if (src.i_limit_A !== null) rows.push(["Current limit", `${src.i_limit_A} A`]);
  if (src.capacity_Ah !== null) rows.push(["Capacity", `${src.capacity_Ah} Ah`]);
  return <Shell title={src.name}
    footer={<><button className="btn btn-danger" onClick={remove} disabled={busy} aria-busy={busy}>Remove source</button><span className="spacer" /><button className="btn" onClick={onClose}>Cancel</button></>}>
    <p className="card-kind"><span className="kind-chip"><KindIcon kind={src.type} size={14} />{SRC_TYPE[src.type] ?? src.type}</span><span className="faint">{src.id} · added in the app, not in your sheet</span></p>
    <dl className="meta">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd title={v}>{v}</dd></div>)}</dl>
  </Shell>;
}
