import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { useApp } from "../App";
import { api, href, withCode } from "../data";

interface G { nodes: { id: string; kind: string; name: string }[]; edges: { a: string; b: string; w: number }[] }
const COL: Record<string, string> = { bus: "#c0392b", breaker: "#d68910", fuse: "#d68910", harness: "#2e86c1", battery: "#27ae60", dcdc: "#27ae60",
  controller: "#8e44ad", relay: "#7f8c8d", switch: "#7f8c8d" };

export function Graph() {
  const { d, net } = useApp();
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<cytoscape.Core | null>(null);
  const [g, setG] = useState<G | null>(null);
  const [kinds, setKinds] = useState<string>("main");
  useEffect(() => { api<G>("/api/graph").then(setG); }, []);
  useEffect(() => {
    if (!g || !box.current) return;
    const keep = (k: string) => kinds === "all" || ["bus", "breaker", "fuse", "harness", "battery", "dcdc", "controller"].includes(k);
    const ns = g.nodes.filter((n) => keep(n.kind));
    const ids = new Set(ns.map((n) => n.id));
    const dark = matchMedia("(prefers-color-scheme: dark)").matches && document.documentElement.dataset.theme !== "light" || document.documentElement.dataset.theme === "dark";
    const c = cytoscape({
      container: box.current,
      elements: [...ns.map((n) => ({ data: { id: n.id, label: withCode(n.name, n.id), kind: n.kind } })),
        ...g.edges.filter((e) => ids.has(e.a) && ids.has(e.b)).map((e) => ({ data: { id: `${e.a}~${e.b}`, source: e.a, target: e.b, w: e.w } }))],
      style: [
        { selector: "node", style: { label: "data(label)", "font-size": 10, color: dark ? "#eee" : "#111", "background-color": (n: cytoscape.NodeSingular) => COL[n.data("kind")] || "#95a5a6", width: 14, height: 14 } },
        { selector: "edge", style: { width: 1, "line-color": dark ? "#555" : "#bbb" } },
        { selector: ".hl", style: { "background-color": "#f1c40f", "border-width": 3, "border-color": "#000", width: 22, height: 22 } },
      ],
      layout: { name: ns.length > 300 ? "concentric" : "cose", animate: false } as cytoscape.LayoutOptions,
    });
    c.on("tap", "node", (e) => { const n = e.target.data(); location.hash = href(n.kind === "harness" ? "connector" : "component", n.id); });
    cy.current = c;
    return () => c.destroy();
  }, [g, kinds]);
  useEffect(() => {
    const c = cy.current; if (!c) return;
    c.nodes().removeClass("hl");
    const n = net ? d.netById.get(net) : null;
    if (n) for (const i of n.c) for (const e of [d.ix.conductors[i].f, d.ix.conductors[i].t]) c.getElementById(e[0]).addClass("hl");
  }, [net, d, g, kinds]);
  return (
    <section className="graph">
      <div className="toolbar"><h1>System graph</h1>
        <label>Show <select value={kinds} onChange={(e) => setKinds(e.target.value)} aria-label="Which components">
          <option value="main">buses, breakers, sources, controllers, harness connectors</option><option value="all">every component</option></select></label>
        <span className="muted">click a node to open it; a highlighted net is shown in yellow</span></div>
      <div ref={box} className="cy" role="img" aria-label="System graph of components, buses, breakers and harness connectors" />
    </section>
  );
}
