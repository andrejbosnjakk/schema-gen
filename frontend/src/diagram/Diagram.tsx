// The block diagram: every component a card, wires bundled per component pair, zones as soft regions.
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EdgeLabelRenderer, Handle, Position, ReactFlow, ReactFlowProvider, useNodesState, useReactFlow, useStore,
  type EdgeProps, type Node as RFNode, type Edge as RFEdge, type NodeProps, type NodeChange } from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { KindIcon } from "../theme/icons";
import { act, post } from "../api";
import type { Node, Workspace } from "../types";
import { at, CH, CW, layout, placeLabels, regions, rounded, route } from "./layout";
import { drawn, useTheme } from "./colour";
import { Glyph } from "../ui";

type CardData = { n: Node; hl?: boolean; pulse?: boolean; first?: boolean };
const FIT = { top: "12px", left: "12px", bottom: "12px", right: "64px" } as const;  // room for the zoom buttons on the right
const NEAR = 0.9;  // below this zoom bundle labels are hidden (they would be unreadable)
type ZoneData = { name: string; w: number; h: number };
type EdgeData = { label: string; n: number; colour: string; ground: boolean; t: number | null; hl?: boolean; dim?: boolean };

const Card = memo(({ data }: NodeProps<RFNode<CardData>>) => {
  const { n } = data;
  return (
    <div className={`card node-card${data.hl ? " hl" : ""}${data.pulse ? " anim-pulse" : ""}`} title={`${n.name} (${n.id}) · ${n.kind} · ${n.pins} ${n.pins === 1 ? "pin" : "pins"}`} style={{ width: CW, height: CH }} data-tour-node={n.id} data-tour={data.first ? "node" : undefined}>
      <Handle type="target" position={Position.Left} isConnectable={false} className="port" />
      <span className="card-icon"><KindIcon kind={n.kind} /></span>
      <span className="card-name">{n.name || n.id}</span>
      {n.sev && <span className={`dot ${n.sev}`} role="img" aria-label={n.sev === "error" ? "has errors" : n.sev === "warning" ? "has warnings" : "has notes"} />}
      <Handle type="source" position={Position.Right} isConnectable={false} className="port" />
    </div>);
});

const ZoneBox = memo(({ data }: NodeProps<RFNode<ZoneData>>) => (
  <div className="zone" style={{ width: data.w, height: data.h }}><span className="zone-name">{data.name}</span></div>));

const Bundle = memo(({ id, sourceX, sourceY, targetX, targetY, data }: EdgeProps<RFEdge<EdgeData>>) => {
  const [hover, setHover] = useState(false);
  const d = data!, c = route(sourceX, sourceY, targetX, targetY), path = rounded(c);
  const show = d.t !== null || hover || d.hl, m = at(c, d.t ?? 0.5);
  const w = 1.25 + Math.min(3, Math.log2(d.n)) * 0.7;
  return <>
    <g className="bundle-g" style={{ "--c": d.colour, "--w": w } as React.CSSProperties}>
      <path d={path} className={`bundle${d.ground ? " ground" : ""}${d.hl ? " hl" : ""}${d.dim ? " dim" : ""}`} />
      <path d={path} className="bundle-hit" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} />
    </g>
    {show && <EdgeLabelRenderer>
      <div className={`elabel${d.t === null || hover || d.hl ? " pinned" : ""}${d.dim ? " dim" : ""}`} data-edge={id}
           style={{ transform: `translate(-50%, -50%) translate(${m.x}px, ${m.y}px)` }}>{d.label}</div>
    </EdgeLabelRenderer>}
  </>;
});

const NODE_TYPES = { card: Card, zone: ZoneBox };
const EDGE_TYPES = { bundle: Bundle };

/** Labels go quiet when zoomed out: one subscription toggles an attribute, no re-render of the edges. */
function ZoomFlag({ host }: { host: React.RefObject<HTMLDivElement> }) {
  const far = useStore((s) => s.transform[2] < NEAR);
  useEffect(() => { host.current?.toggleAttribute("data-far", far); }, [far, host]);
  return null;
}

