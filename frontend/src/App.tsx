import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, Derived, Index } from "./data";
import { WireTable } from "./views/WireTable";
import { ObjectPage } from "./views/ObjectPage";
import { Issues } from "./views/Issues";
import { Graph } from "./views/Graph";
import { Drawings } from "./views/Drawings";
import { Sim } from "./views/Sim";
import { DiffView } from "./views/Diff";
import { Search } from "./views/Search";

interface Ctx {
  ix: Index; d: Derived; net: string; highlight: (net: string) => void;
  setIndex: (ix: Index) => void; toast: (m: string) => void;
}
const C = createContext<Ctx | null>(null);
export const useApp = () => useContext(C)!;

const NAV: [string, string][] = [["table", "Wires"], ["issues", "Issues"], ["graph", "System graph"], ["drawings", "Drawings"],
  ["sim", "Simulation"], ["diff", "Changes & diff"]];

function useHash(): string {
  const [h, setH] = useState(location.hash || "#/table");
  useEffect(() => { const f = () => setH(location.hash || "#/table"); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return h;
}

export function App() {
  const [ix, setIx] = useState<Index | null>(null);
  const [err, setErr] = useState("");
  const [net, setNet] = useState("");
  const [msg, setMsg] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [theme, setTheme] = useState<string>(() => localStorage.getItem("sg-theme") || "auto");
  const hash = useHash();

  useEffect(() => { api<Index>("/api/index").then(setIx).catch((e) => setErr(String(e))); }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("sg-theme", theme);
  }, [theme]);
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen(true); }
      if (e.key === "Escape") setSearchOpen(false);
    };
    addEventListener("keydown", f); return () => removeEventListener("keydown", f);
  }, []);
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
  return (
    <C.Provider value={{ ix, d, net, highlight, setIndex: setIx, toast }}>
      <header className="top">
        <a className="brand" href="#/table">schemagen</a>
        <span className="proj" title={ix.project.root}>{ix.project.name}</span>
        <nav aria-label="Views">
          {NAV.map(([k, t]) => <a key={k} href={`#/${k}`} aria-current={view === k || (!view && k === "table") ? "page" : undefined}>
            {t}{k === "issues" && errors ? <span className="badge error">{errors}</span> : null}</a>)}
        </nav>
        <button className="search-btn" onClick={() => setSearchOpen(true)} aria-label="Search (Ctrl+K)">Search <kbd>Ctrl K</kbd></button>
        <label className="theme">Theme{" "}
          <select value={theme} onChange={(e) => setTheme(e.target.value)} aria-label="Theme">
            <option value="auto">auto</option><option value="light">light</option><option value="dark">dark</option>
          </select>
        </label>
      </header>
      {net ? <div className="netbar" role="status">Net <a href={`#/object/net/${encodeURIComponent(net)}`}>{d.netById.get(net)?.name || net}</a> highlighted
        ({d.netById.get(net)?.c.length} wires) <button onClick={() => highlight(net)}>clear</button></div> : null}
      <main id="main">{body}</main>
      {searchOpen ? <Search onClose={() => setSearchOpen(false)} /> : null}
      {msg ? <div className="toast" role="status">{msg}</div> : null}
    </C.Provider>
  );
}
