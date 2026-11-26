// The block diagram: every component a card, wires bundled per component pair, zones as soft regions.
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EdgeLabelRenderer, Handle, Position, ReactFlow, ReactFlowProvider, useNodesState, useReactFlow, useStore,
  type EdgeProps, type Node as RFNode, type Edge as RFEdge, type NodeProps, type NodeChange } from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { KindIcon } from "../theme/icons";
import { act, post } from "../api";
import { voltText, type CardSim, useSim } from "../simulate";
import type { Node, Overlay, Workspace } from "../types";
import { at, CH, CW, layout, placeBeside, placeLabels, regions, rounded, route } from "./layout";
import { drawn, useTheme } from "./colour";
import { Glyph } from "../ui";

type CardData = { n: Node; hl?: boolean; pulse?: boolean; sel?: boolean; hint?: boolean; dim?: boolean; first?: boolean; sim?: CardSim };
const FIT = { top: "28px", left: "12px", bottom: "4px", right: "64px" } as const;  // room for + Source (top right) and the zoom buttons (right)
const NEAR = 0.9;  // below this zoom bundle labels are hidden (they would be unreadable)
type ZoneData = { name: string; w: number; h: number };
type EdgeData = { label: string; n: number; colour: string; ground: boolean; t: number | null; hl?: boolean; dim?: boolean; sim?: "warn" | "error"; pick?: (id: string, x: number, y: number) => void };

