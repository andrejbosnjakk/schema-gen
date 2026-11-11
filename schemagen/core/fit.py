"""One sentence for one fault: a wire whose gauge does not fit its protective device. The check rule and the app's Simulate
overlay both use this, and the framing comes from the sheet only: the wire's listed current above what its gauge may
carry behind that device means the wire is too thin; otherwise the breaker is too big for the wire.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import tables
from .model import Conductor, ProtectiveDevice


@dataclass
class Fit:
    too_small: bool   # the wire is too thin (else the protector is too big)
    title: str        # short sentence, display names only
    detail: str       # one sentence with the numbers, no standard
    source: str       # the standard the limit comes from
    limit: float      # most the gauge may carry (and be protected with) behind this kind of protector, A
    note: str         # extra remark ("lighter than the lightest tabled gauge")
    fix: str


def device_name(pd: ProtectiveDevice, name: str = "") -> str:
    """"10 A LANDING LT breaker" from the protector's rating and its display name ("Breaker 'LANDING LT' 10 A")."""
    q = re.search(r"'([^']+)'", name or "")
    label = q.group(1) if q else re.sub(r"(?i)\b(breaker|fuse)\b|\d+(\.\d+)?\s*A\b", "", name or "")
    label = " ".join(label.split()) or pd.id
    return f"{pd.rating_a:g} A {label} {pd.kind}"


def gauge_fit(c: Conductor, pd: ProtectiveDevice, name: str = "", cfg: Any = None) -> Fit | None:
    """None when the wire fits (or there is nothing to judge); else the finding."""
    if c.awg is None or pd.rating_a is None: return None
    mx, note = tables.max_rating(c.awg, pd.kind, cfg), ""
    if mx is None:  # lighter than every gauge in the table: hold it to the lightest one
        light = tables.lightest(pd.kind, cfg)
        if light is None or c.awg <= light[0]: return None
        mx, note = light[1], f"lighter than the lightest tabled gauge, {light[0]} AWG"
    if pd.rating_a <= mx: return None
    src, dev = str(tables.table("protection", cfg)["source"]), device_name(pd, name)
    small = c.current_a is not None and c.current_a > mx
    if small:
        return Fit(True, f"{c.label} is too thin for the {dev}",
                   f"{c.label} is {c.awg} AWG and carries {c.current_a:g} A, more than the {mx:g} A it may carry behind the {dev}",
                   src, mx, note, "use a heavier gauge, or a smaller protector")
    carry = f"; the wire carries only {c.current_a:g} A" if c.current_a is not None else ""
    return Fit(False, f"The {dev} is too big for wire {c.label} ({c.awg} AWG, max {mx:g} A)",
               f"The {dev} is above the {mx:g} A that {c.label} ({c.awg} AWG) may be protected with{carry}", src, mx, note,
               f"use a {pd.kind} of {mx:g} A or less, or a heavier gauge")
