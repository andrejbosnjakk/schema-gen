// The quickstart tour (docs/tour.md): driver.js spotlights one control at a time and each step advances when the user does
// the thing, which the app announces as a `schemagen:action` event. Steps whose target is missing are skipped.
import { useEffect } from "react";
import { driver, type Driver } from "driver.js";
import "driver.js/dist/driver.css";
import "./tour.css";
import { post, tourDo } from "../api";

type Side = "top" | "bottom" | "left" | "right";
/** One thing the popover says and waits for; a step with several phases keeps its place in the counter and re-anchors when a phase's action arrives. */
interface Phase { targets: string[]; text: string; title?: string; on: string[]; side?: Side; delay?: number; enter?: () => void; read?: boolean }
interface Step { id: string; title: string; phases: Phase[]; later?: boolean; reveal?: boolean }
const fit = () => document.querySelector<HTMLElement>("[data-tour=fit]")?.click();

const STEPS: Step[] = [
  { id: "diagram", title: "Your whole system, one picture", phases: [{ targets: ["[data-tour=diagram]"], on: ["zoom"],
    text: "This is the Kestrel E2's wiring, grouped by subsystem. Scroll to zoom and drag to pan." }] },
  { id: "node", reveal: true, title: "Click a component", phases: [{ targets: ['[data-tour-node="CB-XPDR"]', "[data-tour=node]"], on: ["card-open"],
    text: "Click the XPDR breaker. Its card lists the wire on each of its pins." }] },
  { id: "card", later: true, title: "Everything about one part", phases: [{ targets: ["[data-tour=card]"], on: ["card-close"],
    text: "The card shows what is wrong with this part, then its pins and the wire on each. Close it when you are done." }] },
  { id: "issues", title: "What is wrong", phases: [{ targets: ["[data-tour=issues]"], on: ["issue-click"],
    text: "The Issues list found three errors: a wire too thin for its breaker, a breaker too big for its wire, and a bus with no power source. Click one to find it on the diagram. Esc clears it." }] },
  { id: "wires", title: "The sheet you know", phases: [{ targets: [".wires.open", "[data-tour=wires]"], on: ["wire-click"], enter: () => tourDo("show-wire", "W045"),
    text: "Every row of your sheet is here, with W045 marked. Click a row to see that wire on the diagram. Click its label to open its card." }] },
  { id: "simulate", title: "Does it work with power on?", phases: [
    { targets: ["[data-tour=simulate]"], on: ["simulate-done"], delay: 350, text: "Press Simulate to switch the power on.", enter: () => { tourDo("clear"); fit(); } },
    { targets: ["[data-tour=sim-summary]"], on: [], read: true, enter: () => tourDo("sim-collapse"), title: "What the simulation shows",
      text: "Each bus card now shows its voltage, and the bars on the breakers show how loaded they are. The cabin bus is red at 0 V: nothing feeds it, so the cabin light, USB charger and cabin fan stay dark. Press Next." }] },
  { id: "source", title: "Try a fix", phases: [
    { targets: ["[data-tour=add-source]"], on: ["source-added"], delay: 0, text: "Click + Source, then click the cabin bus to add a battery to it. Your sheet is not changed." },
    { targets: ["[data-tour=simulate]"], on: ["simulate-done"], delay: 350, title: "Press Simulate again", text: "The new source is wired to the cabin bus. Simulate again to see the result." },
    { targets: ["[data-tour=sim-summary]"], on: [], read: true, enter: () => tourDo("sim-collapse"), title: "The cabin bus has power",
      text: "The cabin bus now shows its voltage and is no longer red, so its loads come on. Press Next." }] },
  { id: "import", title: "Now your own wiring", phases: [{ targets: ["[data-tour=import]"], on: ["import-start"],
    text: "Import your own wire sheet (.xlsx or .csv) and the same diagram, issues and simulation are made from it. Replay this tour from the help menu." }] },
];

interface Run { d: Driver; steps: Step[]; i: number; p: number; timer: number; gen: number }
let run: Run | null = null;
let gen = 0;

const find = (s: Phase) => s.targets.map((q) => document.querySelector<HTMLElement>(q)).find(Boolean) ?? null;
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));

/** The element of step `s`, polling briefly: a card may still be rendering. */
async function waitFor(s: Phase, g: number): Promise<HTMLElement | null> {
  for (let n = 0; n < 15; n++) { const el = find(s); if (el) return el; await wait(80); if (g !== gen) return null; }
  return null;
}

/** Steps aside while the user places a source: hide the spotlight and let clicks reach the diagram, then come back. */
function aside(on: boolean) {
  document.body.classList.toggle("sg-tour-aside", on && !!run);
  if (run) document.body.classList.toggle("driver-active", !on);
}

