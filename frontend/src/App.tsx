// The app: a start screen when no project is open, else the main screen (diagram, issues, wires).
import { useCallback, useEffect, useRef, useState } from "react";
import { act, canRetry, get, post, say, upload } from "./api";
import { Diagram, type Focus } from "./diagram/Diagram";
import { Issues, SkeletonRows, Wires } from "./panels";
import { Logo } from "./theme/icons";
import { startTour, Tour } from "./tour";
import type { ExportResult, Issue, Node, Overlay, Session, Wire, Workspace } from "./types";
import { Dialog, Glyph, MenuButton, Toasts, type Toast } from "./ui";

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
  const [selWire, setSelWire] = useState<string | null>(null);
  const [focus, setFocus] = useState<Focus | null>(null);
  const [card, setCard] = useState<Node | null>(null);
  const [simulating, setSimulating] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((l) => [...l.slice(-2), { ...t, id }]);
    if (!t.action) setTimeout(() => setToasts((l) => l.filter((x) => x.id !== id)), 5000);
  }, []);
  const fail = useCallback((e: unknown, retry?: () => void) =>
    toast({ tone: "err", text: say(e), action: retry && canRetry(e) ? { label: "Retry", run: retry } : undefined }), [toast]);

  const applyTheme = (t: Theme) => { setTheme(t); document.documentElement.dataset.theme = t; };
  const show = (w: Workspace) => { setWs(w); setSelWire(null); setFocus(null); setIssuesOpen(true); setWiresOpen(true); };

  const loadSession = useCallback(() => {
    setFatal(null);
    get<Session>("/api/session").then((s) => {
      setSession(s); applyTheme(s.theme === "dark" ? "dark" : "light");
      if (s.project) { setBusy(true); get<Workspace>("/api/workspace").then(show, (e) => fail(e, loadSession)).finally(() => setBusy(false)); }
    }, (e) => setFatal(say(e)));
  }, [fail]);
  useEffect(loadSession, [loadSession]);

  const open = useCallback((body: { path?: string; example?: boolean }) => {
    setBusy(true);
    post<Workspace>("/api/open", body).then((w) => {
      show(w);
      if (body.example) { act("example-open"); if (session && !session.tour_done) setTimeout(startTour, 400); }
    }, (e) => fail(e, () => open(body))).finally(() => setBusy(false));
  }, [fail, session]);

  const importFile = useCallback((f: File) => {
    if (!SHEET.test(f.name)) { toast({ tone: "err", text: `${f.name} is not a wire sheet. Import an .xlsx or .csv file.` }); return; }
    act("import-start");
    setBusy(true); setImporting({ name: f.name, p: 0 });
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

  const toggleTheme = () => { const t = theme === "light" ? "dark" : "light"; applyTheme(t); post("/api/settings", { theme: t }).catch(() => { /* kept for this session */ }); };

  const simulate = () => {
    setSimulating(true);
    post<Overlay>("/api/simulate").then((o) => { toast({ tone: o.ok ? "ok" : "info", text: `Simulation: ${o.summary.text}.` }); act("simulate-done"); },
      (e) => fail(e, simulate)).finally(() => setSimulating(false));
  };
  const exportAs = (kind: string, what: string) => {
    toast({ tone: "info", text: `Exporting ${what.toLowerCase()}…` });
    post<ExportResult>("/api/export", { kind }).then((r) => toast({ tone: "ok", text: `${what}: ${r.files.length} ${r.files.length === 1 ? "file" : "files"} saved.`,
      action: { label: "Show folder", run: () => { post("/api/reveal", { path: r.folder }).catch((e) => fail(e)); } } }), (e) => fail(e, () => exportAs(kind, what)));
  };

  const pickIssue = (i: Issue) => {
    const ids: string[] = [];
    let wire: string | undefined;
    for (const o of i.objects) {
      const t = o.slice(0, o.indexOf(":")), id = o.slice(o.indexOf(":") + 1);
      if (t === "component") ids.push(id);
      else if (t === "pin") ids.push(id.split("/")[0]);
      else if (t === "conductor") { const w = ws?.conductors.find((c) => c.id === id); if (w) { ids.push(w.a, w.b); wire ??= w.id; } }
    }
    setSelWire(wire ?? null);
    setFocus({ ids, wire, nonce: Date.now() });
    act("issue-click");
  };
  const pickWire = (w: Wire) => { setSelWire(w.id); setFocus({ ids: [w.a, w.b], wire: w.id, nonce: Date.now() }); act("wire-click"); };
  const openCard = useCallback((n: Node) => { setCard(n); act("card-open"); }, []);
  const closeCard = useCallback(() => { setCard(null); act("card-close"); }, []);

  const filePicker = <input ref={picker} type="file" accept=".xlsx,.csv" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importFile(f); }} />;
  const overlays = <>
    {dragging && <div className="drop-overlay" aria-hidden="true"><div className="drop-card anim-pop"><Glyph name="upload" size={24} /><strong>Drop to import the wire sheet</strong><span>.xlsx or .csv</span></div></div>}
    {importing && <ImportBar name={importing.name} p={importing.p} />}
    <Toasts list={toasts} close={(id) => setToasts((l) => l.filter((t) => t.id !== id))} />
    <Tour />
  </>;

  if (fatal) return <div className="fatal" role="alert"><Logo size={32} /><p>{fatal}</p><button className="btn primary" onClick={loadSession}>Try again</button></div>;
  if (!session) return <div className="start" aria-busy="true"><div className="start-col"><div className="skeleton" style={{ height: 40, width: 40 }} /><SkeletonRows n={4} tall /></div></div>;

  if (!ws && !busy) return <>
    <Start session={session} onExample={() => open({ example: true })} onRecent={(path) => open({ path })} onPick={() => picker.current?.click()} />
    {filePicker}{overlays}
  </>;

  const counts = ws ? { error: ws.issues.filter((i) => i.severity === "error").length, all: ws.issues.length } : null;
  return <div className="main">
    <header className="topbar">
      <div className="brand"><Logo size={20} /><h1 className="project" title={ws?.project.root}>{ws ? ws.project.name : <span className="skeleton" style={{ width: 160, height: 14, display: "inline-block" }} />}</h1></div>
      <div className="actions">
        <button className="btn" data-tour="import" onClick={() => picker.current?.click()}><Glyph name="upload" />Import</button>
        <MenuButton label="Export" tour="export" items={[
          { label: "Harness drawings", hint: "SVG, needs Graphviz", run: () => exportAs("drawings", "Harness drawings") },
          { label: "Pinout", hint: "XLSX and HTML", run: () => exportAs("pinout", "Pinout") },
          { label: "Fault sweep", hint: "HTML report", run: () => exportAs("faults", "Fault sweep") },
          { label: "Wire list", hint: "XLSX", run: () => exportAs("wirelist", "Wire list") }]} />
        <button className="btn primary" data-tour="simulate" onClick={simulate} disabled={!ws || simulating} aria-busy={simulating}>
          <Glyph name="play" />{simulating ? "Simulating…" : "Simulate"}</button>
        <span className="sep" aria-hidden="true" />
        <button className="icon-btn" onClick={toggleTheme} aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"} title={theme === "light" ? "Dark theme" : "Light theme"}>
          <Glyph name={theme === "light" ? "moon" : "sun"} /></button>
        <MenuButton label="Help" icon="help" iconOnly tour="help" items={[{ label: "Replay the tour", run: startTour }]} />
      </div>
    </header>
    <div className="body">
      {issuesOpen && <Issues issues={ws?.issues ?? null} loading={busy} onPick={pickIssue} onClose={() => setIssuesOpen(false)} />}
      <main className="canvas" aria-busy={busy}>
        {!issuesOpen && counts && <button className="issues-chip" onClick={() => setIssuesOpen(true)} data-tour="issues">
          {counts.error > 0 && <span className="dot error" aria-hidden="true" />}Issues <span className="count">{counts.all}</span></button>}
        {ws && !busy ? <Diagram ws={ws} focus={focus} selWire={selWire} onCard={openCard} /> : <DiagramSkeleton />}
      </main>
    </div>
    <Wires wires={ws?.conductors ?? null} open={wiresOpen} loading={busy} sel={selWire} onPick={pickWire}
           onToggle={() => setWiresOpen((o) => { if (!o) act("wires-open"); return !o; })} />
    {card && <Dialog title={card.name || card.id} onClose={closeCard} tour="card">
      <p className="card-kind"><span className="kind-chip">{card.kind}</span><span className="faint">{card.id} · {card.pins} pins</span></p></Dialog>}
    {filePicker}{overlays}
  </div>;
}

