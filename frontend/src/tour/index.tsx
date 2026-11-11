// The quickstart tour (docs/tour.md): driver.js spotlights one control at a time and each step advances when the user does
// the thing, which the app announces as a `schemagen:action` event. Steps whose target is missing are skipped.
import { useEffect } from "react";
import { driver, type Driver } from "driver.js";
import "driver.js/dist/driver.css";
import "./tour.css";
import { post } from "../api";

interface Step { id: string; targets: string[]; title: string; text: string; on: string[]; later?: boolean; reveal?: boolean; variant?: () => Partial<Step> | null }

const STEPS: Step[] = [
  { id: "diagram", targets: ["[data-tour=diagram]"], on: ["zoom"], title: "Your whole system, one picture",
    text: "This is the Kestrel E2's wiring: batteries and the DC-DC converter on the left, then breakers, buses, the firewall and wing-root connectors, and the loads. Scroll to zoom and drag to pan." },
  { id: "node", targets: ['[data-tour-node="CB-XPDR"]', "[data-tour=node]"], on: ["card-open"], reveal: true, title: "Click a component",
    text: "Click the XPDR breaker. Its card shows every wire on it, with gauge and current." },
  { id: "card", targets: ["[data-tour=card]"], on: ["card-close"], later: true, title: "Everything about one part",
    text: "The XPDR breaker is 15 A, but the transponder draws 1.5 A through 20 AWG wire, which allows at most 7.5 A. Close the card when you are done." },
  { id: "issues", targets: ["[data-tour=issues]"], on: ["issue-click"], title: "What is wrong",
    text: "The Issues list found two errors: wire W045 is 22 AWG behind the 10 A landing-light breaker, and the 15 A XPDR breaker is too big for its wire. Click one to find it on the diagram." },
  { id: "wires", targets: ["[data-tour=wires]"], on: ["wires-open", "wire-click"], title: "The sheet you know",
    variant: () => document.querySelector("[data-tour=wires][aria-expanded=true]") ? { targets: [".wires.open"], on: ["wire-click"],
      text: "Every row of your sheet is here. Click W045, the landing-light switch feed: it is marked red, and its fix is 18 AWG." } : null,
    text: "Every row of your sheet is here. Open the Wires drawer: W045, the landing-light switch feed, is marked red; its fix is 18 AWG." },
  { id: "simulate", targets: ["[data-tour=simulate]"], on: ["simulate-done"], title: "Does it work with power on?",
    text: "Press Simulate. The main and essential buses sit near 13.4 V, but the cabin bus stays at 0 V: nothing feeds it, so the cabin light, USB charger and cabin fan stay dark." },
  { id: "source", targets: ["[data-tour=add-source]"], on: ["source-added"], title: "Try a fix",
    text: "Add a source to the cabin bus with + Source and simulate again to see its loads come on. Your sheet is not changed." },
  { id: "import", targets: ["[data-tour=import]"], on: ["import-start"], title: "Now your own wiring",
    text: "Import your own wire sheet (.xlsx or .csv) and the same diagram, issues and simulation are made from it. Replay this tour from the help menu." },
];

interface Run { d: Driver; steps: Step[]; i: number; on: string[]; timer: number; gen: number }
let run: Run | null = null;
let gen = 0;

const find = (s: Step) => s.targets.map((q) => document.querySelector<HTMLElement>(q)).find(Boolean) ?? null;
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));

/** The element of step `s`, polling briefly: a card may still be rendering. */
async function waitFor(s: Step, g: number): Promise<HTMLElement | null> {
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
  const { d } = run; run = null; gen++;
  document.body.classList.remove("sg-tour-aside");
  d.destroy();
  post("/api/settings", { tour_done: true }).catch(() => { /* seen only for this session */ });
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

/** Shows step `i` (skipping those whose target is missing) and waits for its action. */
async function go(i: number) {
  const r = run; if (!r) return;
  const g = ++gen; r.gen = g; window.clearTimeout(r.timer);
  for (; i < r.steps.length; i++) {
    const s = { ...r.steps[i], ...r.steps[i].variant?.() };
    const el = s.later ? await waitFor(s, g) : find(s);
    if (g !== gen) return;
    if (!el) continue;
    if (s.reveal) {  // the card may be off screen: fit the view first
      const a = el.getBoundingClientRect(), b = document.querySelector("[data-tour=diagram]")?.getBoundingClientRect();
      if (b && (a.left < b.left || a.right > b.right || a.top < b.top || a.bottom > b.bottom)) {
        document.querySelector<HTMLElement>("[data-tour=fit]")?.click(); await wait(reduced() ? 100 : 600); if (g !== gen) return;
      }
    }
    r.i = i; r.on = s.on; const last = i === r.steps.length - 1;
    r.d.highlight({ element: find(s)!, popover: { title: s.title, description: s.text, side: "bottom", align: "start", popoverClass: "sg-tour", showButtons: [],
      onPopoverRender: (pop) => footer(pop, r, last) } });
    return;
  }
  stop();
}

/** Starts (or restarts) the tour on the open project. */
export function startTour(): void {
  if (run) { run.d.destroy(); run = null; gen++; }
  const steps = STEPS.filter((s) => s.later || find(s));
  if (!steps.length) return;
  const d = driver({ animate: !reduced(), smoothScroll: false, allowKeyboardControl: false, overlayClickBehavior: () => { /* clicks outside do nothing */ },
    stagePadding: 6, stageRadius: 6, popoverOffset: 12 });
  run = { d, steps, i: 0, on: [], timer: 0, gen: 0 };
  void go(0);
}

/** Listens for what the user does; renders nothing. */
export function Tour() {
  useEffect(() => {
    const h = (e: Event) => {
      const r = run, a = (e as CustomEvent<{ action: string }>).detail?.action;
      if (a === "source-pick" || a === "source-pick-end") { aside(a === "source-pick"); return; }
      if (!r || !a || !r.on.includes(a)) return;
      const g = r.gen;
      window.clearTimeout(r.timer);
      r.timer = window.setTimeout(() => { if (run === r && r.gen === g) { if (r.i === r.steps.length - 1) stop(); else void go(r.i + 1); } }, 450);
    };
    window.addEventListener("schemagen:action", h);
    return () => { window.removeEventListener("schemagen:action", h); if (run) { run.d.destroy(); run = null; gen++; } };
  }, []);
  return null;
}
