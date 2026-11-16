// The app: a start screen when no project is open, else the main screen (diagram, issues, wires).
import { useCallback, useEffect, useRef, useState } from "react";
import { act, canRetry, get, post, say, upload } from "./api";
import { CardDialog } from "./cards";
import { Diagram, Legend, type Focus } from "./diagram/Diagram";
import { Issues, SkeletonRows, Wires } from "./panels";
import { SimSummary } from "./simulate";
import { classVoltage, SourceDialog } from "./source";
import { Logo } from "./theme/icons";
import { startTour, stopTour, Tour } from "./tour";
import type { CardTarget, ExportResult, Health, Issue, Node, Overlay, Session, SimGroup, Wire, Workspace } from "./types";
import { Glyph, MenuButton, Toasts, type Toast } from "./ui";

type Theme = "light" | "dark";
const SHEET = /\.(xlsx|csv)$/i;

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [ws, setWs] = useState<Workspace | null>(null);
  const [busy, setBusy] = useState(false);                     // opening a project or importing
  const [importing, setImporting] = useState<{ name: string; p: number } | null>(null);
  const [theme, setTheme] = useState<Theme>("light");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [issuesOpen, setIssuesOpen] = useState(true);
  const [wiresOpen, setWiresOpen] = useState(true);
  const [selWire, setSelWire] = useState<string | null>(null), [selIssue, setSelIssue] = useState<number | null>(null);
  const [reveal, setReveal] = useState<{ id: string; n: number } | null>(null);   // the Wires drawer scrolls to this wire
  const [health, setHealth] = useState<Health | null>(null);
  const [focus, setFocus] = useState<Focus | null>(null);
  const [card, setCard] = useState<CardTarget | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [sim, setSim] = useState<{ o: Overlay; stale: boolean } | null>(null);   // the simulation drawn on the diagram; stale after any edit
  const [simOpen, setSimOpen] = useState(true);                   // the summary panel: open after Simulate, a chip while a source is placed
  const [pick, setPick] = useState(false), [srcAt, setSrcAt] = useState<Node | null>(null);   // "+ Source": choosing the attach point, then the dialog
  const picker = useRef<HTMLInputElement>(null);

  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((l) => [...l.slice(-2), { ...t, id }]);
    const keep = t.tone === "err" && !!t.action;   // an error with Retry stays until closed
    if (!keep) setTimeout(() => setToasts((l) => l.filter((x) => x.id !== id)), t.action ? 8000 : 5000);
  }, []);
  const fail = useCallback((e: unknown, retry?: () => void) =>
    toast({ tone: "err", text: say(e), action: retry && canRetry(e) ? { label: "Retry", run: retry } : undefined }), [toast]);

  const applyTheme = (t: Theme) => { setTheme(t); document.documentElement.dataset.theme = t; };
  const clearSel = () => { setSelWire(null); setSelIssue(null); setFocus(null); };
  const show = (w: Workspace) => { setWs(w); clearSel(); setToasts([]); setIssuesOpen(true); setWiresOpen(true); setSim(null); setCard(null); setPick(false); setSrcAt(null); };
  /** An edit came back as a Workspace: swap it in without touching the view, and the simulation no longer matches it. */
  const edited = useCallback((w: Workspace) => { setWs(w); setSim((s) => s && { ...s, stale: true }); }, []);

  const loadSession = useCallback(() => {
    setFatal(null);
    get<Session>("/api/session").then((s) => {
      setSession(s); applyTheme(s.theme === "dark" ? "dark" : "light");
      if (s.project) { setBusy(true); get<Workspace>("/api/workspace").then(show, (e) => fail(e, loadSession)).finally(() => setBusy(false)); }
    }, (e) => setFatal(say(e)));
  }, [fail]);
  useEffect(loadSession, [loadSession]);
  useEffect(() => { get<Health>("/api/health").then(setHealth, () => { /* drawings stay enabled; the export reports its own error */ }); }, []);

  const open = useCallback((body: { path?: string; example?: boolean }) => {
    setBusy(true); setToasts([]);
    post<Workspace>("/api/open", body).then((w) => {
      show(w);
      if (body.example) { act("example-open"); if (session && !session.tour_done) setTimeout(startTour, 400); }
    }, (e) => fail(e, () => open(body))).finally(() => setBusy(false));
  }, [fail, session]);

  const importFile = useCallback((f: File) => {
    if (!SHEET.test(f.name)) { toast({ tone: "err", text: `${f.name} is not a wire sheet. Import an .xlsx or .csv file.` }); return; }
    act("import-start");
    setBusy(true); setToasts([]); setImporting({ name: f.name, p: 0 });
    upload<Workspace>("/api/import", f, (p) => setImporting({ name: f.name, p })).then((w) => { show(w); act("import-done"); },
      (e) => fail(e, () => importFile(f))).finally(() => { setBusy(false); setImporting(null); });
  }, [fail, toast]);

  // a sheet dropped anywhere on the window imports it
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    let depth = 0;
    const files = (e: DragEvent) => !!e.dataTransfer && [...e.dataTransfer.types].includes("Files");
    const enter = (e: DragEvent) => { if (files(e)) { depth++; setDragging(true); } };
    const leave = (e: DragEvent) => { if (files(e) && --depth <= 0) { depth = 0; setDragging(false); } };
    const over = (e: DragEvent) => { if (files(e)) e.preventDefault(); };
    const drop = (e: DragEvent) => { if (!files(e)) return; e.preventDefault(); depth = 0; setDragging(false); const f = e.dataTransfer!.files[0]; if (f) importFile(f); };
    window.addEventListener("dragenter", enter); window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over); window.addEventListener("drop", drop);
    return () => { window.removeEventListener("dragenter", enter); window.removeEventListener("dragleave", leave); window.removeEventListener("dragover", over); window.removeEventListener("drop", drop); };
  }, [importFile]);

  /** Back to the start screen: the project is closed on the server and the recent list read again. */
  const closeProject = () => {
    stopTour();
    post("/api/close").then(() => get<Session>("/api/session")).then((s) => {
      setSession(s); setWs(null); clearSel(); setToasts([]); setSim(null); setCard(null); setPick(false); setSrcAt(null);
    }, (e) => fail(e, closeProject));
  };
  const removeRecent = (path: string) => {
    post("/api/recent/remove", { path }).then(() => setSession((s) => s && { ...s, recent: s.recent.filter((r) => r.path !== path) }), (e) => fail(e));
  };

  const toggleTheme = () => { const t = theme === "light" ? "dark" : "light"; applyTheme(t); post("/api/settings", { theme: t }).catch(() => { /* kept for this session */ }); };

  const simulate = () => {
    setSimulating(true);
    post<Overlay>("/api/simulate").then((o) => { setSim({ o, stale: false }); setSimOpen(true); act("simulate-done"); },
      (e) => fail(e, simulate)).finally(() => setSimulating(false));
  };
  const clearSim = () => { setSim(null); act("simulate-clear"); };
  const exportAs = (kind: string, what: string) => {
    toast({ tone: "info", text: `Exporting ${what.toLowerCase()}…` });
    post<ExportResult>("/api/export", { kind }).then((r) => toast({ tone: "ok", text: `${what}: ${r.files.length} ${r.files.length === 1 ? "file" : "files"} saved.`,
      action: { label: "Show folder", run: () => { post("/api/reveal", { path: r.folder }).catch((e) => fail(e)); } } }), (e) => fail(e, () => exportAs(kind, what)));
  };

  /** Zoom to and pulse the objects a list of typed refs ("component:ID", "conductor:ID", "pin:ID/C/P") names. */
  const focusOn = (objects: string[]) => {
    const ids: string[] = [];
    let wire: string | undefined;
    for (const o of objects) {
      const t = o.slice(0, o.indexOf(":")), id = o.slice(o.indexOf(":") + 1);
      if (t === "component") ids.push(id);
      else if (t === "pin") ids.push(id.split("/")[0]);
      else if (t === "conductor") { const w = ws?.conductors.find((c) => c.id === id); if (w) { ids.push(w.a, w.b); wire ??= w.id; } }
    }
    setSelWire(wire ?? null);
    setFocus({ ids, wire, nonce: Date.now() });
  };
  const pickIssue = (i: Issue) => {
    if (selIssue === i.k) { clearSel(); return; }   // the same issue again clears it
    focusOn(i.objects); setSelIssue(i.k); act("issue-click");
  };
  const pickGroup = (g: SimGroup) => focusOn(g.objects);
  const openWire = useCallback((id: string) => { setSelWire(id); setCard((c) => { if (!c) act("card-open"); return { type: "wire", id }; }); }, []);
  const showWire = (w: Wire) => { setSelIssue(null); setSelWire(w.id); setFocus({ ids: [w.a, w.b], wire: w.id, nonce: Date.now() }); };
  const pickWire = (w: Wire) => { showWire(w); act("wire-click"); };
  const openCard = useCallback((n: Node) => {
    if (pick) { setPick(false); setSrcAt(n); return; }
    setCard({ type: "component", id: n.id }); act("card-open");
  }, [pick]);
  const closeCard = useCallback(() => { setCard(null); act("card-close"); }, []);
  const saved = useCallback((w: Workspace, what: string) => { edited(w); setCard(null); act("card-close"); toast({ tone: "ok", text: what.startsWith("Removed") ? `${what}.` : `Saved ${what}.` }); }, [edited, toast]);
  const sourceAdded = useCallback((w: Workspace) => { edited(w); setSrcAt(null); act("source-added"); }, [edited]);
  const picking = pick || srcAt !== null;  // the tour steps aside while a source is being placed (docs/tour.md)
  useEffect(() => { if (picking) setSimOpen(false); }, [picking]);
  useEffect(() => { act(picking ? "source-pick" : "source-pick-end"); }, [picking]);
  useEffect(() => {
    if (!pick) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setPick(false); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [pick]);
  // Esc clears the selection when nothing else (a dialog, a menu, source placing) is using the key
  const busyKey = card !== null || srcAt !== null || pick;
  useEffect(() => {
    if (busyKey) return;
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || document.querySelector("[role=menu], .scrim") || (e.target as HTMLElement).closest?.("input, textarea, select")) return;
      clearSel();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [busyKey]);  // eslint-disable-line react-hooks/exhaustive-deps
  // what the tour asks for (docs/tour.md): these send no action events, so the tour does not advance by itself
  const wsRef = useRef(ws); wsRef.current = ws;
  useEffect(() => {
    const h = (e: Event) => {
      const { what, arg } = (e as CustomEvent<{ what: string; arg?: string }>).detail;
      if (what === "close") { setCard(null); setSrcAt(null); setPick(false); }
      if (what === "clear") clearSel();
      if (what === "sim-collapse") setSimOpen(false);
      if (what === "show-wire") {
        const w = wsRef.current?.conductors.find((x) => x.id === arg);
        if (w) { setWiresOpen(true); showWire(w); setReveal({ id: w.id, n: Date.now() }); }
      }
    };
    window.addEventListener("schemagen:tour", h);
    return () => window.removeEventListener("schemagen:tour", h);
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const filePicker = <input ref={picker} type="file" accept=".xlsx,.csv" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importFile(f); }} />;
  const overlays = <>
    {dragging && <div className="drop-overlay" aria-hidden="true"><div className="drop-card anim-pop"><Glyph name="upload" size={24} /><strong>Drop to import the wire sheet</strong><span>.xlsx or .csv</span></div></div>}
    {importing && <ImportBar name={importing.name} p={importing.p} />}
    <Toasts list={toasts} close={(id) => setToasts((l) => l.filter((t) => t.id !== id))} />
    <Tour />
  </>;

  if (fatal) return <div className="fatal" role="alert"><Logo size={32} /><p>{fatal}</p><button className="btn btn-primary" onClick={loadSession}>Try again</button></div>;
  if (!session) return <div className="start" aria-busy="true"><div className="start-col"><div className="skeleton" style={{ height: 40, width: 40 }} /><SkeletonRows n={4} tall /></div></div>;

  if (!ws && !busy) return <>
    <Start session={session} onExample={() => open({ example: true })} onRecent={(path) => open({ path })} onRemove={removeRecent} onPick={() => picker.current?.click()} />
    {filePicker}{overlays}
  </>;

  const drawingsOff = health?.drawings?.available === false;
  const counts = ws ? { error: ws.issues.filter((i) => i.severity === "error").length, all: ws.issues.length } : null;
  return <div className="main">
    <header className="topbar">
      <div className="brand"><button className="btn btn-ghost btn-icon logo-btn" onClick={closeProject} aria-label="Back to the start screen" title="Back to the start screen"><Logo size={20} /></button><h1 className="project" title={ws?.project.root}>{ws ? ws.project.name : <span className="skeleton" style={{ width: 160, height: 14, display: "inline-block" }} />}</h1></div>
      <div className="actions">
        <button className="btn" data-tour="import" onClick={() => picker.current?.click()}><Glyph name="upload" />Import</button>
        <MenuButton label="Export" tour="export" items={[
          { label: "Wire sheet", hint: "XLSX, your sheet written back", run: () => exportAs("wirelist", "Wire sheet") },
          { label: "Wiring checklist", hint: "printable, per component", run: () => exportAs("pinout", "Wiring checklist") },
          { label: "Fault sweep", hint: "HTML report", run: () => exportAs("faults", "Fault sweep") },
          drawingsOff ? { label: "Harness drawings", hint: "needs Graphviz and WireViz", title: health?.drawings?.message, disabled: true, run: () => { /* not available */ } }
            : { label: "Harness drawings", hint: "SVG", run: () => exportAs("drawings", "Harness drawings") }]} />
        <button className="btn btn-primary" data-tour="simulate" onClick={simulate} disabled={!ws || simulating} aria-busy={simulating}>
          <Glyph name="play" />{simulating ? "Simulating…" : "Simulate"}</button>
        {sim && <SimSummary o={sim.o} stale={sim.stale} open={simOpen} onOpen={setSimOpen} onGroup={pickGroup} onClear={clearSim} />}
        <span className="sep" aria-hidden="true" />
        <button className="btn btn-ghost btn-icon" onClick={toggleTheme} aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"} title={theme === "light" ? "Dark theme" : "Light theme"}>
          <Glyph name={theme === "light" ? "moon" : "sun"} /></button>
        <MenuButton label="Help" icon="help" iconOnly tour="help" items={[{ label: "Replay the tour", run: startTour }]} />
      </div>
    </header>
    <div className="body">
      {issuesOpen && <Issues issues={ws?.issues ?? null} loading={busy} sel={selIssue} onPick={pickIssue} onClose={() => setIssuesOpen(false)} />}
      <main className="canvas" aria-busy={busy}>
        {!issuesOpen && counts && <button className="issues-chip" onClick={() => setIssuesOpen(true)} data-tour="issues">
          {counts.error > 0 && <span className="dot error" aria-hidden="true" />}Issues <span className="count">{counts.all}</span></button>}
        {ws && !busy ? <Diagram ws={ws} focus={focus} selWire={selWire} onCard={openCard} onWire={(id) => { if (!pick) openWire(id); }} onLink={(a, b) => { if (!pick) { setCard({ type: "link", id: a, to: b }); act("card-open"); } }} onClear={clearSel} overlay={sim} picking={pick} /> : <DiagramSkeleton />}
        {ws && !busy && <div className="canvas-tools">
          <button className="btn" data-tour="add-source" aria-pressed={pick} onClick={() => setPick((p) => !p)}><Glyph name="plus" />Source</button></div>}
        {pick && <div className="pick-hint anim-pop" role="status"><Glyph name="plus" size={14} />Click a bus or component to attach the source<span className="kbd">Esc</span></div>}
      </main>
    </div>
    <Wires wires={ws?.conductors ?? null} legend={ws && !busy && <Legend palette={ws.palette} used={ws.edges.flatMap((e) => e.cls)} />} open={wiresOpen} loading={busy} sel={selWire} reveal={reveal} onPick={pickWire} onOpen={openWire}
           onToggle={() => setWiresOpen((o) => { if (!o) act("wires-open"); return !o; })} />
    {card && ws && <CardDialog target={card} ws={ws} stale={!!sim?.stale} onClose={closeCard} onSwitch={setCard} onSaved={saved} onError={fail} />}
    {srcAt && ws && <SourceDialog at={srcAt} volt={classVoltage(ws, srcAt.id)} onClose={() => setSrcAt(null)} onSaved={sourceAdded} onError={fail} />}
    {filePicker}{overlays}
  </div>;
}

