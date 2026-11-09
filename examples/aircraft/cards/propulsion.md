# Interface cards: motor controller, BMS and CAN terminations (fictional)

Only the low-voltage control side of the motor controller is in this project.

```yaml schemagen
device: '^MOTOR-CONTROLLER\b'
part: Kestrel 80 kW motor controller (LV side)
kind: controller
load: {model: constant_power, p_w: 15, v_min: 9, provenance: design}
connectors:
  - id: J1
    match: '^J1$'
    pins:
      - {n: "1", name: 14V IN, type: power_in, i_max: 5}
      - {n: "2", name: GND, type: ground}
      - {n: "3", name: ENABLE, type: signal_in}
      - {n: "7", name: CAN_H, type: can_h}
      - {n: "8", name: CAN_L, type: can_l}
```

```yaml schemagen
device: '^BATTERY-MANAGEMENT-SYSTEM\b'
part: Kestrel BMS master
kind: controller
load: {model: constant_power, p_w: 5, v_min: 9, provenance: design}
connectors:
  - id: J1
    match: '^J1$'
    pins:
      - {n: "1", name: 14V IN, type: power_in, i_max: 3}
      - {n: "2", name: GND, type: ground}
      - {n: "3", name: CAN_H, type: can_h}
      - {n: "4", name: CAN_L, type: can_l}
```

```yaml schemagen
device: '^CAN-TERMINATOR-'
part: 120 ohm CAN termination plug
kind: terminator
connectors:
  - id: ""
    match: '^$'
    pins:
      - {n: "1", name: CAN_H, type: can_h, term: true}
      - {n: "2", name: CAN_L, type: can_l, term: true}
```
