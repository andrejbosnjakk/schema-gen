import { useEffect, useRef, useState } from "react";
import { useApp } from "../App";
import { api, href } from "../data";

export function Drawings() {
  const { d, net, highlight, toast } = useApp();
  const [list, setList] = useState<{ name: string }[] | null>(null);
  const [cur, setCur] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { api<{ name: string }[]>("/api/drawings").then((l) => { setList(l); if (l.length) setCur(l[0].name); }); }, []);
  const byLabel = useRef(new Map<string, string>());
  useEffect(() => { byLabel.current = new Map(d.ix.conductors.map((c) => [c.label, c.id])); }, [d]);
  useEffect(() => {
    if (!cur || !box.current) return;
    fetch(`/api/drawing/${encodeURIComponent(cur)}`).then((r) => r.text()).then((svg) => {
      const el = box.current!;
      el.innerHTML = svg.replace(/^[\s\S]*?(<svg)/, "$1");
      // wire labels are drawn as "RD:L05 · 20": make them clickable
      el.querySelectorAll("text").forEach((t) => {
        const m = /(?:^|:)([^:\s]+) · /.exec(t.textContent || "") || /(?:^|:)([^:\s]+)$/.exec(t.textContent || "");
        const id = m ? byLabel.current.get(m[1]) : undefined;
        if (!id) return;
        t.classList.add("wire"); t.dataset.id = id; t.setAttribute("role", "link"); t.setAttribute("tabindex", "0");
        t.addEventListener("click", () => { const c = d.byId.get(id)!; highlight(c.net); });
        t.addEventListener("dblclick", () => { location.hash = href("conductor", id); });
      });
      mark();
    });
  }, [cur]); // eslint-disable-line
  const mark = () => {
    const el = box.current; if (!el) return;
    const n = net ? new Set(d.netById.get(net)?.c.map((i) => d.ix.conductors[i].id)) : new Set<string>();
    el.querySelectorAll<SVGTextElement>("text.wire").forEach((t) => t.classList.toggle("hl", n.has(t.dataset.id || "")));
  };
  useEffect(mark, [net, d]); // eslint-disable-line
  const render = async () => {
    setBusy(true);
    try { const l = await api<{ name: string }[]>("/api/drawings/render", { method: "POST", body: "{}" }); setList(l); if (l.length) setCur(l[0].name); toast(`${l.length} drawings`); }
    catch (e) { toast(`render failed: ${e}`); } finally { setBusy(false); }
  };
  return (
    <section className="drawings">
      <div className="toolbar"><h1>Drawings</h1>
        {list && list.length ? <label>Drawing <select value={cur} onChange={(e) => setCur(e.target.value)} aria-label="Drawing">
          {list.map((x) => <option key={x.name}>{x.name}</option>)}</select></label> : null}
        <button onClick={render} disabled={busy}>{busy ? "Rendering…" : "Render drawings"}</button>
        <span className="muted">click a wire label to highlight its net, double-click to open the wire</span></div>
      {list && !list.length ? <p>No drawings yet. Render them (needs WireViz and Graphviz on this machine).</p> : null}
      <div ref={box} className="svgbox" data-testid="drawing" />
    </section>
  );
}
