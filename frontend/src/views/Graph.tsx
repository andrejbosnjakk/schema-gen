import { memo, useEffect, useMemo, useState } from "react";
import { Background, Controls, Edge, Handle, MiniMap, Node, NodeProps, Position, ReactFlow } from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { Icon, IconName } from "@blueprintjs/core";
import "@xyflow/react/dist/style.css";
import { useApp } from "../App";
import { api, href, withCode } from "../data";

interface G { nodes: { id: string; kind: string; name: string }[]; edges: { a: string; b: string; w: number }[] }
type Card = { label: string; kind: string; code: string; hl: boolean };
const RANK: Record<string, number> = { battery: 0, dcdc: 0, bus: 1, breaker: 2, fuse: 2, harness: 3, relay: 3, switch: 3, controller: 4, device: 4 };
const ICON: Record<string, IconName> = { battery: "lightning", dcdc: "lightning", bus: "column-layout", breaker: "flash", fuse: "flash",
  harness: "inheritance", relay: "exchange", switch: "segmented-control", controller: "desktop", device: "box" };
const MAIN = ["bus", "breaker", "fuse", "harness", "battery", "dcdc", "controller"];
const W = 210, H = 52;
const KCOL: Record<string, string> = { bus: "#cd4246", breaker: "#c87619", fuse: "#c87619", harness: "#2d72d2", battery: "#238551", dcdc: "#238551", controller: "#7961db" };

const CardNode = memo(({ data }: NodeProps<Node<Card>>) => (
  <div className={`fcard k-${data.kind}${data.hl ? " hl" : ""}`}>
    <Handle type="target" position={Position.Left} />
    <div className="fcard-title"><Icon icon={ICON[data.kind] || "box"} size={14} /> <span>{data.label}</span></div>
    <div className="fcard-sub">{data.kind} · {data.code}</div>
    <Handle type="source" position={Position.Right} />
  </div>));
const TYPES = { card: CardNode };

/** dagre, left to right in power order (sources, buses, breakers, harness connectors and switching, loads). */
function layout(g: G, keep: (k: string) => boolean): { nodes: Node<Card>[]; edges: Edge[]; ms: number; crossings: number } {
  const t0 = performance.now();
  const ns = g.nodes.filter((n) => keep(n.kind));
  const ids = new Set(ns.map((n) => n.id));
  const kind = new Map(ns.map((n) => [n.id, n.kind]));
  const es = g.edges.filter((e) => ids.has(e.a) && ids.has(e.b)).map((e) =>
    (RANK[kind.get(e.a)!] ?? 4) <= (RANK[kind.get(e.b)!] ?? 4) ? e : { ...e, a: e.b, b: e.a });
  const dg = new dagre.graphlib.Graph();
  dg.setGraph({ rankdir: "LR", nodesep: 14, ranksep: 90, marginx: 20, marginy: 20, ranker: "tight-tree" });  // network-simplex takes minutes on 5k
  dg.setDefaultEdgeLabel(() => ({}));
  for (const n of ns) dg.setNode(n.id, { width: W, height: H });
  for (const e of es) dg.setEdge(e.a, e.b);
  dagre.layout(dg);
  const nodes: Node<Card>[] = ns.map((n) => {
    const p = dg.node(n.id);
    return { id: n.id, type: "card", position: { x: p.x - W / 2, y: p.y - H / 2 }, data: { label: withCode(n.name, n.id), kind: n.kind, code: n.id, hl: false } };
  });
  const edges: Edge[] = es.map((e) => ({ id: `${e.a}~${e.b}`, source: e.a, target: e.b, type: "smoothstep" }));
  // edge crossings of the straight segments between card ports (the layout metric)
  const pos = new Map(nodes.map((n) => [n.id, n.position]));
  const seg = es.map((e) => { const a = pos.get(e.a)!, b = pos.get(e.b)!; return [a.x + W, a.y + H / 2, b.x, b.y + H / 2, e.a, e.b] as const; });
  let crossings = 0;
  if (seg.length <= 4000) for (let i = 0; i < seg.length; i++) for (let j = i + 1; j < seg.length; j++) {
    const [ax, ay, bx, by, a1, b1] = seg[i], [cx, cy, dx, dy, a2, b2] = seg[j];
    if (a1 === a2 || a1 === b2 || b1 === a2 || b1 === b2) continue;
    const o = (px: number, py: number, qx: number, qy: number, rx: number, ry: number) => Math.sign((qx - px) * (ry - py) - (qy - py) * (rx - px));
    if (o(ax, ay, bx, by, cx, cy) * o(ax, ay, bx, by, dx, dy) < 0 && o(cx, cy, dx, dy, ax, ay) * o(cx, cy, dx, dy, bx, by) < 0) crossings++;
  }
  return { nodes, edges, ms: performance.now() - t0, crossings };
}

export function Graph() {
  const { d, net, select } = useApp();
  const [g, setG] = useState<G | null>(null);
  const [kinds, setKinds] = useState<string>("main");
  useEffect(() => { api<G>("/api/graph").then(setG); }, []);
  const lay = useMemo(() => (g ? layout(g, (k) => kinds === "all" || MAIN.includes(k)) : null), [g, kinds]);
  const on = useMemo(() => {
    const s = new Set<string>();
    const n = net ? d.netById.get(net) : null;
    if (n) for (const i of n.c) for (const e of [d.ix.conductors[i].f, d.ix.conductors[i].t]) s.add(e[0]);
    return s;
  }, [net, d]);
  const nodes = useMemo(() => lay?.nodes.map((n) => (on.has(n.id) ? { ...n, data: { ...n.data, hl: true } } : n)) ?? [], [lay, on]);
  return (
    <section className="graph" data-layout-ms={lay?.ms.toFixed(0)} data-crossings={lay?.crossings} data-nodes={lay?.nodes.length}>
      <div className="toolbar"><h1>System canvas <small>{lay ? `${lay.nodes.length} items, ${lay.edges.length} links` : ""}</small></h1>
        <label>Show <select value={kinds} onChange={(e) => setKinds(e.target.value)} aria-label="Which components">
          <option value="main">buses, breakers, sources, controllers, harness connectors</option><option value="all">every component</option></select></label>
        <span className="muted">click a card to inspect it, double-click to open it; a highlighted net is outlined</span></div>
      <div className="flow" aria-label="System canvas: components, buses, breakers and harness connectors, left to right in power order">
        {lay ? <ReactFlow key={kinds} nodes={nodes} edges={lay.edges} nodeTypes={TYPES} fitView minZoom={0.05} onlyRenderVisibleElements
                          nodesConnectable={false} nodesDraggable={false}
                          onNodeClick={(_, n) => select({ type: n.data.kind === "harness" ? "connector" : "component", id: n.id })}
                          onNodeDoubleClick={(_, n) => { location.hash = href(n.data.kind === "harness" ? "connector" : "component", n.id); }}>
          <Background gap={16} /><Controls showInteractive={false} /><MiniMap pannable zoomable ariaLabel="Overview" nodeColor={(n) => KCOL[(n.data as Card).kind] || "#8f99a8"} />
        </ReactFlow> : <p className="muted">Laying out…</p>}
      </div>
    </section>
  );
}
