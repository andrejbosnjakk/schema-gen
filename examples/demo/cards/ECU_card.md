# Interface card: demo engine control unit (fictional)

## J1 connector, 4-pin

Structured block read by schemagen (the table below is for people):

```yaml schemagen
device: '^ECU$'
connectors:
  - id: J1
    match: '^J1$'
    part: demo 4-pin sealed plug
    pins:
      - {n: 1, name: VBAT, type: power_in, v_max: 16, i_max: 5}
      - {n: 2, name: GND, type: ground}
      - {n: 3, name: CAN_H, type: can}
      - {n: 4, name: CAN_L, type: can}
```

| Pin | Signal | Dir | Type | Rule |
|---|---|---|---|---|
| 1 | VBAT | in | power | 9–16 V, fused 5 A |
| 2 | GND | — | ground | to ground bus |
| 3 | CAN_H | bi | bus | 120 Ω terminated inside the ECU |
| 4 | CAN_L | bi | bus | as pin 3 |
