"""Typed, lossless project model (Pydantic v2). Every view, check and the simulation read from this.

Input fields that have no place in a model field are kept in `extra` (nothing is dropped silently). Fields marked
"resolved" are derived on import (from the config, labels.json, display names) and stored so that every consumer
sees the same value; exporters write the input fields, importers recompute the resolved ones.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

SCHEMA_VERSION = "0.5"

PinType = Literal["power_in", "power_out", "ground", "signal_in", "signal_out", "bidir", "can_h", "can_l", "shield", "passive"]
PIN_TYPES: tuple[str, ...] = PinType.__args__  # type: ignore[attr-defined]
Kind = Literal["device", "load", "sensor", "controller", "switch", "relay", "battery", "dcdc", "breaker", "fuse",
               "terminator", "splice", "bus", "harness"]
KINDS: tuple[str, ...] = Kind.__args__  # type: ignore[attr-defined]
Severity = Literal["error", "warning", "info"]
Side = Literal["near", "far", ""]
Provenance = Literal["measured", "datasheet", "assumed", "estimated", "design", "default"]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_assignment=False)


class Source(Base):
    """Where a value comes from: a document and a page."""
    doc: str
    page: str = ""

    def text(self) -> str:
        return f"{self.doc} p. {self.page}" if self.page else self.doc


class Terminal(Base):
    """One end of a conductor: device string, connector (or half name on a harness connector), pin."""
    device: str
    connector: str = ""
    pin: str = ""
    side: Side = ""  # harness connector ends only (resolved: explicit, or guessed with a warning)

    def key(self) -> tuple[str, str, str]:
        return (self.device, self.connector, self.pin)


class PinDef(Base):
    n: str
    name: str = ""
    type: PinType | None = None
    v_max: float | None = None
    i_max: float | None = None
    awg_min: int | None = None  # contact range: heaviest wire (lowest AWG number) ...
    awg_max: int | None = None  # ... to lightest wire (highest AWG number)
    required: bool = False
    term: bool = False  # CAN: terminated inside the part
    r_contact: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ConnectorDef(Base):
    id: str
    match: str = ""
    part: str = ""
    pins: list[PinDef] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class LoadModel(Base):
    model: Literal["constant_power", "constant_current", "resistive"]
    p_w: float | None = None
    i_a: float | None = None
    r_ohm: float | None = None
    v_nom: float | None = None
    v_min: float = 0.0
    provenance: Provenance = "datasheet"


class SourceModel(Base):
    """Battery (v_oc, r_int), DC/DC or regulated output (v_out, i_limit, r_out)."""
    v_oc: float | None = None
    r_int: float | None = None
    v_out: float | None = None
    i_limit: float | None = None
    r_out: float | None = None
    efficiency: float | None = None
    provenance: Provenance = "datasheet"


class Coil(Base):
    a1: str  # "CONNECTOR.PIN"
    a2: str
    r: float
    v_pickup: float
    v_dropout: float = 0.0


class Contact(Base):
    """A switch contact a-b, or a relay changeover com/no/nc."""
    a: str = ""
    b: str = ""
    com: str = ""
    no: str = ""
    nc: str = ""


class Part(Base):
    """A part from the library (datasheet cards or the Parts sheet)."""
    id: str
    kind: Kind = "device"
    device: str = ""  # regex on device codes that are instances of this part
    card: str = ""
    connectors: list[ConnectorDef] = Field(default_factory=list)
    load: LoadModel | None = None
    source: SourceModel | None = None
    supply_out: SourceModel | None = None
    coil: Coil | None = None
    contacts: list[Contact] = Field(default_factory=list)
    trip_curve: list[tuple[float, float]] = Field(default_factory=list)  # (multiple of rating, seconds)
    i_interrupt: float | None = None
    r_closed: float | None = None
    controller: bool = False
    term: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)

    def pin(self, connector: str, pin: str) -> PinDef | None:
        import re
        for c in self.connectors:
            if c.id == connector or (c.match and re.search(c.match, connector)):
                for p in c.pins:
                    if p.n == pin: return p
        return None


class Component(Base):
    """An instance: a device, splice, bus, breaker, switch... Keyed by its code (first token of the device string)."""
    id: str
    raw: str
    name: str = ""
    kind: Kind = "device"
    part: str = ""
    zone: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class ConnectorHalf(Base):
    name: str
    side: Literal["near", "far"]
    guessed: bool = False


class Connector(Base):
    """A harness connector (both mated halves)."""
    id: str
    raw: str
    name: str = ""
    far_side: str = ""
    halves: list[ConnectorHalf] = Field(default_factory=list)
    pin_count: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Splice(Base):
    id: str
    raw: str
    zone: str = ""


class Bus(Base):
    id: str
    raw: str
    function_class: str = ""


class ProtectiveDevice(Base):
    id: str
    kind: Literal["breaker", "fuse"] = "breaker"
    rating_a: float | None = None
    rating_provenance: Provenance = "design"
    panel: str = ""
    loads: list[str] = Field(default_factory=list)
    trip_curve: str = ""  # part id holding the time-current curve
    i_interrupt: float | None = None
    sources: list[Source] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class Switch(Base):
    id: str
    part: str = ""
    contacts: list[Contact] = Field(default_factory=list)


class Relay(Base):
    id: str
    part: str = ""
    coil: Coil | None = None
    contacts: list[Contact] = Field(default_factory=list)


class Conductor(Base):
    """One physical conductor."""
    id: str
    label: str = ""  # printed label (resolved: row, labels.json, else id)
    name: str = ""   # resolved: row, names.py, else the function text
    from_: Terminal = Field(alias="from")
    to: Terminal
    func: str = ""
    bus: str = ""
    cls: str = ""      # explicit function class (empty: derived)
    gauge: str = ""    # as written: "22", "20 AWG", "TBD"
    colour: str = ""   # explicit colour code (empty: from the palette)
    length_m: float | None = None
    current_a: float | None = None
    status: str = ""
    subsystem: str = ""
    notes: str = ""
    zone: str = ""
    harness: str = ""
    protection: str = ""
    sources: list[Source] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    # resolved
    kind: str = ""       # function class: 14 V, 24 V, 5 V, GND, signal, CAN
    can: str = ""        # CAN_H / CAN_L
    colour_code: str = ""

    def end(self, e: int) -> Terminal:
        return self.from_ if e == 1 else self.to

    @property
    def awg(self) -> int | None:
        import re
        m = re.match(r"\s*(\d+)", self.gauge)
        return int(m.group(1)) if m else None


class Harness(Base):
    id: str
    name: str = ""
    conductors: list[str] = Field(default_factory=list)


class Zone(Base):
    id: str
    name: str = ""
    xy: tuple[float, float] | None = None


class Decision(Base):
    id: str
    date: str = ""
    text: str = ""
    by: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class OpenItem(Base):
    id: str
    text: str = ""
    status: str = "open"
    owner: str = ""
    objects: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class Issue(Base):
    """A rule finding."""
    rule: str
    severity: Severity
    message: str
    objects: list[str] = Field(default_factory=list)  # object refs: conductor:W1, component:ECU, pin:X-BH/3 ...
    fix: str = ""
    file: str = ""
    row: int | None = None
    column: str = ""


class LabelEntry(Base):
    label: str
    conductor: str = ""
    status: Literal["active", "retired"] = "active"
    reason: str = ""
    date: str = ""


class LabelLedger(Base):
    """Printed labels are never reused: retired labels stay here with a reason."""
    entries: list[LabelEntry] = Field(default_factory=list)


class Model(Base):
    """The whole project."""
    schema_version: str = SCHEMA_VERSION
    conductors: list[Conductor] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    connectors: list[Connector] = Field(default_factory=list)
    splices: list[Splice] = Field(default_factory=list)
    buses: list[Bus] = Field(default_factory=list)
    protective_devices: list[ProtectiveDevice] = Field(default_factory=list)
    switches: list[Switch] = Field(default_factory=list)
    relays: list[Relay] = Field(default_factory=list)
    parts: list[Part] = Field(default_factory=list)
    harnesses: list[Harness] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    open_items: list[OpenItem] = Field(default_factory=list)
    ledger: LabelLedger = Field(default_factory=LabelLedger)
    _by_raw: dict[str, Component] = PrivateAttr(default_factory=dict)

    def component(self, raw: str) -> Component | None:
        """Component for a device string (cached index; compare models with model_dump(), not ==)."""
        if len(self._by_raw) != len(self.components): self._by_raw = {c.raw: c for c in self.components}
        return self._by_raw.get(raw)

    def part(self, pid: str) -> Part | None:
        return next((p for p in self.parts if p.id == pid), None)


def json_schemas() -> dict[str, dict[str, Any]]:
    """JSON Schemas written to schemas/ (`schemagen schema`); a test fails when they drift from the models."""
    out = {"model.schema.json": Model.model_json_schema(by_alias=True), "part.schema.json": Part.model_json_schema(by_alias=True),
           "issue.schema.json": Issue.model_json_schema(by_alias=True)}
    for k, s in out.items(): s["$id"] = f"https://schemagen.invalid/schemas/{k}"; s["x-schema-version"] = SCHEMA_VERSION
    return out
