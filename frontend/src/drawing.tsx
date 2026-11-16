// The wiring drawing inside a card (docs/api.md, Drawing): one row per run, from the pin through each wire and everything it
// passes (harness connector pins, splices) to where it lands. A harness connector shows both halves around its pin.
// "Save as PDF" prints this sheet alone, with a title block.
import { createPortal } from "react-dom";
import { drawn, useTheme } from "./diagram/colour";
import type { CardTarget, Drawing as D, DrawingSeg } from "./types";

type Switch = (t: CardTarget) => void;

function Wire({ s, theme, onSwitch }: { s: DrawingSeg; theme: string; onSwitch?: Switch }) {
  const tip = [s.name, s.reason].filter(Boolean).join(": ");
  const text = <><strong>{s.label || s.wire}</strong>{s.gauge && <span>{s.gauge} AWG</span>}{s.colour && <span>{s.colour}</span>}</>;
  return <span className={`dw-wire${s.sev === "error" ? " bad" : s.sev === "warning" ? " warn" : ""}`} title={tip}>
    {onSwitch ? <button className="dw-label link" onClick={() => onSwitch({ type: "wire", id: s.wire })}>{text}</button> : <span className="dw-label">{text}</span>}
    <span className="dw-line" style={{ "--c": drawn(s.hex, "--surface", theme) } as React.CSSProperties} aria-hidden="true" />
    {s.name && <span className="dw-name">{s.name}</span>}
  </span>;
}

function Land({ s, onSwitch }: { s: DrawingSeg; onSwitch?: Switch }) {
  const via = s.role === "splice" || s.role === "harness";
  return onSwitch && s.comp && s.role !== "splice"
    ? <button className={`dw-at${via ? " via" : ""}`} onClick={() => onSwitch({ type: "component", id: s.comp })} title={`Open ${s.at}`}>{s.at}</button>
    : <span className={`dw-at${via ? " via" : ""}`}>{s.at}</span>;
}

/** The rows of a drawing; `onSwitch` makes wires and landings links (left out on the printed sheet). */
export function DrawingRows({ d, onSwitch }: { d: D; onSwitch?: Switch }) {
  const theme = useTheme();
  const harness = d.sides.length > 0;
  return <div className={`drawing pin-table${harness ? " both" : ""}`}>
    {harness && <div className="dw-sides" aria-hidden="true"><span>{d.sides[0]}</span><span>pin</span><span>{d.sides[1] ?? ""}</span></div>}
    {d.groups.map((g) => <section key={g.name} aria-label={g.name || d.name}>
      {g.name && <h3 className="dw-group">{g.name}</h3>}
      {g.rows.map((r, i) => {
        const same = i > 0 && g.rows[i - 1].pin === r.pin;   // a pin with several runs is named once
        return <div className="dw-row pin" key={i}>
          {harness && <span className="dw-left">{[...r.left].reverse().map((s, k) => <span className="dw-hop" key={k}><Land s={s} onSwitch={onSwitch} /><Wire s={s} theme={theme} onSwitch={onSwitch} /></span>)}</span>}
          <span className={`dw-pin${same ? " same" : ""}`}><strong>{r.pin}</strong>{r.pin_name && <span className="pin-sub">{r.pin_name}</span>}</span>
          <span className="dw-right">{r.right.map((s, k) => <span className="dw-hop" key={k}><Wire s={s} theme={theme} onSwitch={onSwitch} /><Land s={s} onSwitch={onSwitch} /></span>)}</span>
        </div>;
      })}
    </section>)}
    {d.groups.length === 0 && <p className="faint">No wires here.</p>}
    {d.cut > 0 && <p className="faint">{d.cut} more runs are not shown. The wiring checklist export has all of them.</p>}
  </div>;
}

/** The sheet that "Save as PDF" prints: hidden on screen, the only thing on paper. */
export function PrintSheet({ d }: { d: D }) {
  const title = d.to ? `${d.name} to ${d.to.name}` : d.name;
  return createPortal(<div className="print-sheet" data-theme="light">
    <header className="ps-head"><div><h1>{title}</h1><p>Wiring diagram · {d.wires} {d.wires === 1 ? "wire" : "wires"}</p></div>
      <div className="ps-block"><span>{d.project}</span><span>{new Date().toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</span><span>schemagen</span></div></header>
    <DrawingRows d={d} />
  </div>, document.body);
}
