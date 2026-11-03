# Interface card: demo 14 V battery (fictional)

```yaml schemagen
device: '^BAT$'
part: demo battery 12 Ah
kind: battery
source: {v_oc: 13.2, r_int: 0.02}
connectors:
  - {id: "+", match: '^\+$', type: power_out, i_max: 200}
  - {id: "−", match: '^−$', type: ground, i_max: 200}
```
