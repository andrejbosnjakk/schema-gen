# Kestrel E2 demonstrator (fictional)

The example project of schemagen 1.0 and the one the quickstart tour walks through. The Kestrel E2 is an invented
two-seat electric aircraft; every name, value and part here is made up.

- `wires.xlsx`: the wire list as a readable sheet (docs/readable.md), 121 wires. Written by `make_sheet.py`; edit the
  rows there and run `python examples/aircraft/make_sheet.py` (the same rows always give the same bytes).
- `schemagen.yml`: points at the sheet; the firewall connector's `motor side` is the far half; the 400 V stub is its
  own class `HV`, drawn orange. LV is never orange (14 V red, ground black, signal blue, CAN green).
- `cards/`: part data for the simulation: the three batteries and the DC-DC converter (source values), the panel
  switches and the battery contactor (contacts, coil), the avionics, motor controller and BMS (loads with `p_w` and
  `v_min`, CAN pins), and the two CAN terminations.

## What is in it

| | |
|---|---|
| sources | main battery 14 V, backup battery 14 V, DC-DC converter 400 V to 13.8 V, HV battery pack (a stub: only the converter input) |
| distribution | main bus, essential bus (avionics, fed from the main bus through the avionics master and from the backup battery), cabin bus, ground bus; 17 breakers, 1 fuse, battery contactor, 7 switches |
| harness connectors | firewall `X-FW` (cockpit side / motor side), wing root `X-WR` (cockpit side / wing side) |
| loads | EFIS, com radio, transponder, GPS; nav, strobe and landing lights; motor controller (LV control and CAN side), BMS, coolant pump; cabin light, USB charger, cabin fan |
| sensors | throttle position, motor and coolant temperature, outside air temperature |
| CAN | one bus, EFIS to motor controller and BMS through the firewall, terminated at the panel and in the motor bay |

Counts: 121 conductors, 70 components (29 devices, 17 breakers, 1 fuse, 7 switches, 1 relay, 4 buses, 8 splices,
2 harness connectors).

## The three deliberate mistakes

| # | what | where | found by |
|---|---|---|---|
| 1 | **Undersized wire.** The landing light draws 6 A on a correctly sized 10 A breaker, but the wire from the breaker to the landing light switch is 22 AWG (at most 5 A per FAA AC 43.13-1B Table 11-3). The rest of the run is 18 AWG. | `W045` "Landing light switch feed", `CB-LANDING-LT` | `check`: `gauge-protection` (error). The app overlay should call it "wire too small for its breaker". Fix: 18 AWG. |
| 2 | **Oversized breaker.** The transponder draws 1.5 A on 20 AWG, which is fine, but its breaker is 15 A: 20 AWG allows at most 7.5 A, and 15 A is ten times the load. | `W058` "Transponder supply", `CB-XPDR` | `check`: `gauge-protection` (error). The app overlay should call it "breaker oversized for its wire". Fix: a 3 A breaker. |
| 3 | **Load on an unpowered bus.** The cabin bus feeds three breakers (cabin light, USB charger, cabin fan) but nothing feeds the cabin bus: no wire from the main bus or any source. | `BB-CABIN-BUS`; `W113`, `W116`, `W119` and the loads `CABIN-LIGHT`, `USB-CHARGER`, `CABIN-FAN` | Not by `check` today (no rule looks for it). The simulation shows the cabin bus at 0 V and its three loads unpowered, but `schemagen sim` still prints `pass` (the 0.7 false pass that stream A fixes). The app overlay should flag "bus with loads and no source" (error). Fix: a feed from the main bus through a breaker. |

Everything else is clean: `schemagen check examples/aircraft` reports the two `gauge-protection` errors above and
one info, `direction-unknown` for the three antenna coax cables (an antenna and a radio have no one-way signal).
