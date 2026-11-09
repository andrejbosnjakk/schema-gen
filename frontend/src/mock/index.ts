// An in-memory server for development and the e2e tests (`?mock=1`), per docs/api.md. Fictional aircraft-like system.
//   ?mock=1             start screen          &open=1     start with the example open
//   &wires=1000         a bigger example      &fail=open  /api/open fails once (retry flow)
import { useMock } from "../api";
import type { Edge, Issue, Node, Overlay, Session, Wire, Workspace } from "../types";

const PALETTE: Record<string, string> = { "14 V": "#ff0000", "GND": "#000000", "CAN_H": "#00ff00", "CAN_L": "#00ff00",
  "HV": "#ff8000", "signal": "#0066ff", "5 V": "#8000ff" };
const VOLT: Record<string, string> = { "14 V": "14 V", "GND": "0 V", "CAN_H": "CAN", "CAN_L": "CAN", "HV": "400 V", "signal": "signal", "5 V": "5 V" };
const SHORT: Record<string, string> = { CAN_H: "CAN", CAN_L: "CAN", GND: "GND" };

function rng(seed: number) { return () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296); }

// [id, name, kind, zone, bus, current A, via harness connector, on CAN]
type Load = [string, string, string, string, string, number, string, boolean];
const LOADS: Load[] = [
  ["PFD", "Primary flight display", "avionics", "Avionics", "AVB", 2.5, "", true],
  ["MFD", "Multi-function display", "avionics", "Avionics", "AVB", 2.5, "", true],
  ["GPS", "GPS receiver", "avionics", "Avionics", "AVB", 0.8, "", false],
  ["COM1", "COM 1 radio", "avionics", "Avionics", "AVB", 1.5, "", false],
  ["COM2", "COM 2 radio", "avionics", "Avionics", "AVB", 1.5, "", false],
  ["XPDR", "Transponder", "avionics", "Avionics", "AVB", 1, "", false],
  ["ADAHRS", "Air data and attitude unit", "sensor", "Avionics", "AVB", 0.6, "", true],
  ["AUD", "Audio panel", "avionics", "Avionics", "AVB", 0.5, "", false],
  ["AP", "Autopilot pitch servo", "motor", "Avionics", "AVB", 3, "X-TAIL", true],
  ["NAVL", "Navigation light left", "light", "Lighting", "MAIN", 1.2, "X-WING", false],
  ["NAVR", "Navigation light right", "light", "Lighting", "MAIN", 1.2, "X-WING", false],
  ["STRL", "Strobe left", "light", "Lighting", "MAIN", 1.8, "X-WING", false],
  ["STRR", "Strobe right", "light", "Lighting", "MAIN", 1.8, "X-WING", false],
  ["LDG", "Landing light", "light", "Lighting", "MAIN", 4, "X-WING", false],
  ["TAXI", "Taxi light", "light", "Lighting", "MAIN", 3, "X-WING", false],
  ["CABL", "Cabin light", "light", "Lighting", "ESS", 0.6, "", false],
  ["MC", "Motor controller", "motor", "Propulsion", "", 0, "", true],
  ["BMS", "Battery management system", "can", "Propulsion", "ESS", 0.4, "", true],
  ["PUMP", "Coolant pump", "motor", "Propulsion", "ESS", 5, "", false],
  ["FAN", "Radiator fan", "motor", "Propulsion", "ESS", 6, "", false],
  ["THR", "Throttle position sensor", "sensor", "Propulsion", "ESS", 0.1, "", true],
  ["PITOT", "Pitot heater", "device", "Systems", "MAIN", 7, "X-WING", false],
  ["FLAP", "Flap actuator", "motor", "Systems", "MAIN", 8, "X-WING", false],
  ["TRIM", "Elevator trim actuator", "motor", "Systems", "ESS", 2, "X-TAIL", false],
  ["STALL", "Stall warning sensor", "sensor", "Systems", "ESS", 0.2, "X-WING", false],
  ["CFAN", "Cabin fan", "motor", "Systems", "MAIN", 2, "", false],
  ["USB", "USB charging port", "device", "Systems", "MAIN", 3, "", false],
  ["CANOPY", "Canopy closed switch", "switch", "Systems", "ESS", 0.05, "", false],
];

