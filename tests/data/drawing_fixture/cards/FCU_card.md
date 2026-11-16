# Interface card: fictional 40-pin controller

```yaml schemagen
device: '^FCU$'
kind: controller
load: {model: constant_power, p_w: 20, v_min: 9}
connectors:
  - id: J1
    match: '^J1$'
    part: fictional 40-pin plug
    pins:
      - {n: 1, name: VBAT, type: power_in}
      - {n: 2, name: GND, type: ground}
      - {n: 3, name: CAN_H, type: can_h}
      - {n: 4, name: CAN_L, type: can_l}
      - {n: 5, name: IO1, type: signal}
      - {n: 6, name: IO2, type: signal}
      - {n: 7, name: IO3, type: signal}
      - {n: 8, name: IO4, type: signal}
      - {n: 9, name: IO5, type: signal}
      - {n: 10, name: IO6, type: signal}
      - {n: 11, name: IO7, type: signal}
      - {n: 12, name: IO8, type: signal}
      - {n: 13, name: IO9, type: signal}
      - {n: 14, name: IO10, type: signal}
      - {n: 15, name: IO11, type: signal}
      - {n: 16, name: IO12, type: signal}
      - {n: 17, name: IO13, type: signal}
      - {n: 18, name: IO14, type: signal}
      - {n: 19, name: IO15, type: signal}
      - {n: 20, name: IO16, type: signal}
      - {n: 21, name: IO17, type: signal}
      - {n: 22, name: IO18, type: signal}
      - {n: 23, name: IO19, type: signal}
      - {n: 24, name: IO20, type: signal}
      - {n: 25, name: IO21, type: signal}
      - {n: 26, name: IO22, type: signal}
      - {n: 27, name: IO23, type: signal}
      - {n: 28, name: IO24, type: signal}
      - {n: 29, name: IO25, type: signal}
      - {n: 30, name: IO26, type: signal}
      - {n: 31, name: IO27, type: signal}
      - {n: 32, name: IO28, type: signal}
      - {n: 33, name: IO29, type: signal}
      - {n: 34, name: IO30, type: signal}
      - {n: 35, name: IO31, type: signal}
      - {n: 36, name: IO32, type: signal}
      - {n: 37, name: IO33, type: signal}
      - {n: 38, name: IO34, type: signal}
      - {n: 39, name: IO35, type: signal}
      - {n: 40, name: IO36, type: signal}
```
