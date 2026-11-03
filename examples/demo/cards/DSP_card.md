# Interface card: demo dashboard display (fictional)

Terminated CAN node (120 Ω inside), supplies and reads the oil temperature sensor.

```yaml schemagen
device: '^DSP$'
part: demo display
kind: device
connectors:
  - id: CAN
    match: '^CAN$'
    pins:
      - {n: H, name: CAN_H, type: can_h, term: true}
      - {n: L, name: CAN_L, type: can_l, term: true}
  - id: Sensor
    match: '^Sensor$'
    pins:
      - {n: 5V, name: SENS 5V, type: power_out, i_max: 0.1}
      - {n: AI1, name: AI1 oil temp, type: signal_in}
```