/** A whole Workspace of about `target` wires. */
export function build(target: number, name: string, extraIssues: Issue[] = []): Workspace {
  const r = rng(7);
  const comps = new Map<string, Node>();
  const zone = new Map<string, string>();
  const wires: Wire[] = [];
  const add = (id: string, nm: string, kind: string, rank: number, z: string) => {
    comps.set(id, { id, name: nm, kind, zone: z, subsystem: z, pins: 0, rank, sev: "" }); zone.set(id, z);
  };
  const gauge = (a: number) => (a > 20 ? "8 AWG" : a > 7 ? "16 AWG" : a > 3 ? "18 AWG" : a > 1 ? "20 AWG" : "22 AWG");
  const wire = (a: string, b: string, cls: string, current: number | null, harness = "") => {
    const n = wires.length + 1, id = `W${String(n).padStart(4, "0")}`;
    const ca = comps.get(a)!, cb = comps.get(b)!;
    ca.pins++; cb.pins++;
    wires.push({ id, label: `L${String(n).padStart(3, "0")}`, name: `${cb.name} ${cls === "GND" ? "return" : cls.startsWith("CAN") ? cls.replace("_", " ") : "supply"}`,
      from: `${ca.name} J1 ${ca.pins}`, to: `${cb.name} J1 ${cb.pins}`, a, b, gauge: cls.startsWith("CAN") ? "24 AWG" : gauge(current ?? 1),
      voltage: VOLT[cls] ?? "", current, cls, hex: PALETTE[cls] ?? "#999999", length: Math.round(r() * 60 + 5) / 10, harness,
      protection: "", status: "", notes: "", sev: "" });
  };
  add("BAT", "Main battery 14 V", "battery", 0, "Power"); add("BAT2", "Standby battery 14 V", "battery", 0, "Power");
  add("HVB", "HV battery pack 400 V", "battery", 0, "Propulsion"); add("DCDC", "DC/DC converter 400 V to 14 V", "dcdc", 0, "Power");
  add("CB-MAIN", "Main breaker 60 A", "breaker", 1, "Power"); add("CB-STBY", "Standby breaker 20 A", "breaker", 1, "Power");
  add("CB-ESS", "Essential feed breaker 30 A", "breaker", 1, "Power"); add("CB-AV", "Avionics master breaker 15 A", "breaker", 1, "Power");
  add("F-HV", "HV main fuse 250 A", "fuse", 1, "Propulsion");
  add("MAIN", "Main bus 14 V", "bus", 2, "Power"); add("ESS", "Essential bus 14 V", "bus", 2, "Power");
  add("AVB", "Avionics bus 14 V", "bus", 2, "Power"); add("GNDB", "Ground bus", "ground", 2, "Power");
  add("X-WING", "Wing harness connector", "harness", 3, "Airframe"); add("X-TAIL", "Tail harness connector", "harness", 3, "Airframe");
  wire("BAT", "CB-MAIN", "14 V", 45); wire("CB-MAIN", "MAIN", "14 V", 45); wire("BAT", "GNDB", "GND", 45);
  wire("BAT2", "CB-STBY", "14 V", 15); wire("CB-STBY", "ESS", "14 V", 15); wire("BAT2", "GNDB", "GND", 15);
  wire("DCDC", "CB-ESS", "14 V", 25); wire("CB-ESS", "ESS", "14 V", 25); wire("DCDC", "GNDB", "GND", 25);
  wire("CB-AV", "MAIN", "14 V", 12); wire("CB-AV", "AVB", "14 V", 12);
  wire("HVB", "DCDC", "HV", 3); wire("HVB", "DCDC", "GND", 3); wire("HVB", "F-HV", "HV", 200);

  const can: string[] = [];
  const place = (l: Load, sfx: string, zn: string, conn: string) => {
    const [id0, nm, kind, , bus, amps, , onCan] = l, id = id0 + sfx;
    add(id, nm + (sfx ? ` ${sfx.slice(1)}` : ""), kind, 4, zn);
    if (id0 === "MC") {
      wire("F-HV", id, "HV", 200); wire("HVB", id, "GND", 200);
      add("MOT" + sfx, "Propulsion motor", "motor", 4, zn);
      for (let p = 0; p < 3; p++) wire(id, "MOT" + sfx, "HV", 180);  // three phases
    } else if (conn) {
      wire(bus, conn, "14 V", amps, conn); wire(conn, id, "14 V", amps, conn); wire("GNDB", id, "GND", amps);
    } else { wire(bus, id, "14 V", amps); wire("GNDB", id, "GND", amps); }
    if (kind === "sensor" || kind === "switch") wire(id, "PFD", "signal", 0.01);
    if (onCan) can.push(id);
  };
  for (const l of LOADS) place(l, "", l[3], l[6]);
  for (let i = 1; wires.length < target - 2 * can.length; i++) {  // more cabin zones, each behind its own harness connector
    const x = `X-CAB${i}`, z = `Cabin section ${i}`;
    add(x, `Cabin harness connector ${i}`, "harness", 3, "Airframe");
    for (const l of LOADS.filter((l) => l[3] !== "Propulsion" && l[0] !== "PFD").slice(0, 12)) {
      if (wires.length >= target - 2 * can.length) break;
      place([l[0], l[1], l[2], z, l[4] || "MAIN", l[5], x, false], `-${i}`, z, x);
    }
  }
  for (let i = 0; i + 1 < can.length; i++) { wire(can[i], can[i + 1], "CAN_H", null); wire(can[i], can[i + 1], "CAN_L", null); }

  // findings (fictional); severity shows on the cards and wires they name
  const issues: Issue[] = [...extraIssues];
  const I = (severity: Issue["severity"], rule: string, title: string, message: string, objects: string[]) =>
    issues.push({ k: issues.length + 1, rule, severity, title, message, fix: "", objects });
  const w = (i: number) => wires[Math.min(i, wires.length - 1)];
  I("error", "gauge-vs-breaker", "Wire for the landing light is too thin for its breaker",
    `${w(40).label} is ${w(40).gauge}, but the feed is protected at 15 A (max 7.5 A for this gauge).`, [`conductor:${w(40).id}`, "component:LDG"]);
  I("error", "unpowered-bus", "Avionics bus has no source when the main breaker is open",
    "Every load on the avionics bus depends on CB-MAIN; consider a standby feed.", ["component:AVB"]);
  I("error", "can-termination", "CAN bus has only one termination", "The chain PFD … THR is terminated at PFD only; add a terminator at the far end.", ["component:THR", "component:PFD"]);
  I("warning", "missing-ground", "Pitot heater return shares a pin with the stall warning sensor", "Two returns on one pin make a fault hard to find.", ["component:PITOT", "component:STALL"]);
  I("warning", "direction", "Wire written from the load to the bus", `${w(12).label} runs ${w(12).to} → ${w(12).from}; the sheet usually writes source first.`, [`conductor:${w(12).id}`]);
  I("warning", "oversized", "Radiator fan wire is far heavier than needed", "16 AWG carries 6 A here; 20 AWG would do.", ["component:FAN"]);
  I("warning", "no-current", "No current given for the coolant pump", "The simulation assumes 5 A from the part name.", ["component:PUMP"]);
  I("info", "spare-pins", "Wing harness connector has 6 spare pins", "Spares are shown on the harness drawing.", ["component:X-WING"]);
  I("info", "no-length", "11 wires have no length", "Voltage drop is estimated with 2 m for these.", [`conductor:${w(70).id}`]);
  const rankSev = { error: 3, warning: 2, info: 1, "": 0 };
  const bump = (o: { sev: Node["sev"] }, s: Issue["severity"]) => { if (rankSev[s] > rankSev[o.sev]) o.sev = s; };
  const wById = new Map(wires.map((x) => [x.id, x]));
  for (const i of issues) for (const o of i.objects) {
    const [t, id] = [o.slice(0, o.indexOf(":")), o.slice(o.indexOf(":") + 1)];
    if (t === "component" && comps.has(id)) bump(comps.get(id)!, i.severity);
    if (t === "conductor" && wById.has(id)) { const x = wById.get(id)!; bump(x, i.severity); bump(comps.get(x.a)!, i.severity); }
  }

  // bundle per component pair, a -> b in power order
  const groups = new Map<string, Wire[]>();
  for (const x of wires) {
    const [a, b] = comps.get(x.a)!.rank <= comps.get(x.b)!.rank ? [x.a, x.b] : [x.b, x.a];
    const k = `${a}~${b}`; const g = groups.get(k); if (g) g.push(x); else groups.set(k, [x]);
  }
  const edges: Edge[] = [...groups].map(([k, g]) => {
    const [a, b] = k.split("~"), cls = [...new Set(g.map((x) => x.cls))];
    const short = [...new Set(cls.map((c) => SHORT[c] ?? c))];
    return { id: k, a, b, wires: g.map((x) => x.id), cls, label: short.length === 1 ? `${g.length} × ${short[0]}` : `${g.length} wires` };
  });
  const zones = [...new Set(zone.values())].map((z) => ({ id: z.toLowerCase().replace(/\s+/g, "-"), name: z, members: [...zone].filter(([, v]) => v === z).map(([k]) => k) }));
  return { project: { name, root: `C:\\Users\\you\\AppData\\Local\\schemagen\\projects\\${name}`, version: "1.0.0", warnings: [] },
    components: [...comps.values()], edges, conductors: wires, issues, zones, positions: {}, sources: [], palette: PALETTE };
}

