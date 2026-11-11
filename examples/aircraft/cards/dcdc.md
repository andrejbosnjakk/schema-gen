# Interface card: Kestrel E2 DC-DC converter, 400 V to 14 V (fictional)

```yaml schemagen
device: '^DC-DC-CONVERTER\b'
part: Kestrel 600 W isolated DC-DC
kind: dcdc
source: {v_out: 13.8, i_limit: 40, r_out: 0.01, efficiency: 0.93, provenance: design}
connectors:
  - id: HV
    match: '^HV$'
    pins:
      - {n: "1", name: HV+, type: power_in, v_max: 450}
      - {n: "2", name: HV-, type: ground}
  - id: LV
    match: '^LV$'
    pins:
      - {n: "1", name: 14V OUT, type: power_out, i_max: 45}
      - {n: "2", name: 14V RTN, type: ground, i_max: 45}
```
