"""Synthetic (fictional) vehicle projects for tests and benchmarks: `schemagen synth --wires N --seed S -o DIR`.

The project uses the row-module input (ss??_*.py with R, P, D, O tables), labels.json, cards with ```yaml schemagen
blocks, lengths.csv and scenarios/. It is electrically consistent (gauges fit the breakers, wires follow the
direction convention, CAN buses have two terminators), so a clean project has no rule findings except its open items.
Same seed, same output.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# zone code -> (name, x, y) in metres; harness connectors join neighbouring zones
ZONES = {"FR": ("Front", 0.0, 0.0), "CB": ("Cabin", 1.5, 0.0), "EN": ("Engine", 3.0, 0.0),
         "RR": ("Rear", 4.5, 0.0), "RF": ("Roof", 1.5, 1.0)}
LINKS = [("FR", "CB"), ("CB", "EN"), ("EN", "RR"), ("CB", "RF")]
# max breaker rating per gauge, FAA AC 43.13-1B Table 11-3 (same table as core/data/protection.yml)
CB_MAX = {22: 5, 20: 7.5, 18: 10, 16: 15, 14: 20, 12: 30, 10: 40, 8: 50, 6: 80, 4: 100}
FU_MAX = {22: 5, 20: 5, 18: 10, 16: 10, 14: 15, 12: 20, 10: 30, 8: 50, 6: 70, 4: 70}
RATINGS = [3, 5, 7.5, 10, 15, 20]
LOADS = {  # family -> (part, description, model, watts or amps, v_nom, v_min, bus)
    "L10": ("SV-LAMP-10W", "lamp 10 W", "constant_power", 10, 14, 9, "14 V"),
    "L25": ("SV-LAMP-25W", "lamp 25 W", "constant_power", 25, 14, 9, "14 V"),
    "PU": ("SV-PUMP-3A", "pump 3 A", "constant_current", 3.0, 14, 10, "14 V"),
    "HT": ("SV-HEATER-60W", "heater 60 W", "resistive", 60, 14, 0, "14 V"),
    "FN": ("SV-FAN-48W", "fan 48 W", "constant_power", 48, 24, 18, "24 V"),
    "AC": ("SV-ACT-24W", "actuator 24 W", "constant_power", 24, 24, 18, "24 V"),
}


@dataclass
class Synth:
    n: int
    rng: random.Random
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    harness: dict[tuple[str, str, str], list[Any]] = field(default_factory=dict)  # (a, b, kind) -> [raw, next pin, cap]
    hdecl: dict[str, list[str]] = field(default_factory=dict)
    sides: dict[str, dict[str, str]] = field(default_factory=dict)
    gsplice: dict[str, list[Any]] = field(default_factory=dict)  # zone -> [raw, wires, amps]
    gtrunks: list[tuple[str, str, float]] = field(default_factory=list)
    P: list[dict[str, Any]] = field(default_factory=list)
    lengths: dict[str, float] = field(default_factory=dict)
    cur_mod: str = "ss01_power"
    total: int = 0
    ctl: str = ""
    ctl_splice: str = ""
    ctl_count: int = 0
    devices: dict[str, str] = field(default_factory=dict)  # code -> zone

    # ------------------------------------------------------------ helpers
    def nid(self, k: str) -> int:
        self.counters[k] = self.counters.get(k, 0) + 1
        return self.counters[k]

    def wire(self, a: tuple[str, str, str], b: tuple[str, str, str], func: str, bus: str, awg: int, amps: float = 0,
             zone: str = "CB", harn: str = "", prot: str = "", length: float | None = None, cls: str = "P") -> str:
        i = self.nid("wire")
        wid = f"W{i:05d}"
        lab = f"{cls}{self.nid('lab' + cls):04d}"
        r: dict[str, Any] = dict(id=wid, p1=a[0], p1c=a[1], p1p=a[2], p2=b[0], p2c=b[1], p2p=b[2], func=func, bus=bus,
                                 awg=str(awg), st="Released", src=f"EWD-{self.cur_mod[2:4]} p. {1 + i // 25}", zone=zone)
        if amps: r["amps"] = round(amps, 3)
        if harn: r["harn"] = harn
        if prot: r["prot"] = prot
        if cls == "S" and self.rng.random() < 0.3: r["col"] = "WH"
        if self.rng.random() < 0.05: r["legacy"] = f"OLD-{i:04d}"
        self.rows.setdefault(self.cur_mod, []).append(r)
        self.labels[wid] = lab
        ln = length if length is not None else round(0.4 + self.rng.random() * 1.6, 2)
        if self.rng.random() < 0.4 or cls == "N": self.lengths[lab] = ln
        self.total += 1
        return wid

    def dev(self, code: str, desc: str, zone: str) -> str:
        self.devices[code] = zone
        return f"{code} {desc}"

    def hconn(self, a: str, b: str, kind: str) -> tuple[str, str, str, int]:
        """Next free pin on a harness connector between neighbouring zones a, b: (raw, half of a, half of b, pin)."""
        key = (a, b, kind) if (a, b) in LINKS else (b, a, kind)
        h = self.harness.get(key)
        if h is None or h[1] > h[2]:
            k = sum(1 for x in self.hdecl if x.startswith(f"X-{key[0]}{key[1]}-{kind}")) + 1
            code = f"X-{key[0]}{key[1]}-{kind}{k:02d}"
            desc = "signal connector D-SUB 37" if kind == "S" else "power connector circular 19"
            raw = f"{code} {ZONES[key[0]][0].lower()}/{ZONES[key[1]][0].lower()} {desc}"
            h = self.harness[key] = [raw, 1, 37 if kind == "S" else 19]
            self.hdecl[code] = [f"{ZONES[key[0]][0]}/{ZONES[key[1]][0]} {'signal' if kind == 'S' else 'power'} connector {code}",
                                code, ZONES[key[1]][0].lower()]
            self.sides[code] = {f"{ZONES[key[0]][0]} half": "near", f"{ZONES[key[1]][0]} half": "far"}
        p = h[1]; h[1] += 1
        return h[0], f"{ZONES[a][0]} half", f"{ZONES[b][0]} half", p

    @staticmethod
    def path(a: str, b: str) -> list[str]:
        """Zones on the way from a to b (a tree, so a breadth-first search is enough)."""
        adj: dict[str, list[str]] = {}
        for x, y in LINKS: adj.setdefault(x, []).append(y); adj.setdefault(y, []).append(x)
        prev, todo = {a: ""}, [a]
        while todo:
            z = todo.pop(0)
            for y in adj[z]:
                if y not in prev: prev[y] = z; todo.append(y)
        out = [b]
        while out[-1] != a: out.append(prev[out[-1]])
        return out[::-1]

    def run(self, a: tuple[str, str, str], za: str, b: tuple[str, str, str], zb: str, func: str, bus: str, awg: int,
            amps: float = 0, prot: str = "", cls: str = "P", length: float | None = None) -> list[str]:
        """Conductors from terminal a (zone za) to terminal b (zone zb), crossing harness connectors on the way."""
        zs = self.path(za, zb)
        kind = "S" if awg >= 20 and cls in "SVNG" else "P"
        out, cur, cz = [], a, za
        for nz in zs[1:]:
            raw, ha, hb, p = self.hconn(cz, nz, kind)
            out.append(self.wire(cur, (raw, ha, str(p)), func, bus, awg, amps, cz, f"H-{cz}", prot, length, cls))
            cur, cz = (raw, hb, str(p)), nz
        out.append(self.wire(cur, b, func, bus, awg, amps, cz, f"H-{cz}" if len(zs) > 1 else "", prot, length, cls))
        return out

    def ground(self, term: tuple[str, str, str], zone: str, awg: int, amps: float, func: str) -> None:
        """Return from a device terminal to its zone's ground splice (the splice trunks go to GNDB at the end)."""
        g = self.gsplice.get(zone)
        if g is None or g[1] >= 8:
            if g: self.gtrunks.append((zone, g[0], g[2]))
            raw = self.dev(f"SP-G{zone}-{self.nid('gs' + zone)}", f"{ZONES[zone][0].lower()} ground splice", zone)
            g = self.gsplice[zone] = [raw, 0, 0.0]
        g[1] += 1; g[2] += amps
        self.wire(term, (g[0], "Splice", ""), func + " return", "GND", awg, amps, zone, "", "", None, "G")

    @staticmethod
    def gauge_for(rating: float, fuse: bool = False) -> int:
        return max(g for g, r in (FU_MAX if fuse else CB_MAX).items() if r >= rating)

    def breaker(self, bus: str, rating: float, desc: str, loads: list[str], fuse: bool = False) -> str:
        """A breaker (or fuse) on BB1 / BB24 with its feed wire; returns the raw device string."""
        k = self.nid("cb")
        code = f"{'FU' if fuse else 'CB'}-{k:03d}"
        raw = self.dev(code, f"{rating:g} A", "CB")
        bb = BB1 if bus == "14 V" else BB24
        self.wire((bb, "Stud", ""), (raw, "LINE", ""), f"{desc} breaker feed", bus, self.gauge_for(rating), 0, "CB", "", code,
                  0.3, "P" if bus == "14 V" else "T")
        self.P.append(dict(id=code, rating=rating, panel=desc.upper()[:24], loads=loads, kind="fuse" if fuse else "breaker",
                           i_interrupt=3000 if not fuse else 2000))
        return raw

    # ------------------------------------------------------------ circuits
    def backbone(self) -> None:
        self.cur_mod = "ss01_power"
        bat = self.dev("BAT", "battery 14 V", "RR")
        main = self.dev("CB-MAIN", "100 A", "CB")
        self.P.append(dict(id="CB-MAIN", rating=100, panel="MAIN", loads=["BB1"], kind="breaker", i_interrupt=5000))
        self.run((bat, "+", ""), "RR", (main, "LINE", ""), "CB", "Battery feed", "14 V", 4, 0, "", "P", 1.5)
        self.wire((main, "LOAD", ""), (BB1, "Stud", ""), "Main bus feed", "14 V", 4, 0, "CB", "", "CB-MAIN", 0.3)
        self.run((bat, "-", ""), "RR", (GNDB, "Stud", ""), "CB", "Battery return", "GND", 4, 0, "", "G", 1.5)
        cb = self.breaker("14 V", 30, "DC/DC input", ["DCDC1"])
        dc = self.dev("DCDC1", "14/24 V converter", "CB")
        self.wire((cb, "LOAD", ""), (dc, "IN", ""), "DC/DC input", "14 V", 12, 0, "CB", "", cb.split()[0], 0.5)
        self.wire((dc, "OUT", ""), (BB24, "Stud", ""), "24 V bus feed", "24 V", 12, 0, "CB", "", "", 0.5, "T")
        self.wire((dc, "GND", ""), (GNDB, "Stud", ""), "DC/DC return", "GND", 12, 0, "CB", "", "", 0.5, "G")
        self.ctl = self.breaker("14 V", 5, "relay control", [])

    def load(self) -> None:
        self.cur_mod = "ss02_loads"
        fam = self.rng.choice(sorted(LOADS))
        part, desc, model, val, vnom, vmin, bus = LOADS[fam]
        amps = val if model == "constant_current" else val / vnom
        zone = self.rng.choice(sorted(ZONES))
        k = self.nid("ld")
        ld = self.dev(f"LD-{fam}-{k:03d}", desc, zone)
        rating = min(r for r in RATINGS if r >= 1.25 * amps)
        fuse = self.rng.random() < 0.15
        awg = self.gauge_for(rating, fuse)
        cb = self.breaker(bus, rating, f"{desc} {k}", [ld.split()[0]], fuse=fuse)
        code = cb.split()[0]
        src: tuple[str, str, str] = (cb, "LOAD", "")
        cls = "P" if bus == "14 V" else "T"
        mode = self.rng.random()
        if mode < 0.25:  # power switch in line
            sw = self.dev(f"SW-P-{self.nid('swp'):03d}", "power switch", "CB")
            self.wire(src, (sw, "C", "IN"), desc, bus, awg, amps, "CB", "", code, None, cls)
            src = (sw, "C", "OUT")
        elif mode < 0.45:  # relay, coil from a control switch
            rl = self.dev(f"K-{self.nid('k'):03d}", "relay", "CB")
            self.wire(src, (rl, "C", "COM"), desc, bus, awg, amps, "CB", "", code, None, cls)
            src = (rl, "C", "NO")
            if not self.ctl_splice or self.ctl_count >= 6:
                self.ctl_splice = self.dev(f"SP-CTL-{self.nid('spc')}", "relay control splice", "CB")
                self.wire((self.ctl, "LOAD", ""), (self.ctl_splice, "Splice", ""), "Relay control", "14 V", 22, 0, "CB", "",
                          self.ctl.split()[0], 0.3)
                self.ctl_count = 0
            self.ctl_count += 1
            cs = self.dev(f"SW-C-{self.nid('swc'):03d}", "control switch", "CB")
            self.wire((self.ctl_splice, "Splice", ""), (cs, "C", "IN"), "Relay control", "14 V", 22, 0.165, "CB", "",
                      self.ctl.split()[0], 0.4)
            self.wire((cs, "C", "OUT"), (rl, "COIL", "A1"), "Relay coil", "14 V", 22, 0.165, "CB", "", self.ctl.split()[0], 0.4)
            self.ground((rl, "COIL", "A2"), "CB", 22, 0.165, "Relay coil")
        self.run(src, "CB", (ld, "P1", "1"), zone, desc, bus, awg, amps, code, cls)
        self.ground((ld, "P1", "2"), zone, awg, amps, desc)

    def ecu(self, zone: str) -> dict[str, Any]:
        self.cur_mod = "ss03_control"
        k = self.nid("ecu")
        e = self.dev(f"ECU-{k:02d}", "control unit", zone)
        cb = self.breaker("14 V", 3, f"ECU {k}", [e.split()[0]])
        self.run((cb, "LOAD", ""), "CB", (e, "J1", "1"), zone, f"ECU {k} supply", "14 V", 22, 0.43, cb.split()[0])
        self.ground((e, "J1", "2"), zone, 22, 0.43, f"ECU {k} supply")
        return dict(raw=e, zone=zone, ai=1, di=1)

    def sensor(self, ecu: dict[str, Any]) -> None:
        self.cur_mod = "ss04_sensors"
        zone = self.rng.choice(["FR", "EN", "RR", ecu["zone"]])
        s = self.dev(f"S-{self.nid('s'):03d}", "pressure sensor", zone)
        ch, e, ez = ecu["ai"], ecu["raw"], ecu["zone"]
        ecu["ai"] += 1
        self.run((e, "J2", f"5V{ch}"), ez, (s, "P1", "1"), zone, f"{s.split()[0]} supply", "5 V", 22, 0.01, "", "V")
        self.run((s, "P1", "2"), zone, (e, "J2", f"AI{ch}"), ez, f"{s.split()[0]} signal", "—", 22, 0, "", "S")
        self.run((s, "P1", "3"), zone, (e, "J2", f"AG{ch}"), ez, f"{s.split()[0]} ground", "GND", 22, 0.01, "", "G")

    def switch_input(self, ecu: dict[str, Any]) -> None:
        self.cur_mod = "ss05_switches"
        zone = self.rng.choice(["FR", "CB", "RF"])
        sw = self.dev(f"SW-I-{self.nid('swi'):03d}", "input switch", zone)
        ch = ecu["di"]; ecu["di"] += 1
        self.run((sw, "C", "A"), zone, (ecu["raw"], "J3", f"DI{ch}"), ecu["zone"], f"{sw.split()[0]} input", "—", 22, 0, "", "S")
        self.ground((sw, "C", "B"), zone, 22, 0, f"{sw.split()[0]} input")

    def can(self, nodes: list[tuple[str, str]], bus_no: int) -> None:
        """A CAN bus in node order with a terminator plug at each end; one node per bus is on a short splice stub."""
        self.cur_mod = "ss06_can"
        t1 = self.dev(f"TR-{self.nid('tr'):02d}", "CAN terminator", nodes[0][1])
        t2 = self.dev(f"TR-{self.nid('tr'):02d}", "CAN terminator", nodes[-1][1])
        chain = [((t1, "J", "H"), (t1, "J", "L"), nodes[0][1])]
        chain += [((raw, "J1", "3"), (raw, "J1", "4"), z) for raw, z in nodes]
        chain += [((t2, "J", "H"), (t2, "J", "L"), nodes[-1][1])]
        stub = 2 if len(chain) > 4 else 0
        for i in range(len(chain) - 1):
            (ah, al, za), (bh, bl, zb) = chain[i], chain[i + 1]
            if stub and i + 1 == stub:  # node chain[stub] hangs off a splice pair in its own zone
                sh = self.dev(f"SP-CAN{bus_no}H-{i}", f"CAN{bus_no} H splice", zb)
                sl = self.dev(f"SP-CAN{bus_no}L-{i}", f"CAN{bus_no} L splice", zb)
                nh, nl, nz = chain[i + 2]
                for (a, s, n, x) in ((ah, sh, nh, "H"), (al, sl, nl, "L")):
                    self.run(a, za, (s, "Splice", ""), zb, f"CAN{bus_no} CAN_{x}", "—", 22, 0, "", "N", 1.0)
                    self.wire((s, "Splice", ""), bh if x == "H" else bl, f"CAN{bus_no} CAN_{x}", "—", 22, 0, zb, "", "", 0.3, "N")
                    self.run((s, "Splice", ""), zb, n, nz, f"CAN{bus_no} CAN_{x}", "—", 22, 0, "", "N", 1.0)
                continue
            if stub and i == stub: continue  # already wired through the splice
            self.run(ah, za, bh, zb, f"CAN{bus_no} CAN_H", "—", 22, 0, "", "N", 1.0)
            self.run(al, za, bl, zb, f"CAN{bus_no} CAN_L", "—", 22, 0, "", "N", 1.0)

    def finish(self) -> None:
        self.cur_mod = "ss01_power"
        for z, g in sorted(self.gsplice.items()): self.gtrunks.append((z, g[0], g[2]))
        self.gsplice = {}
        for z, raw, amps in self.gtrunks:
            awg = min(self.gauge_for(min(r for r in [*RATINGS, 30, 40, 50] if r >= max(1.25 * amps, 3))), 16)
            self.run((raw, "Splice", ""), z, (GNDB, "Stud", ""), "CB", "Ground trunk", "GND", awg, amps, "", "G")
        while self.total < self.n:  # exact count: structure ground straps
            k = self.nid("str")
            st = self.dev(f"STR-{k:03d}", "structure ground stud", "CB")
            self.wire((st, "Stud", ""), (GNDB, "Stud", ""), "Structure bond", "GND", 12, 0, "CB", "", "", 0.3, "G")