export interface Focus { ids: string[]; wire?: string; nonce: number }
interface Props { ws: Workspace; focus: Focus | null; selWire: string | null; onCard: (n: Node) => void }

function Flow({ ws, focus, selWire, onCard }: Props) {
  const rf = useReactFlow();
  const host = useRef<HTMLDivElement>(null);
  const theme = useTheme();
  const comp = useMemo(() => new Map(ws.components.map((n) => [n.id, n])), [ws]);
  const view = useRef({ w: Math.max(480, innerWidth - 300), h: Math.max(240, innerHeight - 48 - Math.min(0.26 * innerHeight, 200)) });  // the canvas as first shown: steers the packing
  const auto = useMemo(() => layout(ws.components, ws.edges, ws.zones, view.current), [ws]);
  const base = useMemo(() => {
    const p = new Map(auto);
    for (const [id, xy] of Object.entries(ws.positions)) if (p.has(id)) p.set(id, { x: xy[0], y: xy[1] });
    return p;
  }, [auto, ws.positions]);
  const [pos, setPos] = useState(base), [seen, setSeen] = useState(base);
  if (seen !== base) { setSeen(base); setPos(base); }  // a new project or layout: start from it

  const firstId = ws.components.length ? [...auto].sort((a, b) => a[1].x - b[1].x || a[1].y - b[1].y)[0][0] : "";
  const [cards, setCards, onCardsChange] = useNodesState<RFNode<CardData>>([]);
  useEffect(() => {
    setCards(ws.components.filter((n) => base.has(n.id)).map((n) => ({ id: n.id, type: "card", position: base.get(n.id)!, data: { n, first: n.id === firstId },
      width: CW, height: CH, draggable: true, selectable: false, ariaLabel: `${n.name}, ${n.kind}` })));
    // only when the project or the stored layout changes; drags move cards through onNodesChange
  }, [base]);  // eslint-disable-line react-hooks/exhaustive-deps

  // stored positions and labels update when a drag ends (never per frame)
  const zones = useMemo(() => regions(ws.zones, pos), [ws.zones, pos]);
  const labels = useMemo(() => placeLabels(ws.edges, pos, zones), [ws.edges, pos, zones]);
  const pending = useRef<Record<string, [number, number]>>({});
  const timer = useRef<number>();
  const onDragStop = useCallback((_: unknown, _n: RFNode, moved: RFNode[]) => {
    setPos((p) => { const q = new Map(p); for (const m of moved) q.set(m.id, { ...m.position }); return q; });
    for (const m of moved) pending.current[m.id] = [Math.round(m.position.x), Math.round(m.position.y)];
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { const positions = pending.current; pending.current = {}; post("/api/positions", { positions }).catch(() => { /* view state only */ }); }, 600);
  }, []);

  const [hoverNode, setHoverNode] = useState<string | null>(null);
  // highlight: the selected wire's bundle and its two cards; pulse on the focused cards
  const wireEdge = useMemo(() => { const m = new Map<string, string>(); for (const e of ws.edges) for (const w of e.wires) m.set(w, e.id); return m; }, [ws.edges]);
  const hlEdge = selWire ? wireEdge.get(selWire) ?? null : null;
  const hlNodes = useMemo(() => { const e = ws.edges.find((x) => x.id === hlEdge); return new Set(e ? [e.a, e.b] : []); }, [hlEdge, ws.edges]);
  const near = useMemo(() => new Set(hoverNode ? ws.edges.filter((e) => e.a === hoverNode || e.b === hoverNode).map((e) => e.id) : []), [hoverNode, ws.edges]);  // bundles of the hovered card
  const [pulse, setPulse] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!focus) return;
    const ids = focus.ids.filter((id) => comp.has(id));
    if (!ids.length) return;
    rf.fitView({ nodes: ids.map((id) => ({ id })), duration: 450, padding: 0.5, maxZoom: 1.1 });
    setPulse(new Set(ids));
    const t = setTimeout(() => setPulse(new Set()), 1700);
    return () => clearTimeout(t);
  }, [focus]);  // eslint-disable-line react-hooks/exhaustive-deps

  const nodes = useMemo(() => {
    const zs: RFNode[] = zones.map((z) => ({ id: `zone:${z.id}`, type: "zone", position: { x: z.x, y: z.y }, data: { name: z.name, w: z.w, h: z.h },
      width: z.w, height: z.h, draggable: false, selectable: false, focusable: false, zIndex: -1, className: "zone-node" }));
    const cs = cards.map((c) => (hlNodes.has(c.id) || pulse.has(c.id) ? { ...c, data: { ...c.data, hl: hlNodes.has(c.id), pulse: pulse.has(c.id) } } : c));
    return [...zs, ...cs] as RFNode[];
  }, [zones, cards, hlNodes, pulse]);

  const edges = useMemo<RFEdge<EdgeData>[]>(() => ws.edges.filter((e) => comp.has(e.a) && comp.has(e.b)).map((e) => {
    const main = e.cls.find((c) => c !== "GND") ?? e.cls[0] ?? "";
    const on = e.id === hlEdge || near.has(e.id), any = !!hlEdge || near.size > 0;
    return { id: e.id, source: e.a, target: e.b, type: "bundle", focusable: false, selectable: false,
      data: { label: e.label, n: e.wires.length, colour: drawn(ws.palette[main] ?? "", "--canvas", theme), ground: main === "GND", t: labels.get(e.id) ?? null, hl: on, dim: any && !on } };
  }), [ws, comp, labels, hlEdge, near, theme]);

  const onChange = useCallback((ch: NodeChange<RFNode<CardData>>[]) => onCardsChange(ch.filter((c) => !("id" in c) || !String(c.id).startsWith("zone:"))), [onCardsChange]);
  const moved = useRef(0);

  return (
    <div className="flow" ref={host} data-tour="diagram" role="region" aria-label="System diagram: components left to right in power order">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} edgeTypes={EDGE_TYPES} onNodesChange={onChange as never}
        onNodeDragStop={onDragStop} onNodeMouseEnter={(_, n) => { if (n.type === "card") setHoverNode(n.id); }} onNodeMouseLeave={() => setHoverNode(null)} onNodeClick={(_, n) => { if (n.type === "card") onCard((n.data as CardData).n); }}
        onMoveEnd={(e) => { if (e && Date.now() - moved.current > 400) { moved.current = Date.now(); act("zoom"); } }}
        fitView fitViewOptions={{ padding: FIT }} minZoom={0.05} maxZoom={2} onlyRenderVisibleElements nodesConnectable={false}
        elementsSelectable={false} zoomOnDoubleClick={false} proOptions={{ hideAttribution: false }}>
        <ZoomFlag host={host} />
      </ReactFlow>
      <div className="zoom-controls" role="group" aria-label="Zoom">
        <button className="btn btn-ghost btn-icon" onClick={() => rf.zoomIn({ duration: 200 })} aria-label="Zoom in" title="Zoom in"><Glyph name="plus" /></button>
        <button className="btn btn-ghost btn-icon" onClick={() => rf.zoomOut({ duration: 200 })} aria-label="Zoom out" title="Zoom out"><Glyph name="minus" /></button>
        <button className="btn btn-ghost btn-icon" data-tour="fit" onClick={() => { rf.fitView({ duration: 450, padding: FIT }); act("zoom"); }} aria-label="Fit to screen" title="Fit to screen"><Glyph name="fit" /></button>
      </div>
    </div>);
}

/** The wire colours in use, for the drawer header. */
export function Legend({ palette, used }: { palette: Record<string, string>; used: string[] }) {
  const theme = useTheme();
  const seen = new Map<string, string>();
  for (const c of used) { const k = c.startsWith("CAN") ? "CAN" : c; if (!seen.has(k) && palette[c]) seen.set(k, palette[c]); }
  return <ul className="legend" aria-label="Wire colours">
    {[...seen].map(([k, hex]) => <li key={k}><span className="swatch" style={{ "--c": drawn(hex, "--surface", theme) } as React.CSSProperties} />{k}</li>)}
  </ul>;
}

export function Diagram(p: Props) { return <ReactFlowProvider><Flow {...p} /></ReactFlowProvider>; }
