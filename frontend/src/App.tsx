import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Button, HotkeysProvider, Icon, IconName, useHotkeys } from "@blueprintjs/core";
import { api, Derived, Index } from "./data";
import { WireTable } from "./views/WireTable";
import { ObjectPage } from "./views/ObjectPage";
import { Issues } from "./views/Issues";
import { Graph } from "./views/Graph";
import { Drawings } from "./views/Drawings";
import { Sim } from "./views/Sim";
import { DiffView } from "./views/Diff";
import { Search } from "./views/Search";
import { Navigator } from "./views/Navigator";
import { Inspector } from "./views/Inspector";
import { Problems } from "./views/Problems";

export interface Sel { type: string; id: string }
interface Ctx {
  ix: Index; d: Derived; net: string; highlight: (net: string) => void;
  setIndex: (ix: Index) => void; toast: (m: string) => void; sel: Sel | null; select: (s: Sel | null) => void;
}
const C = createContext<Ctx | null>(null);
export const useApp = () => useContext(C)!;

export const NAV: [string, string, IconName][] = [["table", "Wires", "th"], ["issues", "Issues", "warning-sign"], ["graph", "System graph", "graph"],
  ["drawings", "Drawings", "media"], ["sim", "Simulation", "lightning"], ["diff", "Changes & diff", "history"]];
const PANELS = "schemagen.panels";
type Panels = { nav: boolean; insp: boolean; prob: boolean };

