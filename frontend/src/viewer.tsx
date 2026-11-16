// The wiring diagram viewer: the sheets of one scope drawn by schemagen's engine (GET /api/diagram), always on white paper,
// with wheel zoom, drag pan, Fit and Sheet n of m. "Save as PDF" writes the same drawing as a PDF (POST /api/export).
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Failed, useCard } from "./cards";
import { SkeletonRows } from "./panels";
import type { DiagramSheets } from "./types";
import { Dialog, Glyph } from "./ui";

const PX = 96 / 25.4;   // the sheets are in mm
type View = { x: number; y: number; k: number };

/** One sheet on a pannable, zoomable stage: the wheel zooms at the pointer, a drag pans, `fit` is the first view. */
function Stage({ html }: { html: string }) {
  const [w, h] = (/viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(html) ?? [, "420", "297"]).slice(1).map((v) => Number(v) * PX);
  const box = useRef<HTMLDivElement>(null), drag = useRef<{ x: number; y: number } | null>(null);
  const [v, setV] = useState<View>({ x: 0, y: 0, k: 1 });
  const fit = () => {
    const el = box.current!, k = Math.min(el.clientWidth / w, el.clientHeight / h) * 0.97;
    setV({ k, x: (el.clientWidth - w * k) / 2, y: (el.clientHeight - h * k) / 2 });
  };
  useLayoutEffect(fit, [html]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {   // a native listener: React's wheel handler is passive and could not stop the page from scrolling
    const el = box.current!;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      setV((o) => { const k = Math.min(12, Math.max(0.05, o.k * Math.exp(-e.deltaY * 0.0015))); return { k, x: mx - (mx - o.x) * k / o.k, y: my - (my - o.y) * k / o.k }; });
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, []);
  return <div className="vw-stage" ref={box} data-testid="vw-stage"
    onPointerDown={(e) => { if ((e.target as HTMLElement).closest("button")) return; drag.current = { x: e.clientX, y: e.clientY }; e.currentTarget.setPointerCapture(e.pointerId); }}
    onPointerMove={(e) => { const d = drag.current; if (!d) return; drag.current = { x: e.clientX, y: e.clientY }; setV((o) => ({ ...o, x: o.x + e.clientX - d.x, y: o.y + e.clientY - d.y })); }}
    onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
    <div className="vw-paper" style={{ width: w, height: h, transform: `translate(${v.x}px, ${v.y}px) scale(${v.k})` }} dangerouslySetInnerHTML={{ __html: html }} />
    <button className="btn vw-fit" onClick={fit} title="Fit the sheet to the window">Fit</button>
  </div>;
}

export function DiagramViewer({ scope, onClose, onSave }: { scope: string; onClose: () => void; onSave: () => void }) {
  const [d, err, reload] = useCard<DiagramSheets>(`/api/diagram?scope=${encodeURIComponent(scope)}`);
  const [n, setN] = useState(0);
  const last = d ? d.sheets.length - 1 : 0;
  return <Dialog className="viewer-dialog" tour="viewer" onClose={onClose}
    title={d ? d.title : <span className="skeleton" style={{ width: 200, height: 16, display: "inline-block", verticalAlign: "middle" }} />}
    footer={<><span className="spacer" /><button className="btn btn-primary" onClick={onSave} disabled={!d}>Save as PDF</button></>}>
    {err ? <div className="vw-msg"><Failed err={err} retry={reload} /></div>
      : !d ? <div className="vw-msg" aria-busy="true"><SkeletonRows n={6} tall /></div>
      : <>
        <Stage html={d.sheets[Math.min(n, last)]} />
        {d.sheets.length > 1 && <div className="vw-sheets" role="group" aria-label="Sheets">
          <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setN(Math.max(0, n - 1))} disabled={n === 0} aria-label="Previous sheet"><Glyph name="left" /></button>
          <span role="status">Sheet {n + 1} of {d.sheets.length}</span>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setN(Math.min(last, n + 1))} disabled={n === last} aria-label="Next sheet"><Glyph name="right" /></button>
        </div>}
      </>}
  </Dialog>;
}
