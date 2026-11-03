"""DC operating point by modified nodal analysis (scipy sparse), with Newton iteration for constant-power and
constant-current loads and current-limited sources, and a fixed-point loop for relay coils.

A Circuit holds named nodes ("0" is the reference) and elements. `solve()` returns node voltages and element
currents and checks Kirchhoff's current law at every node.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
import numpy as np
import numpy.typing as npt
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu

Vec = npt.NDArray[np.float64]
REF = "0"


@dataclass
class Resistor:
    name: str
    a: str
    b: str
    r: float
    kind: str = "wire"         # wire, contact, breaker, switch, coil, fault, internal
    ref: str = ""              # object reference (conductor:W1, protective:CB-1, ...)


@dataclass
class Source:
    """Voltage source v between p (+) and m (-) with series resistance rs (0 = ideal) and optional current limit."""
    name: str
    p: str
    m: str
    v: float
    rs: float = 0.0
    i_limit: float | None = None
    ref: str = ""
    limited: bool = False      # solver state: running at its current limit


@dataclass
class Load:
    """A load from a to b: constant_power (value W), constant_current (A) or resistive (ohm), with a minimum
    operating voltage. Below v_knee it behaves resistively so the model stays continuous."""
    name: str
    a: str
    b: str
    model: str
    value: float
    v_min: float = 0.0
    v_knee: float = 1.0
    ref: str = ""
    dcdc_of: str = ""          # constant-power input of a DC/DC converter: P = P_out(source) / efficiency
    efficiency: float = 1.0

    def current(self, v: float) -> tuple[float, float]:
        """(I, dI/dV) at voltage v across the load."""
        if self.model == "resistive": return v / self.value, 1 / self.value
        k = max(self.v_knee, 1e-6)
        if self.model == "constant_power":
            if v >= k: return self.value / v, -self.value / v ** 2
            g = self.value / k ** 2
            return g * v, g
        if v >= k: return self.value, 0.0
        return self.value * v / k, self.value / k


@dataclass
class Result:
    v: dict[str, float]
    i: dict[str, float]                    # element name -> current (resistors a->b, sources delivered out of p, loads a->b)
    iterations: int
    residual: float                        # largest KCL residual over all nodes, A
    converged: bool
    message: str = ""
    limited: list[str] = field(default_factory=list)
    relay_rounds: int = 0
    relay_states: dict[str, bool] = field(default_factory=dict)
    oscillating: list[str] = field(default_factory=list)


class SimError(Exception):
    pass


@dataclass
class Relay:
    """A coil (resistor element `coil`) that closes the `no` contacts and opens the `nc` contacts at pick-up."""
    name: str
    coil: str
    v_pickup: float
    v_dropout: float
    no: list[str] = field(default_factory=list)   # resistor names closed when energised
    nc: list[str] = field(default_factory=list)   # resistor names closed when not energised


class Circuit:
    def __init__(self, gmin: float = 1e-12):
        self.res: list[Resistor] = []
        self.src: list[Source] = []
        self.loads: list[Load] = []
        self.relays: list[Relay] = []
        self.gmin = gmin
        self.off: set[str] = set()            # elements switched out (open contacts, failed sources, loads off)

    # ---------------------------------------------------------------- building
    def r(self, name: str, a: str, b: str, r: float, kind: str = "wire", ref: str = "") -> Resistor:
        x = Resistor(name, a, b, max(r, 1e-9), kind, ref); self.res.append(x); return x

    def vsrc(self, name: str, p: str, m: str, v: float, rs: float = 0.0, i_limit: float | None = None, ref: str = "") -> Source:
        x = Source(name, p, m, v, rs, i_limit, ref); self.src.append(x); return x

    def load(self, name: str, a: str, b: str, model: str, value: float, v_min: float = 0.0, v_knee: float | None = None, ref: str = "") -> Load:
        k = v_knee if v_knee is not None else (v_min if v_min > 0 else 1.0)
        x = Load(name, a, b, model, value, v_min, k, ref); self.loads.append(x); return x

    def nodes(self) -> list[str]:
        out: dict[str, None] = {}
        for r in self.res: out[r.a] = None; out[r.b] = None
        for s in self.src: out[s.p] = None; out[s.m] = None
        for ld in self.loads: out[ld.a] = None; out[ld.b] = None
        out.pop(REF, None)
        return list(out)

    # ---------------------------------------------------------------- solving
    def solve(self, max_iter: int = 50, tol_v: float = 1e-10, tol_i: float = 1e-11, x0: dict[str, float] | None = None) -> Result:
        """Operating point. Relay coils are iterated to a fixed point (oscillation is reported, not hidden)."""
        states = {rl.name: False for rl in self.relays}
        seen: list[dict[str, bool]] = []
        res: Result | None = None
        for rounds in range(1, 21):
            self._apply_relays(states)
            res = self._newton(max_iter, tol_v, tol_i, x0 if res is None else res.v)
            new = {}
            for rl in self.relays:
                c = next(r for r in self.res if r.name == rl.coil)
                vc = abs(res.v.get(c.a, 0.0) - res.v.get(c.b, 0.0)) if c.name not in self.off else 0.0
                new[rl.name] = vc >= rl.v_pickup if not states[rl.name] else vc > rl.v_dropout
            res.relay_rounds, res.relay_states = rounds, dict(new)
            if new == states: return res
            if new in seen:
                res.oscillating = sorted(k for k in new if any(s[k] != new[k] for s in seen))
                res.message = f"relay coils oscillate: {', '.join(res.oscillating)} (no stable contact state)"
                res.converged = False
                return res
            seen.append(dict(states)); states = new
        assert res is not None
        res.converged, res.message = False, "relay states did not settle in 20 rounds"
        return res

    def _apply_relays(self, states: dict[str, bool]) -> None:
        for rl in self.relays:
            on = states[rl.name]
            for n in rl.no: (self.off.discard if on else self.off.add)(n)
            for n in rl.nc: (self.off.add if on else self.off.discard)(n)

    def _newton(self, max_iter: int, tol_v: float, tol_i: float, x0: dict[str, float] | None) -> Result:
        names = self.nodes()
        idx = {n: k for k, n in enumerate(names)}
        n = len(names)
        ideal = [s for s in self.src if s.name not in self.off and s.rs <= 0]
        m = n + len(ideal)
        if n == 0: return Result({REF: 0.0}, {}, 0, 0.0, True)
        rows: list[int] = []; cols: list[int] = []; vals: list[float] = []
        rhs0 = np.zeros(m)

        def g2(a: str, b: str, g: float, rr: list[int], cc: list[int], vv: list[float]) -> None:
            ia, ib = idx.get(a), idx.get(b)
            if ia is not None: rr.append(ia); cc.append(ia); vv.append(g)
            if ib is not None: rr.append(ib); cc.append(ib); vv.append(g)
            if ia is not None and ib is not None: rr += [ia, ib]; cc += [ib, ia]; vv += [-g, -g]

        def inj(node: str, i: float, rhs: Vec) -> None:  # current i injected into node
            k = idx.get(node)
            if k is not None: rhs[k] += i

        for r in self.res:
            if r.name not in self.off: g2(r.a, r.b, 1 / r.r, rows, cols, vals)
        for k in range(n): rows.append(k); cols.append(k); vals.append(self.gmin)
        for j, s in enumerate(ideal):
            for node, sg in ((s.p, 1.0), (s.m, -1.0)):
                kn = idx.get(node)
                if kn is not None: rows += [kn, n + j]; cols += [n + j, kn]; vals += [sg, sg]
            rhs0[n + j] = s.v
        thev = [s for s in self.src if s.name not in self.off and s.rs > 0]
        for s in thev: g2(s.p, s.m, 1 / s.rs, rows, cols, vals)
        loads = [ld for ld in self.loads if ld.name not in self.off]
        x = np.zeros(m)
        if x0:
            for nm, k in idx.items(): x[k] = x0.get(nm, 0.0)
        else:  # start from nominal resistive loads
            pass
        it, msg, conv = 0, "", False
        for s in thev: s.limited = False
        for it in range(1, max_iter + 1):
            rr, cc, vv = list(rows), list(cols), list(vals)
            rhs = rhs0.copy()
            for s in thev:
                if s.limited and s.i_limit is not None:
                    # at the limit: a current source; the series conductance is removed again
                    g2(s.p, s.m, -1 / s.rs, rr, cc, vv); inj(s.p, s.i_limit, rhs); inj(s.m, -s.i_limit, rhs)
                else: inj(s.p, s.v / s.rs, rhs); inj(s.m, -s.v / s.rs, rhs)
            vx = self._volts(x, idx)
            pout = self._pout(vx, thev)
            for ld in loads:
                if ld.dcdc_of: ld.value = max(pout.get(ld.dcdc_of, 0.0), 0.0) / max(ld.efficiency, 1e-6)
                v = vx.get(ld.a, 0.0) - vx.get(ld.b, 0.0)
                if it == 1 and not x0 and ld.model != "resistive":  # first guess: a resistor at the knee
                    g = (ld.value / ld.v_knee ** 2) if ld.model == "constant_power" else ld.value / ld.v_knee
                    i0 = 0.0
                else:
                    i0, g = ld.current(v); i0 = i0 - g * v
                g2(ld.a, ld.b, g, rr, cc, vv); inj(ld.a, -i0, rhs); inj(ld.b, i0, rhs)
            A = csc_matrix((vv, (rr, cc)), shape=(m, m))
            try: xn = splu(A).solve(rhs)
            except RuntimeError as e: raise SimError(f"singular circuit matrix: {e}") from e
            if not np.all(np.isfinite(xn)): raise SimError("the solution is not finite (a source shorted by an ideal element?)")
            dv = float(np.max(np.abs(xn - x))) if m else 0.0
            x = xn
            vx = self._volts(x, idx)
            changed = False
            for s in thev:
                if s.i_limit is None: continue
                vt = vx.get(s.p, 0.0) - vx.get(s.m, 0.0)
                if not s.limited and (s.v - vt) / s.rs > s.i_limit * (1 + 1e-12): s.limited = changed = True
                elif s.limited and vt > s.v - s.i_limit * s.rs: s.limited = False; changed = True
            if it > 1 and dv < tol_v * (1 + float(np.max(np.abs(x)))) and not changed:
                cur = self._currents(vx, x, ideal, n)
                resid = self.kcl(vx, cur)
                if resid < tol_i or dv == 0.0: conv = True; break
        else:
            msg = f"Newton did not converge in {max_iter} iterations"
        vx = self._volts(x, idx)
        cur = self._currents(vx, x, ideal, n)
        return Result(vx, cur, it, self.kcl(vx, cur), conv, msg, [s.name for s in thev if s.limited])

    @staticmethod
    def _volts(x: Vec, idx: dict[str, int]) -> dict[str, float]:
        v = {nm: float(x[k]) for nm, k in idx.items()}; v[REF] = 0.0
        return v

    def _pout(self, v: dict[str, float], thev: list[Source]) -> dict[str, float]:
        out = {}
        for s in thev:
            vt = v.get(s.p, 0.0) - v.get(s.m, 0.0)
            i = s.i_limit if s.limited and s.i_limit is not None else (s.v - vt) / s.rs
            out[s.name] = vt * i
        return out

    def _currents(self, v: dict[str, float], x: Vec, ideal: list[Source], n: int) -> dict[str, float]:
        cur: dict[str, float] = {}
        for r in self.res:
            cur[r.name] = 0.0 if r.name in self.off else (v.get(r.a, 0.0) - v.get(r.b, 0.0)) / r.r
        for j, s in enumerate(ideal): cur[s.name] = -float(x[n + j])
        for s in self.src:
            if s.name in self.off: cur[s.name] = 0.0
            elif s.rs > 0:
                vt = v.get(s.p, 0.0) - v.get(s.m, 0.0)
                cur[s.name] = s.i_limit if s.limited and s.i_limit is not None else (s.v - vt) / s.rs
        for ld in self.loads:
            cur[ld.name] = 0.0 if ld.name in self.off else ld.current(v.get(ld.a, 0.0) - v.get(ld.b, 0.0))[0]
        return cur

    def kcl(self, v: dict[str, float], cur: dict[str, float]) -> float:
        """Largest |sum of currents| over all non-reference nodes (element currents recomputed from the solution)."""
        s: dict[str, float] = {nm: -self.gmin * v.get(nm, 0.0) for nm in self.nodes()}
        def add(node: str, i: float) -> None:
            if node in s: s[node] += i
        for r in self.res:
            if r.name in self.off: continue
            add(r.a, -cur[r.name]); add(r.b, cur[r.name])
        for src in self.src:
            if src.name in self.off: continue
            add(src.p, cur[src.name]); add(src.m, -cur[src.name])
        for ld in self.loads:
            if ld.name in self.off: continue
            add(ld.a, -cur[ld.name]); add(ld.b, cur[ld.name])
        return max((abs(x) for x in s.values()), default=0.0)


def trip_time(multiple: float, curve: list[tuple[float, float]]) -> float:
    """Seconds to trip at `multiple` x rating, log-log interpolated on the curve; inf below its first point."""
    pts = sorted(curve)
    if not pts or multiple < pts[0][0]: return math.inf
    if multiple >= pts[-1][0]: return pts[-1][1]
    for (m1, t1), (m2, t2) in zip(pts, pts[1:]):
        if m1 <= multiple <= m2:
            f = (math.log(multiple) - math.log(m1)) / (math.log(m2) - math.log(m1))
            return math.exp(math.log(t1) + f * (math.log(t2) - math.log(t1)))
    return pts[-1][1]


def spice(c: Circuit) -> str:
    """The circuit as an ngspice netlist (for cross-checks): resistors, sources, loads as behavioural current sources."""
    nm: dict[str, str] = {REF: "0"}
    def N(x: str) -> str:
        if x not in nm: nm[x] = f"n{len(nm)}"
        return nm[x]
    lines = ["* schemagen"]
    for r in c.res:
        if r.name not in c.off: lines.append(f"R{len(lines)} {N(r.a)} {N(r.b)} {r.r:.12g}")
    for s in c.src:
        if s.name in c.off: continue
        if s.rs > 0:
            mid = f"{s.name}_int"; lines.append(f"V{len(lines)} {N(mid)} {N(s.m)} DC {s.v:.12g}"); lines.append(f"R{len(lines)} {N(s.p)} {N(mid)} {s.rs:.12g}")
        else: lines.append(f"V{len(lines)} {N(s.p)} {N(s.m)} DC {s.v:.12g}")
    for ld in c.loads:
        if ld.name in c.off: continue
        a, b = N(ld.a), N(ld.b)
        if ld.model == "resistive": lines.append(f"R{len(lines)} {a} {b} {ld.value:.12g}")
        elif ld.model == "constant_power":
            k = ld.v_knee
            lines.append(f"B{len(lines)} {a} {b} I = (V({a},{b}) >= {k}) ? {ld.value}/V({a},{b}) : {ld.value / k ** 2}*V({a},{b})")
        else:
            lines.append(f"B{len(lines)} {a} {b} I = (V({a},{b}) >= {ld.v_knee}) ? {ld.value} : {ld.value / ld.v_knee}*V({a},{b})")
    lines += [".op", ".end"]
    return "\n".join(lines) + "\n"


def spice_nodes(c: Circuit) -> dict[str, str]:
    """Node name -> netlist node, in the order spice() numbers them."""
    out: dict[str, str] = {REF: "0"}
    def N(x: str) -> None:
        if x not in out: out[x] = f"n{len(out)}"
    for r in c.res:
        if r.name not in c.off: N(r.a); N(r.b)
    for s in c.src:
        if s.name in c.off: continue
        if s.rs > 0: N(f"{s.name}_int"); N(s.m); N(s.p)
        else: N(s.p); N(s.m)
    for ld in c.loads:
        if ld.name not in c.off: N(ld.a); N(ld.b)
    return out