/** Ends the tour and records that it has been seen (finished or skipped). */
function stop() {
  if (!run) return;
  stopTour();
  post("/api/settings", { tour_done: true }).catch(() => { /* seen only for this session */ });
}

/** Ends the tour without recording anything (the project was closed). */
export function stopTour() {
  if (!run) return;
  const { d } = run; run = null; gen++;
  document.body.classList.remove("sg-tour-aside", "sg-tour-read");
  d.destroy();
}

/** The popover footer: step counter, Skip, Next (Done on the last step). */
function footer(pop: { wrapper: HTMLElement }, r: Run, last: boolean) {
  const f = document.createElement("div"); f.className = "sg-tour-foot";
  const n = document.createElement("span"); n.className = "sg-tour-count"; n.textContent = `${r.i + 1} of ${r.steps.length}`;
  const skip = document.createElement("button"); skip.className = "btn btn-ghost btn-sm"; skip.textContent = "Skip tour"; skip.onclick = stop;
  const next = document.createElement("button"); next.className = "btn btn-primary btn-sm"; next.textContent = last ? "Done" : "Next";
  next.onclick = () => (last ? stop() : void go(r.i + 1));
  f.append(n, skip, next); pop.wrapper.append(f);
}

/** Shows phase `p` of step `i` (skipping steps whose target is missing) and waits for its action. */
async function go(i: number, p = 0) {
  const r = run; if (!r) return;
  const g = ++gen; r.gen = g; window.clearTimeout(r.timer);
  for (; i < r.steps.length; i++) {
    const st = r.steps[i], ph = st.phases[p];
    if (p === 0 && st.id !== "card") tourDo("close");   // a new step starts with no card or dialog open (the card step is about the card)
    if (ph.enter) { ph.enter(); await wait(reduced() ? 150 : 650); if (g !== gen) return; }
    document.body.classList.toggle("sg-tour-read", !!ph.read);
    const el = st.later || p > 0 ? await waitFor(ph, g) : find(ph);
    if (g !== gen) return;
    if (!el) { if (p > 0) { void go(i + 1); return; } continue; }
    if (st.reveal) {  // the card may be off screen: fit the view first
      const a = el.getBoundingClientRect(), b = document.querySelector("[data-tour=diagram]")?.getBoundingClientRect();
      if (b && (a.left < b.left || a.right > b.right || a.top < b.top || a.bottom > b.bottom)) {
        document.querySelector<HTMLElement>("[data-tour=fit]")?.click(); await wait(reduced() ? 100 : 600); if (g !== gen) return;
      }
    }
    r.i = i; r.p = p; const last = i === r.steps.length - 1;
    r.d.highlight({ element: find(ph)!, popover: { title: ph.title ?? st.title, description: ph.text, side: ph.side ?? "bottom", align: ph.read ? "end" : "start", popoverClass: "sg-tour", showButtons: [],
      onPopoverRender: (pop) => footer(pop, r, last) } });
    return;
  }
  stop();
}

/** Starts (or restarts) the tour on the open project. */
export function startTour(): void {
  if (run) { run.d.destroy(); run = null; gen++; }
  const steps = STEPS.filter((s) => s.later || s.phases[0].enter || find(s.phases[0]));
  if (!steps.length) return;
  const d = driver({ animate: !reduced(), smoothScroll: false, allowKeyboardControl: false, overlayClickBehavior: () => { /* clicks outside do nothing */ },
    stagePadding: 6, stageRadius: 6, popoverOffset: 12 });
  run = { d, steps, i: 0, p: 0, timer: 0, gen: 0 };
  void go(0);
}

/** Listens for what the user does; renders nothing. */
export function Tour() {
  useEffect(() => {
    const h = (e: Event) => {
      const r = run, a = (e as CustomEvent<{ action: string }>).detail?.action;
      if (a === "source-pick" || a === "source-pick-end") { aside(a === "source-pick"); return; }
      const st = r?.steps[r.i], ph = st?.phases[r!.p];
      if (!r || !a || !st || !ph || !ph.on.includes(a)) return;
      const g = r.gen, more = r.p < st.phases.length - 1;
      window.clearTimeout(r.timer);
      r.timer = window.setTimeout(() => { if (run === r && r.gen === g) { if (more) void go(r.i, r.p + 1); else if (r.i === r.steps.length - 1) stop(); else void go(r.i + 1); } }, ph.delay ?? 450);
    };
    window.addEventListener("schemagen:action", h);
    return () => { window.removeEventListener("schemagen:action", h); if (run) { run.d.destroy(); run = null; gen++; } };
  }, []);
  return null;
}
