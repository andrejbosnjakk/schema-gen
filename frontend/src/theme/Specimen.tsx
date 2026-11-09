// Style sheet page for review (not wired into the app; may be mounted at #/specimen). Tokens and theme classes only.
import { useState, type CSSProperties, type ReactNode } from "react";
import { Icon, ICON_NAMES, KindIcon, KIND_NAMES, Logo } from "./icons";

const COLOURS = [
  ["bg", "canvas", "surface", "surface-2"], ["border", "border-strong", "text", "text-2", "text-3", "logo"],
  ["accent", "accent-hover", "accent-soft", "on-accent", "focus"],
  ["ok", "ok-soft", "warn", "warn-soft", "err", "err-soft"],
];
const TYPE: [string, string, string][] = [
  ["--fs-xl", "--fw-bold", "Main battery feed"], ["--fs-lg", "--fw-bold", "Power distribution"],
  ["--fs-md", "--fw-med", "Avionics bus, 14 V"], ["--fs", "--fw", "W-1042  20 AWG  Red  PDU J2-4 to ECU P1-7, 1.8 m"],
  ["--fs-sm", "--fw", "Secondary text: 3 connectors, 42 wires"], ["--fs-xs", "--fw-med", "CAPTION  11 PX"],
];

const row: CSSProperties = { display: "flex", alignItems: "center", gap: "var(--s1)", flexWrap: "wrap" };
const label: CSSProperties = { fontSize: "var(--fs-xs)", color: "var(--text-3)", fontWeight: "var(--fw-med)" as never, letterSpacing: "0.04em", textTransform: "uppercase" };

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section style={{ display: "grid", gap: "var(--s2)", padding: "var(--s3) 0", borderTop: "var(--border-w) solid var(--border)" }}>
    <h3>{title}</h3>{children}</section>;
}

function setTheme(t: string) { document.documentElement.dataset.theme = t; }