const OVERLAY: Overlay = { ok: false, summary: { problems: 3, trips: 0, unpowered: 1, text: "3 problems, 0 trips" },
  buses: [{ id: "MAIN", voltage_V: 13.6, nominal_V: 14, powered: true }, { id: "AVB", voltage_V: 0, nominal_V: 14, powered: false }],
  breakers: [{ id: "CB-MAIN", current_A: 41.2, rating_A: 60, loading: 0.69, trips: false }],
  items: { "component:AVB": { status: "error", reason: "Avionics bus has loads and no source" } }, assumptions: ["Loads without part data draw their sheet current."] };

/** Route the app's calls to the in-memory server. */
export function install(q: URLSearchParams) {
  const big = Number(q.get("wires")) || 120;
  let ws: Workspace | null = q.has("open") ? build(big, "Example aircraft") : null;
  let failOpen = q.get("fail") === "open";
  const session: Session = { project: ws?.project ?? null, tour_done: true, theme: "light", recent: [
    { name: "Example aircraft", path: "C:\\Users\\you\\AppData\\Local\\schemagen\\projects\\Example aircraft", opened: "2026-11-06T09:12:00" },
    { name: "Glider avionics retrofit", path: "C:\\Users\\you\\Documents\\wiring\\glider-avionics", opened: "2026-10-28T16:40:00" }] };
  const ok = (json: unknown, ms = 120) => new Promise<{ status: number; json: unknown }>((res) => setTimeout(() => res({ status: 200, json }), ms));
  const err = (status: number, code: string, message: string, retry = false) => ok({ error: { code, message, retry } }).then((r) => ({ ...r, status }));
  useMock(async (method, path, body) => {
    if (path === "/api/session") return ok({ ...session, project: ws?.project ?? null });
    if (path === "/api/settings") { Object.assign(session, body); return ok({ ok: true }, 20); }
    if (path === "/api/open") {
      if (failOpen) { failOpen = false; return err(503, "internal", "The project could not be opened just now. Please try again.", true); }
      ws = build(big, (body as { path?: string }).path?.split("\\").pop() || "Example aircraft"); return ok(ws, 350);
    }
    if (path === "/api/import") {
      const f = body as File;
      if (!/\.(xlsx|csv)$/i.test(f.name)) return err(400, "import-failed", "Only .xlsx and .csv wire sheets can be imported.");
      const rows = /\.csv$/i.test(f.name) ? (await f.text()).split(/\r?\n/).filter((l) => l.trim()).length - 1 : Math.round(f.size / 80);
      ws = build(Math.max(20, rows), f.name.replace(/\.[^.]+$/, ""), [{ k: 0, rule: "readable-cell", severity: "warning",
        title: "Row 14: the pin cell could not be read", message: "“pin 3/4?” is not a pin; the wire is kept without a pin.", fix: "", objects: [] }]);
      return ok(ws, 200 + rows * 0.5);
    }
    if (path === "/api/workspace") return ws ? ok(ws) : err(409, "no-project", "No project is open.");
    if (path === "/api/positions") { if (ws) Object.assign(ws.positions, (body as { positions: object }).positions); return ok({ ok: true }, 20); }
    if (path === "/api/simulate") return ok(OVERLAY, 600);
    if (path === "/api/export") return ok({ folder: `${ws?.project.root}\\out`, files: ["X-WING.svg", "X-TAIL.svg"] }, 400);
    if (path === "/api/reveal") return ok({ ok: true });
    return err(404, "not-found", `Nothing at ${method} ${path}.`);
  });
}