const Card = memo(({ data }: NodeProps<RFNode<CardData>>) => {
  const { n, sim } = data;
  return (
    <div className={`card node-card${data.hl ? " hl" : ""}${data.sel ? " sel" : ""}${data.hint ? " hint" : ""}${data.dim ? " dim" : ""}${data.pulse ? " anim-pulse" : ""}${sim?.status ? ` ring-${sim.status}` : ""}`} title={`${n.name} (${n.id}) · ${n.kind} · ${n.pins} ${n.pins === 1 ? "pin" : "pins"}`} style={{ width: CW, height: CH }} data-tour-node={n.id} data-tour={data.first ? "node" : undefined}>
      <Handle type="target" position={Position.Left} isConnectable={false} className="port" />
      <span className="card-icon"><KindIcon kind={n.kind} /></span>
      <span className="card-name">{n.name || n.id}</span>
      {sim?.volt && <span className={`v-badge${sim.volt.low ? " low" : ""}`}>{voltText(sim.volt.v)}</span>}
      {sim?.load && <span className={`load-bar${sim.load.f >= 1 ? " over" : sim.load.f >= 0.8 ? " near" : ""}`} role="img" aria-label={sim.load.text} title={sim.load.text}><span style={{ width: `${Math.min(100, Math.round(sim.load.f * 100))}%` }} /></span>}
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
  const w = 1.25 + Math.min(3, Math.log2(Math.max(1, d.n))) * 0.7;
  return <>
    <g className="bundle-g" style={{ "--c": d.colour, "--w": w } as React.CSSProperties}>
      <path d={path} className={`bundle${d.ground ? " ground" : ""}${d.hl ? " hl" : ""}${d.dim ? " dim" : ""}${d.sim ? ` sim-${d.sim}` : ""}`} />
      <path d={path} className="bundle-hit" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onClick={(e) => d.pick?.(id, e.clientX, e.clientY)} />
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
interface Props { ws: Workspace; focus: Focus | null; selWire: string | null; picked: string[]; onPick: (n: Node) => void; onCard: (n: Node) => void; onWire: (id: string) => void; onLink: (a: string, b: string) => void; onClear: () => void; overlay: { o: Overlay; stale: boolean } | null; picking: boolean }

function Flow({ ws, focus, selWire, picked, onPick, onCard, onWire, onLink, onClear, overlay, picking }: Props) {
  const rf = useReactFlow();
  const host = useRef<HTMLDivElement>(null);
  const theme = useTheme();
  const comp = useMemo(() => new Map(ws.components.map((n) => [n.id, n])), [ws]);
  const view = useRef({ w: Math.max(480, innerWidth - 300), h: Math.max(240, innerHeight - 48 - Math.min(0.26 * innerHeight, 200)) });  // the canvas as first shown: steers the packing
  const auto = useMemo(() => layout(ws.components, ws.edges, ws.zones, view.current), []);  // eslint-disable-line react-hooks/exhaustive-deps
  const [pos, setPos] = useState(() => {
    const p = new Map(auto);
    for (const [id, xy] of Object.entries(ws.positions)) if (p.has(id)) p.set(id, { x: xy[0], y: xy[1] });
    return p;
  });
  // an edit that adds or removes components (a source) keeps every position and the view; a new card goes next to what it is wired to
  const ids = ws.components.map((n) => n.id).join("|"), [seen, setSeen] = useState(ids);
  if (seen !== ids) {
    setSeen(ids);
    const q = new Map<string, { x: number; y: number }>();
    for (const n of ws.components) {
      const old = pos.get(n.id);
      if (old) { q.set(n.id, old); continue; }
      const e = ws.edges.find((x) => x.a === n.id || x.b === n.id), other = e && (e.a === n.id ? e.b : e.a), nb = other ? q.get(other) ?? pos.get(other) : undefined;
      const all = new Map([...pos, ...q]), own = ws.zones.find((z) => z.members.includes(other ?? ""))?.id;
      q.set(n.id, placeBeside(nb ?? { x: 0, y: 0 }, own, all, ws.edges, regions(ws.zones, all)));
    }
    setPos(q);
  }

  // adding or removing a card pins every position the user sees (the packing would otherwise come out different on reload and move the zones)
  const firstIds = useRef(ids);
  useEffect(() => {
    if (firstIds.current === ids) return;
    firstIds.current = ids;
    const positions: Record<string, [number, number] | null> = {};
    for (const n of ws.components) { const p = pos.get(n.id); if (p) positions[n.id] = [Math.round(p.x), Math.round(p.y)]; }
    for (const id of Object.keys(ws.positions)) if (!(id in positions)) positions[id] = null;
    post("/api/positions", { positions }).catch(() => { /* view state only */ });
  }, [ids]);  // eslint-disable-line react-hooks/exhaustive-deps

  // a card added by an edit that lands outside the view: bring it and what it is wired to into view (never zoomed in), so the new source is never off screen
  const known = useRef(new Set(ws.components.map((n) => n.id)));
  useEffect(() => {
    const added = ws.components.filter((n) => !known.current.has(n.id));
    known.current = new Set(ws.components.map((n) => n.id));
    const p = added.length ? pos.get(added[0].id) : null, el = host.current;
    if (!p || !el) return;
    const v = rf.getViewport(), x = p.x * v.zoom + v.x, y = p.y * v.zoom + v.y;
    if (x < 0 || y < 0 || x + CW * v.zoom > el.clientWidth - 64 || y + CH * v.zoom > el.clientHeight) {
      const e = ws.edges.find((e) => e.a === added[0].id || e.b === added[0].id);
      rf.fitView({ nodes: [{ id: added[0].id }, ...(e ? [{ id: e.a === added[0].id ? e.b : e.a }] : [])], duration: 450, padding: 0.4, maxZoom: v.zoom });
    }
  }, [ids]);  // eslint-disable-line react-hooks/exhaustive-deps

  const firstId = ws.components.length ? [...auto].sort((a, b) => a[1].x - b[1].x || a[1].y - b[1].y)[0][0] : "";
  const [cards, setCards, onCardsChange] = useNodesState<RFNode<CardData>>([]);
  useEffect(() => {
    // an edit gives new names and severities: the cards keep the position they have now (drags move them through onNodesChange)
    setCards((old) => { const at = new Map(old.map((c) => [c.id, c.position]));
      return ws.components.filter((n) => pos.has(n.id)).map((n) => ({ id: n.id, type: "card", position: at.get(n.id) ?? pos.get(n.id)!, data: { n, first: n.id === firstId },
        width: CW, height: CH, draggable: true, selectable: false, ariaLabel: `${n.name}, ${n.kind}` })); });
  }, [ws.components, ids]);  // eslint-disable-line react-hooks/exhaustive-deps

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
  // the hovered card's own lines, and its circuit: the power lines that feed it (back to the sources) and those it feeds
  const near = useMemo(() => {
    const out = new Set<string>();
    if (!hoverNode) return out;
    const power = (e: (typeof ws.edges)[number]) => e.cls.some((c) => /\d\s*V|HV/.test(c));
    for (const e of ws.edges) if (e.a === hoverNode || e.b === hoverNode) out.add(e.id);
    const walk = (n: string, up: boolean, seen: Set<string>) => {
      if (seen.has(n)) return;
      seen.add(n);
      for (const e of ws.edges) if (power(e) && (up ? e.b : e.a) === n) { out.add(e.id); walk(up ? e.a : e.b, up, seen); }
    };
    walk(hoverNode, true, new Set()); walk(hoverNode, false, new Set());
    return out;
  }, [hoverNode, ws.edges]);
  const [pulse, setPulse] = useState<Set<string>>(new Set());
  const sim = useSim(overlay?.o ?? null);
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
    const peers = new Set(picked.length ? ws.components.find((x) => x.id === picked[0])?.peers ?? [] : []);  // what shift-click may add to the first pick
    const cs = cards.map((c) => { const sm = sim.cards.get(c.id);
      const sel = picked.includes(c.id), hint = !sel && peers.has(c.id), dim = picked.length > 0 && !sel && !hint;
      return hlNodes.has(c.id) || pulse.has(c.id) || sel || hint || dim || sm ? { ...c, data: { ...c.data, hl: hlNodes.has(c.id), pulse: pulse.has(c.id), sel, hint, dim, sim: sm } } : c; });
    return [...zs, ...cs] as RFNode[];
  }, [zones, cards, hlNodes, pulse, picked, sim, ws.components]);

  // clicking a line opens the card of that connection (a single wire: the wire's card)
  const edgeOf = useRef(new Map<string, { a: string; b: string; wires: string[] }>());
  edgeOf.current = new Map(ws.edges.map((e) => [e.id, e]));
  const pickEdge = useCallback((id: string) => {
    const e = edgeOf.current.get(id);
    if (e?.wires.length === 1) onWire(e.wires[0]); else if (e) onLink(e.a, e.b);
  }, [onWire, onLink]);

  const edges = useMemo<RFEdge<EdgeData>[]>(() => ws.edges.filter((e) => comp.has(e.a) && comp.has(e.b)).map((e) => {
    const main = e.cls.find((c) => c !== "GND") ?? e.cls[0] ?? "";
    const on = e.id === hlEdge || near.has(e.id), any = !!hlEdge || near.size > 0;
    const st = e.wires.map((w) => sim.wires.get(w)), bad = st.includes("error") ? "error" : st.includes("warn") ? "warn" : undefined;
    return { id: e.id, source: e.a, target: e.b, type: "bundle", focusable: false, selectable: false,
      data: { label: e.label, n: e.wires.length, colour: drawn(ws.palette[main] ?? "", "--canvas", theme), ground: main === "GND", t: labels.get(e.id) ?? null, hl: on, dim: any && !on, sim: bad, pick: pickEdge } };
  }), [ws, comp, labels, hlEdge, near, theme, sim, pickEdge]);

  const onChange = useCallback((ch: NodeChange<RFNode<CardData>>[]) => onCardsChange(ch.filter((c) => !("id" in c) || !String(c.id).startsWith("zone:"))), [onCardsChange]);
  const moved = useRef(0);

  return (
    <div className={`flow${picking ? " picking" : ""}${overlay?.stale ? " stale" : ""}`} ref={host} data-tour="diagram" role="region" aria-label="System diagram">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} edgeTypes={EDGE_TYPES} onNodesChange={onChange as never}
        onNodeDragStop={onDragStop} onNodeMouseEnter={(_, n) => { if (n.type === "card") setHoverNode(n.id); }} onNodeMouseLeave={() => setHoverNode(null)} onNodeClick={(e, n) => { if (n.type !== "card") onClear(); else if (e.shiftKey) onPick((n.data as CardData).n); else onCard((n.data as CardData).n); }} onPaneClick={onClear}
        onMoveEnd={(e) => { if (e && Date.now() - moved.current > 400) { moved.current = Date.now(); act("zoom"); } }}
        fitView fitViewOptions={{ padding: FIT }} minZoom={0.05} maxZoom={2} onlyRenderVisibleElements nodesConnectable={false}
        elementsSelectable={false} selectionKeyCode={null} zoomOnDoubleClick={false} proOptions={{ hideAttribution: false }}>
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

export function Diagram(p: Props) { return <ReactFlowProvider><Flow key={p.ws.project.root} {...p} /></ReactFlowProvider>; }