function useHash(): string {
  const [h, setH] = useState(location.hash || "#/table");
  useEffect(() => { const f = () => setH(location.hash || "#/table"); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return h;
}

function loadPanels(): Panels {
  try { return { nav: true, insp: true, prob: true, ...JSON.parse(localStorage.getItem(PANELS) || "{}") }; } catch { return { nav: true, insp: true, prob: true }; }
}

function useDark(theme: string): boolean {
  const q = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null;
  const [sys, setSys] = useState(!!q?.matches);
  useEffect(() => { if (!q) return; const f = () => setSys(q.matches); q.addEventListener("change", f); return () => q.removeEventListener("change", f); }, [q]);
  return theme === "dark" || (theme === "auto" && sys);
}

export function App() {
  return <HotkeysProvider><Shell /></HotkeysProvider>;
}

function Shell() {
  const [ix, setIx] = useState<Index | null>(null);
  const [err, setErr] = useState("");
  const [net, setNet] = useState("");
  const [msg, setMsg] = useState("");
  const [sel, select] = useState<Sel | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [panels, setPanels] = useState<Panels>(loadPanels);
  const [theme, setTheme] = useState<string>(() => { try { return localStorage.getItem("sg-theme") || "auto"; } catch { return "auto"; } });
  const dark = useDark(theme);
  const hash = useHash();

  useEffect(() => { api<Index>("/api/index").then(setIx).catch((e) => setErr(String(e))); }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.body.classList.toggle("bp5-dark", dark);
    try { localStorage.setItem("sg-theme", theme); } catch { /* storage blocked */ }
  }, [theme, dark]);
  const toggle = useCallback((k: keyof Panels) => setPanels((p) => {
    const n = { ...p, [k]: !p[k] };
    try { localStorage.setItem(PANELS, JSON.stringify(n)); } catch { /* storage blocked: lasts for this page */ }
    return n;
  }), []);
  const cycleTheme = useCallback(() => setTheme((t) => (t === "auto" ? "light" : t === "light" ? "dark" : "auto")), []);
  const hotkeys = useMemo(() => [
    { combo: "mod+k", global: true, allowInInput: true, label: "Open the Omnibar", preventDefault: true, onKeyDown: () => setSearchOpen(true) },
    ...NAV.map(([k, t], i) => ({ combo: `alt+${i + 1}`, global: true, label: `Go to ${t}`, onKeyDown: () => { location.hash = `#/${k}`; } })),
    { combo: "[", global: true, label: "Show or hide the navigator", onKeyDown: () => toggle("nav") },
    { combo: "]", global: true, label: "Show or hide the inspector", onKeyDown: () => toggle("insp") },
    { combo: "shift+p", global: true, label: "Show or hide the problems panel", onKeyDown: () => toggle("prob") },
    { combo: "shift+t", global: true, label: "Next theme (auto, light, dark)", onKeyDown: cycleTheme },
  ], [toggle, cycleTheme]);
  const { handleKeyDown, handleKeyUp } = useHotkeys(hotkeys);
  useEffect(() => {
    addEventListener("keydown", handleKeyDown as unknown as EventListener); addEventListener("keyup", handleKeyUp as unknown as EventListener);
    return () => { removeEventListener("keydown", handleKeyDown as unknown as EventListener); removeEventListener("keyup", handleKeyUp as unknown as EventListener); };
  }, [handleKeyDown, handleKeyUp]);
  const d = useMemo(() => (ix ? new Derived(ix) : null), [ix]);
  const highlight = useCallback((n: string) => {
    const t0 = performance.now();
    setNet((cur) => (cur === n ? "" : n));
    // two frames: the highlight is painted when the second one runs
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const ms = performance.now() - t0;
      (window as unknown as { __lastHighlightMs: number }).__lastHighlightMs = ms;
      document.body.dataset.highlightMs = ms.toFixed(1);
    }));
  }, []);
  const toast = useCallback((m: string) => { setMsg(m); setTimeout(() => setMsg(""), 4000); }, []);
  const commands = useMemo(() => [
    ...NAV.map(([k, t]) => ({ title: `Go to ${t}`, run: () => { location.hash = `#/${k}`; } })),
    { title: "Show or hide the navigator", run: () => toggle("nav") },
    { title: "Show or hide the inspector", run: () => toggle("insp") },
    { title: "Show or hide the problems panel", run: () => toggle("prob") },
    { title: "Theme: next (auto, light, dark)", run: cycleTheme },
  ], [toggle, cycleTheme]);

  if (err) return <main className="center"><h1>schemagen</h1><p role="alert">Could not load the project: {err}</p></main>;
  if (!ix || !d) return <main className="center" aria-busy="true"><p>Loading project…</p></main>;
  const [, view, ...rest] = hash.slice(1).split("/");
  let body;
  if (view === "object") body = <ObjectPage type={rest[0]} id={decodeURIComponent(rest.slice(1).join("/"))} />;
  else if (view === "issues") body = <Issues />;
  else if (view === "graph") body = <Graph />;
  else if (view === "drawings") body = <Drawings />;
  else if (view === "sim") body = <Sim />;
  else if (view === "diff") body = <DiffView />;
  else body = <WireTable />;
  const errors = ix.issues.filter((i) => i.severity === "error").length;
  const cls = ["shell", panels.nav ? "" : "no-nav", panels.insp ? "" : "no-insp"].join(" ");
  return (
    <C.Provider value={{ ix, d, net, highlight, setIndex: setIx, toast, sel, select }}>
      <div className={cls}>
        <header className="top">
          <a className="brand" href="#/table">schemagen</a>
          <span className="proj" title={ix.project.root}>{ix.project.name}</span>
          <button className="search-btn" onClick={() => setSearchOpen(true)} aria-label="Omnibar: search and commands (Ctrl+K)">
            <Icon icon="search" size={14} /> Search or run a command <kbd>Ctrl K</kbd></button>
          <label className="theme">Theme{" "}
            <select value={theme} onChange={(e) => setTheme(e.target.value)} aria-label="Theme">
              <option value="auto">auto</option><option value="light">light</option><option value="dark">dark</option>
            </select>
          </label>
        </header>
        <nav className="rail" aria-label="Views">
          {NAV.map(([k, t, icon], i) => (
            <a key={k} href={`#/${k}`} aria-label={t} title={`${t} (Alt+${i + 1})`}
               aria-current={view === k || (!view && k === "table") ? "page" : undefined}>
              <Icon icon={icon} size={18} />
              {k === "issues" && errors ? <span className="badge error">{errors}</span> : null}
            </a>))}
          <span className="grow" />
          <Button minimal icon="list-detail-view" aria-label="Show or hide the navigator ([)" aria-pressed={panels.nav} onClick={() => toggle("nav")} />
          <Button minimal icon="panel-stats" aria-label="Show or hide the inspector (])" aria-pressed={panels.insp} onClick={() => toggle("insp")} />
          <Button minimal icon="console" aria-label="Show or hide the problems panel (Shift+P)" aria-pressed={panels.prob} onClick={() => toggle("prob")} />
        </nav>
        {panels.nav ? <Navigator /> : null}
        <div className="canvas">
          {net ? <div className="netbar" role="status">Net <a href={`#/object/net/${encodeURIComponent(net)}`}>{d.netById.get(net)?.name || net}</a> highlighted
            ({d.netById.get(net)?.c.length} wires) <button onClick={() => highlight(net)}>clear</button></div> : null}
          <main id="main">{body}</main>
          {panels.prob ? <Problems /> : null}
        </div>
        {panels.insp ? <Inspector /> : null}
      </div>
      {searchOpen ? <Search onClose={() => setSearchOpen(false)} commands={commands} /> : null}
      {msg ? <div className="toast" role="status">{msg}</div> : null}
    </C.Provider>
  );
}