function Start({ session, onExample, onRecent, onPick }: { session: Session; onExample: () => void; onRecent: (p: string) => void; onPick: () => void }) {
  return <div className="start">
    <div className="start-col">
      <Logo size={40} />
      <h1>schemagen</h1>
      <p className="lede">Drop your wire sheet to see the whole system as one diagram, and what is wrong with it.</p>
      <button className="btn primary lg" onClick={onExample} autoFocus>Open the example project</button>
      <div className="or" aria-hidden="true"><span>or</span></div>
      <div className="dropzone" onClick={onPick} role="button" tabIndex={0} aria-label="Import your wire sheet (.xlsx or .csv)"
           onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}>
        <Glyph name="upload" size={20} />
        <strong>Import your wire sheet</strong>
        <span>Drop an .xlsx or .csv file here, or <u>choose a file</u></span>
      </div>
      {session.recent.length > 0 && <section className="recent" aria-labelledby="recent-h">
        <h2 id="recent-h">Recent</h2>
        <ul>{session.recent.map((r) => <li key={r.path}><button onClick={() => onRecent(r.path)} title={r.path}>
          <Glyph name="file" /><span className="r-name">{r.name}</span><span className="r-path">{r.path}</span><span className="r-date">{ago(r.opened)}</span>
        </button></li>)}</ul>
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