function Start({ session, onExample, onRecent, onRemove, onPick }: { session: Session; onExample: () => void; onRecent: (p: string) => void; onRemove: (p: string) => void; onPick: () => void }) {
  return <div className="start">
    <div className="start-col">
      <Logo size={40} />
      <h1>schemagen</h1>
      <p className="lede">Drop your wire sheet to see the whole system as one diagram, and what is wrong with it.</p>
      <button className="btn btn-primary btn-lg" onClick={onExample}>Open the example project</button>
      <div className="or" aria-hidden="true"><span>or</span></div>
      <div className="dropzone" onClick={onPick} role="button" tabIndex={0} aria-label="Import your wire sheet (.xlsx or .csv)"
           onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}>
        <Glyph name="upload" size={20} />
        <strong>Import your wire sheet</strong>
        <span>Drop an .xlsx or .csv file here, or <u>choose a file</u></span>
      </div>
      {session.recent.length > 0 && <section className="recent" aria-labelledby="recent-h">
        <h2 id="recent-h">Recent</h2>
        <ul>{session.recent.map((r) => <li key={r.path}><button className="r-open" onClick={() => onRecent(r.path)} title={r.path}>
          <Glyph name="file" /><span className="r-name">{r.name}</span><span className="r-date">{ago(r.opened)}</span>
        </button><button className="btn btn-ghost btn-icon btn-sm r-remove" onClick={() => onRemove(r.path)} aria-label={`Remove ${r.name} from the list`} title="Remove from the list"><Glyph name="x" size={14} /></button></li>)}</ul>
      </section>}
    </div>
  </div>;
}

function ImportBar({ name, p }: { name: string; p: number }) {
  const done = p >= 1;
  return <div className="importbar anim-pop" role="status" aria-label={`Importing ${name}`}>
    <span className="ib-text">{done ? "Reading" : "Uploading"} <strong>{name}</strong></span>
    <span className={`bar${done ? " indeterminate" : ""}`}><span style={{ width: done ? undefined : `${Math.round(p * 100)}%` }} /></span>
  </div>;
}

function DiagramSkeleton() {
  return <div className="diagram-skel" aria-hidden="true">{[3, 4, 3, 2, 5].map((n, c) =>
    <div key={c} className="skel-col">{Array.from({ length: n }, (_, i) => <div key={i} className="skeleton skel-card" />)}</div>)}</div>;
}

function ago(iso: string) {
  const d = new Date(iso), days = Math.round((Date.now() - d.getTime()) / 864e5);
  return days <= 0 ? "Today" : days === 1 ? "Yesterday" : days < 7 ? `${days} days ago` : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
