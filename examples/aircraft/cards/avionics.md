# Interface cards: Kestrel E2 avionics (fictional)

Loads are constant power with the lowest supply voltage at which each unit keeps working.

```yaml schemagen
device: '^EFIS\b'
part: Kestrel EFIS 10 inch
kind: device
load: {model: constant_power, p_w: 30, v_min: 9, provenance: design}
connectors:
  - id: J1
    match: '^J1$'
    pins:
      - {n: "1", name: POWER, type: power_in, i_max: 5}
      - {n: "2", name: GND, type: ground}
      - {n: "7", name: CAN_H, type: can_h}
      - {n: "8", name: CAN_L, type: can_l}
  - id: J2
    match: '^J2$'
    pins:
      - {n: "3", name: ALT OUT, type: signal_out}
      - {n: "4", name: GPS IN, type: signal_in}
      - {n: "7", name: OAT, type: signal_in}
      - {n: "8", name: OAT REF, type: signal_in}
```

```yaml schemagen
device: '^COM-RADIO\b'
part: Kestrel VHF com radio
kind: device
load: {model: constant_power, p_w: 40, v_min: 10, provenance: design}
connectors:
  - id: J1
    match: '^J1$'
    pins:
      - {n: "1", name: POWER, type: power_in, i_max: 7.5}
      - {n: "2", name: GND, type: ground}
```

```yaml schemagen
device: '^TRANSPONDER\s'
part: Kestrel mode S transponder
kind: device
load: {model: constant_power, p_w: 20, v_min: 10, provenance: design}
connectors:
  - id: J1
    match: '^J1$'
    pins:
      - {n: "1", name: POWER, type: power_in, i_max: 5}
      - {n: "2", name: GND, type: ground}
      - {n: "5", name: ALT IN, type: signal_in}
```

```yaml schemagen
device: '^GPS-RECEIVER\b'
part: Kestrel GPS receiver
kind: device
load: {model: constant_power, p_w: 8, v_min: 9, provenance: design}
connectors:
  - id: J1
    match: '^J1$'
    pins:
      - {n: "1", name: POWER, type: power_in, i_max: 3}
      - {n: "2", name: GND, type: ground}
      - {n: "4", name: DATA OUT, type: signal_out}
```