export default function Specimen() {
  const [theme, setT] = useState(document.documentElement.dataset.theme || "light");
  const toggle = () => { const t = theme === "dark" ? "light" : "dark"; setTheme(t); setT(t); };
  return <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
    <header style={{ ...row, height: 48, padding: "0 var(--s2)", borderBottom: "var(--border-w) solid var(--border)", position: "sticky", top: 0, background: "var(--bg)", zIndex: 1 }}>
      <Logo size={20} /><strong style={{ fontWeight: "var(--fw-bold)" as never }}>schemagen</strong>
      <span style={{ color: "var(--text-3)" }}>design system 1.0</span>
      <span style={{ flex: 1 }} />
      <button className="btn btn-ghost btn-icon" onClick={toggle} aria-label="Toggle theme"><Icon name={theme === "dark" ? "sun" : "moon"} /></button>
    </header>

    <main style={{ maxWidth: 1120, margin: "0 auto", padding: "var(--s1) var(--s3) var(--s6)" }}>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1fr)", gap: "0 var(--s6)" }}>
        <div>
          <Section title="Type: Inter, 13 px base">
            <div style={{ display: "grid", gap: "var(--s1)" }}>
              {TYPE.map(([fs, fw, t]) => <div key={fs} style={{ display: "grid", gridTemplateColumns: "72px 1fr", alignItems: "baseline", gap: "var(--s2)" }}>
                <span style={label}>{fs.slice(2)}</span>
                <span style={{ fontSize: `var(${fs})`, fontWeight: `var(${fw})` as never, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t}</span>
              </div>)}
            </div>
          </Section>

          <Section title="Colour">
            {COLOURS.map((g, i) => <div key={i} style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "var(--s1)" }}>
              {g.map((c) => <div key={c} style={{ display: "grid", gap: "var(--s-half)" }}>
                <div style={{ height: 36, borderRadius: "var(--radius)", background: `var(--${c})`, border: "var(--border-w) solid var(--border)" }} />
                <span style={{ fontSize: "var(--fs-xs)", color: "var(--text-2)" }}>--{c}</span>
              </div>)}
            </div>)}
          </Section>

          <Section title="Buttons">
            <div style={row}>
              <button className="btn btn-primary"><Icon name="play" />Simulate</button>
              <button className="btn"><Icon name="import" />Import sheet</button>
              <button className="btn btn-ghost"><Icon name="export" />Export</button>
              <button className="btn btn-danger">Delete wire</button>
              <button className="btn" disabled>Disabled</button>
            </div>
            <div style={row}>
              <button className="btn btn-primary btn-sm">Apply</button>
              <button className="btn btn-sm">Cancel</button>
              <span className="divider divider-v" />
              <button className="btn btn-ghost btn-icon" aria-label="Zoom in"><Icon name="zoom-in" /></button>
              <button className="btn btn-ghost btn-icon" aria-label="Zoom out"><Icon name="zoom-out" /></button>
              <button className="btn btn-ghost btn-icon" aria-label="Fit"><Icon name="fit" /></button>
              <button className="btn btn-icon" aria-label="Add"><Icon name="plus" /></button>
              <span className="divider divider-v" />
              <span style={{ color: "var(--text-2)" }}>Search <span className="kbd">Ctrl</span> <span className="kbd">K</span></span>
            </div>
          </Section>

          <Section title="Inputs">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--s2)" }}>
              <label style={{ display: "grid", gap: "var(--s-half)" }}><span style={{ color: "var(--text-2)", fontSize: "var(--fs-sm)" }}>Wire id</span>
                <input className="input" defaultValue="W-1042" /></label>
              <label style={{ display: "grid", gap: "var(--s-half)" }}><span style={{ color: "var(--text-2)", fontSize: "var(--fs-sm)" }}>Gauge</span>
                <select className="input" defaultValue="20"><option value="20">20 AWG</option><option>22 AWG</option></select></label>
              <label style={{ display: "grid", gap: "var(--s-half)" }}><span style={{ color: "var(--text-2)", fontSize: "var(--fs-sm)" }}>Length (m)</span>
                <input className="input" aria-invalid="true" defaultValue="-1.8" /></label>
              <label style={{ display: "grid", gap: "var(--s-half)" }}><span style={{ color: "var(--text-2)", fontSize: "var(--fs-sm)" }}>Search</span>
                <input className="input" placeholder="Find a device, wire or pin" /></label>
            </div>
          </Section>

          <Section title="Status">
            <div style={row}>
              <span className="badge badge-ok">Powered 14.1 V</span><span className="badge badge-warn">2 warnings</span>
              <span className="badge badge-err">Unpowered</span><span className="badge">Not simulated</span>
            </div>
            <div style={{ display: "grid", gap: "var(--s-half)", maxWidth: 360 }}>
              <span className="skeleton" style={{ height: 12, width: "70%" }} /><span className="skeleton" style={{ height: 12 }} />
              <span className="skeleton" style={{ height: 12, width: "40%" }} />
            </div>
          </Section>
        </div>

        <div>
          <Section title="Component card (diagram block)">
            <div style={{ background: "var(--canvas)", borderRadius: "var(--radius)", padding: "var(--s3)", display: "flex", gap: "var(--s3)", alignItems: "flex-start", border: "var(--border-w) solid var(--border)" }}>
              <div className="card" style={{ width: 220, padding: 0 }}>
                <div style={{ ...row, padding: "10px 12px", borderBottom: "var(--border-w) solid var(--border)" }}>
                  <span style={{ color: "var(--text-2)", display: "inline-flex" }}><KindIcon kind="battery" /></span>
                  <strong style={{ fontWeight: "var(--fw-med)" as never, flex: 1 }}>Main battery</strong>
                  <span className="badge badge-ok">14.1 V</span>
                </div>
                <div style={{ padding: "var(--s1) 12px", display: "grid", gap: 2, fontSize: "var(--fs-sm)", color: "var(--text-2)" }}>
                  <span>BAT+  to  PDU J1-1</span><span>BAT-  to  GND bus</span>
                </div>
              </div>
              <div className="card anim-pulse" style={{ width: 180, padding: 0, borderColor: "var(--accent)", boxShadow: "0 0 0 1px var(--accent)" }}>
                <div style={{ ...row, padding: "10px 12px" }}>
                  <span style={{ color: "var(--text-2)", display: "inline-flex" }}><KindIcon kind="avionics" /></span>
                  <strong style={{ fontWeight: "var(--fw-med)" as never, flex: 1 }}>ECU</strong>
                  <span className="badge badge-err">0 V</span>
                </div>
              </div>
            </div>
          </Section>

          <Section title="Popup and menu">
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--s2)", alignItems: "flex-start", background: "var(--canvas)", padding: "var(--s2)", borderRadius: "var(--radius)", border: "var(--border-w) solid var(--border)" }}>
              <div className="dialog anim-pop" style={{ minWidth: 0, width: 272 }}>
                <header><span>W-1042</span><button className="btn btn-ghost btn-icon btn-sm" aria-label="Close"><Icon name="close" /></button></header>
                <section style={{ display: "grid", gap: "var(--s1)" }}>
                  <div style={{ ...row, color: "var(--warn)" }}><Icon name="warning" /><span style={{ color: "var(--text)" }}>Voltage drop 4.2 % (limit 3 %)</span></div>
                  <span style={{ color: "var(--text-2)" }}>20 AWG, 1.8 m, 7.5 A. A 18 AWG wire keeps the drop under 3 %.</span>
                </section>
                <footer><button className="btn btn-sm">Ignore</button><button className="btn btn-primary btn-sm">Use 18 AWG</button></footer>
              </div>
              <div style={{ display: "grid", gap: "var(--s2)" }}>
                <div className="menu anim-pop">
                  <button className="menu-item"><Icon name="file" />Harness drawing<span className="kbd">D</span></button>
                  <button className="menu-item" aria-selected="true"><Icon name="export" />Pinout sheet</button>
                  <button className="menu-item"><Icon name="refresh" />Fault sweep</button>
                  <div className="divider" style={{ margin: "var(--s-half) 0" }} />
                  <button className="menu-item menu-item-danger"><Icon name="x-circle" />Remove</button>
                </div>
                <div style={{ position: "relative", height: 28 }}><span className="tooltip" style={{ left: 0, top: 0 }}>Fit to screen<span className="kbd">F</span></span></div>
              </div>
            </div>
          </Section>

          <Section title="Component kinds">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "var(--s2) var(--s1)" }}>
              {KIND_NAMES.map((k) => <div key={k} style={{ display: "grid", justifyItems: "center", gap: 6, color: "var(--text)" }}>
                <span style={{ display: "flex", gap: 10, alignItems: "center" }}><KindIcon kind={k} /><KindIcon kind={k} size={24} /></span>
                <span style={{ fontSize: "var(--fs-xs)", color: "var(--text-2)" }}>{k}</span></div>)}
            </div>
          </Section>

          <Section title="UI icons">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(9, 1fr)", gap: "var(--s2) var(--s1)" }}>
              {ICON_NAMES.map((n) => <div key={n} title={n} style={{ display: "grid", justifyItems: "center", gap: 6 }}>
                <Icon name={n} /><span style={{ fontSize: 10, color: "var(--text-3)", whiteSpace: "nowrap" }}>{n}</span></div>)}
            </div>
            <div style={{ ...row, gap: "var(--s2)" }}>
              <Logo size={16} /><Logo size={24} /><Logo size={32} /><Logo size={48} />
              <span style={{ color: "var(--text-2)", fontSize: "var(--fs-sm)" }}>logo in --logo (never the accent)</span>
            </div>
          </Section>
        </div>
      </div>
    </main>
  </div>;
}