BB1, BB24, GNDB = "BB1 14 V bus bar", "BB24 24 V bus bar", "GNDB ground bus"


def generate(n: int, seed: int) -> Synth:
    """Build the rows; n is the exact number of conductors."""
    s = Synth(n, random.Random(seed))
    s.backbone()
    nb = max(1, n // 500)
    ecus = [s.ecu("CB" if i % 2 == 0 else "EN") for i in range(max(2, n // 70))]
    dsps = []
    for i in range(nb):
        s.cur_mod = "ss06_can"
        k = s.nid("dsp")
        d = s.dev(f"DSP-{k:02d}", "display", "CB")
        cb = s.breaker("14 V", 3, f"display {k}", [d.split()[0]])
        s.run((cb, "LOAD", ""), "CB", (d, "J1", "1"), "CB", f"Display {k} supply", "14 V", 22, 0.71, cb.split()[0])
        s.ground((d, "J1", "2"), "CB", 22, 0.71, f"Display {k} supply")
        dsps.append((d, "CB"))
    for b in range(nb):
        mine = [(e["raw"], e["zone"]) for e in ecus[b::nb]]
        s.can([dsps[b]] + mine, b + 1)
    def pending() -> int:  # ground trunk conductors still to come
        return sum(len(s.path(z, "CB")) for z in s.gsplice) + sum(len(s.path(z, "CB")) for z, _, _ in s.gtrunks)
    while s.total + pending() + 16 < n:
        r = s.rng.random()
        free_ai = [e for e in ecus if e["ai"] <= 8]
        free_di = [e for e in ecus if e["di"] <= 8]
        if r < 0.45: s.load()
        elif r < 0.75 and free_ai: s.sensor(s.rng.choice(free_ai))
        elif free_di: s.switch_input(s.rng.choice(free_di))
        else: s.load()
    s.finish()
    if s.total > n: raise SystemExit(f"--wires {n} is too small for a complete project (needs at least {s.total})")
    return s


CARDS: dict[str, dict[str, Any]] = {
    "battery": dict(device="^BAT$", part="SV-BAT-40AH", kind="battery", source=dict(v_oc=13.2, r_int=0.01),
                    connectors=[dict(id="+", match=r"^\+$", type="power_out", i_max=200),
                                dict(id="-", match="^-$", type="ground", i_max=200)]),
    "dcdc": dict(device="^DCDC1$", part="SV-DCDC-24V-15A", kind="dcdc", source=dict(v_out=24.0, i_limit=15.0, r_out=0.01, efficiency=0.9),
                 connectors=[dict(id="IN", match="^IN$", type="power_in", i_max=40), dict(id="OUT", match="^OUT$", type="power_out", i_max=40),
                             dict(id="GND", match="^GND$", type="ground", i_max=40)]),
    "breaker": dict(device="^CB-", part="SV-CB", kind="breaker", trip_curve=[[1.15, 3600], [1.5, 60], [2, 12], [5, 1.5], [10, 0.02]],
                    connectors=[dict(id="LINE", match="^LINE$", type="power_in"), dict(id="LOAD", match="^LOAD$", type="power_out")]),
    "fuse": dict(device="^FU-", part="SV-FUSE", kind="fuse", trip_curve=[[1.35, 3600], [2, 5], [5, 0.1], [10, 0.005]],
                 connectors=[dict(id="LINE", match="^LINE$", type="power_in"), dict(id="LOAD", match="^LOAD$", type="power_out")]),
    "relay": dict(device="^K-", part="SV-RELAY-14V", kind="relay", coil=dict(a1="COIL.A1", a2="COIL.A2", r=85, v_pickup=8.4, v_dropout=3.0),
                  contacts=[dict(com="C.COM", no="C.NO")],
                  connectors=[dict(id="C", match="^C$", pins=[dict(n="COM", type="power_in", i_max=30, awg=[10, 22]),
                                                               dict(n="NO", type="power_out", i_max=30, awg=[10, 22])]),
                              dict(id="COIL", match="^COIL$", pins=[dict(n="A1", type="power_in", i_max=1, awg=[18, 24]),
                                                                    dict(n="A2", type="ground", i_max=1, awg=[18, 24])])]),
    "pswitch": dict(device="^SW-[PC]-", part="SV-SWITCH-20A", kind="switch", contacts=[dict(a="C.IN", b="C.OUT")],
                    connectors=[dict(id="C", match="^C$", pins=[dict(n="IN", type="power_in", i_max=20, awg=[12, 22]),
                                                                 dict(n="OUT", type="power_out", i_max=20, awg=[12, 22])])]),
    "iswitch": dict(device="^SW-I-", part="SV-SWITCH-SIG", kind="switch", contacts=[dict(a="C.A", b="C.B")],
                    connectors=[dict(id="C", match="^C$", pins=[dict(n="A", type="signal_out", i_max=1, awg=[20, 24]),
                                                                 dict(n="B", type="ground", i_max=1, awg=[20, 24])])]),
    "ecu": dict(device=r"^ECU-\d+$", part="SV-ECU-8", kind="controller", load=dict(model="constant_power", p_w=6, v_min=9),
                supply_out=dict(v=5.0, i_limit=0.2, r_out=0.05), controller=True,
                connectors=[dict(id="J1", match="^J1$", pins=[dict(n=1, name="VBAT", type="power_in", i_max=5, awg=[18, 24], required=True),
                                                               dict(n=2, name="GND", type="ground", i_max=5, awg=[18, 24], required=True),
                                                               dict(n=3, name="CAN_H", type="can_h", awg=[20, 24]),
                                                               dict(n=4, name="CAN_L", type="can_l", awg=[20, 24])]),
                            dict(id="J2", match="^J2$", pins=[dict(n=f"{k}{i}", name=f"{k}{i}", type=t, i_max=0.1, awg=[20, 24])
                                                               for i in range(1, 9) for k, t in (("5V", "power_out"), ("AI", "signal_in"), ("AG", "ground"))]),
                            dict(id="J3", match="^J3$", pins=[dict(n=f"DI{i}", name=f"DI{i}", type="signal_in", i_max=0.1, awg=[20, 24])
                                                               for i in range(1, 9)])]),
    "display": dict(device=r"^DSP-\d+$", part="SV-DISPLAY", kind="device", load=dict(model="constant_power", p_w=10, v_min=9),
                    connectors=[dict(id="J1", match="^J1$", pins=[dict(n=1, name="VBAT", type="power_in", i_max=3, awg=[18, 24], required=True),
                                                                   dict(n=2, name="GND", type="ground", i_max=3, awg=[18, 24], required=True),
                                                                   dict(n=3, name="CAN_H", type="can_h", awg=[20, 24]),
                                                                   dict(n=4, name="CAN_L", type="can_l", awg=[20, 24])])]),
    "sensor": dict(device=r"^S-\d+$", part="SV-PRESSURE", kind="sensor", load=dict(model="constant_current", i_a=0.01, v_min=4.5),
                   connectors=[dict(id="P1", match="^P1$", pins=[dict(n=1, name="SUPPLY", type="power_in", i_max=0.1, awg=[20, 24]),
                                                                  dict(n=2, name="OUT", type="signal_out", i_max=0.1, awg=[20, 24]),
                                                                  dict(n=3, name="GND", type="ground", i_max=0.1, awg=[20, 24])])]),
    "terminator": dict(device=r"^TR-\d+$", part="SV-CAN-TERM", kind="terminator", term=True,
                       connectors=[dict(id="J", match="^J$", pins=[dict(n="H", name="CAN_H", type="can_h", term=True, awg=[20, 24]),
                                                                    dict(n="L", name="CAN_L", type="can_l", term=True, awg=[20, 24])])]),
}


def load_cards() -> dict[str, dict[str, Any]]:
    out = dict(CARDS)
    for fam, (part, desc, model, val, vnom, vmin, bus) in LOADS.items():
        ld: dict[str, Any] = dict(model=model, v_min=vmin, v_nom=vnom)
        ld["i_a" if model == "constant_current" else "p_w"] = val
        out["load_" + fam] = dict(device=f"^LD-{fam}-\\d+$", part=part, kind="load", load=ld,
                                  connectors=[dict(id="P1", match="^P1$", pins=[dict(n=1, name="SUPPLY", type="power_in", i_max=20, awg=[12, 22], required=True),
                                                                                 dict(n=2, name="GND", type="ground", i_max=20, awg=[12, 22], required=True)])])
    return out


SCENARIOS = {
    "normal": dict(scenario="normal operation, all switches on", set={"*SW-P-*": "closed", "*SW-C-*": "closed"},
                   expect=dict(no_trip=True, min_voltage={"BB1": 12.0, "BB24": 23.0})),
    "switches_off": dict(scenario="all switches off", set={"*SW-P-*": "open", "*SW-C-*": "open"}, expect=dict(no_trip=True)),
}


def write(s: Synth, out: Path, seed: int) -> None:
    """Write the project folder."""
    wl = out / "wirelist"; cards = out / "cards"; sc = out / "scenarios"
    for d in (wl, cards, sc): d.mkdir(parents=True, exist_ok=True)
    mods = dict(s.rows)
    head = f'"""Synthetic wire list (fictional vehicle), generated by schemagen synth --wires {s.n} --seed {seed}."""\n'
    for name in sorted(set(mods) | {"ss00_records"}):
        rows = mods.get(name, [])
        body = [head, f"SUBSYSTEM = ({name[:4].upper()!r}, {name[5:]!r})\n", "R = [\n"]
        body += [f"    {r!r},\n" for r in rows]
        body.append("]\n")
        if name == "ss01_power": body.append("P = [\n" + "".join(f"    {p!r},\n" for p in s.P) + "]\n")
        if name == "ss00_records":
            D = [dict(id="D-001", date="2026-01-12", text="D-SUB signal connectors carry 20 AWG and lighter only", by="systems"),
                 dict(id="D-002", date="2026-02-03", text="Every load returns through its zone ground splice", by="systems")]
            O = [dict(id="O-001", text="Confirm the roof harness routing", status="open", owner="wiring", objects=["X-CBRF-P01"]),
                 dict(id="O-002", text="Check DC/DC current limit against inrush", status="closed", owner="power", objects=["DCDC1"])]
            body.append(f"D = {D!r}\nO = {O!r}\n")
        (wl / f"{name}.py").write_text("".join(body), encoding="utf-8")
    (wl / "labels.json").write_text(json.dumps(s.labels, indent=0), encoding="utf-8")
    for k, c in sorted(load_cards().items()):
        blk = yaml.safe_dump(c, sort_keys=False, default_flow_style=None, width=150)
        (cards / f"{k}.md").write_text(f"# Interface card: synthetic {k} (fictional)\n\n```yaml schemagen\n{blk}```\n", encoding="utf-8")
    with open(out / "lengths.csv", "w", encoding="utf-8") as fh:
        fh.write("label,length_m\n" + "".join(f"{k},{v}\n" for k, v in sorted(s.lengths.items())))
    for k, v in SCENARIOS.items():
        (sc / f"{k}.yml").write_text(yaml.safe_dump(v, sort_keys=False), encoding="utf-8")
    cfg = dict(wirelist="wirelist", cards="cards", out="out", lengths="lengths.csv", default_harnesses=[],
               buses=["GNDB", "BB1", "BB24"], breaker_prefixes=["CB-", "FU-"], splice_prefix="SP-",
               switch_prefixes=["SW-"], relay_prefixes=["K-"],
               harnesses=dict(sorted(s.hdecl.items())), sides=dict(sorted(s.sides.items())),
               zones={k: dict(name=v[0], xy=[v[1], v[2]]) for k, v in ZONES.items()})
    (out / "schemagen.yml").write_text("# Synthetic project (fictional), generated by schemagen synth.\n"
                                       + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main(n: int, seed: int, out: str) -> int:
    s = generate(n, seed)
    write(s, Path(out), seed)
    print(f"{s.total} wires, {len(s.P)} protective devices, {len(s.hdecl)} harness connectors -> {out}")
    return s.total
