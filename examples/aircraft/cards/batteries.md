# Interface cards: Kestrel E2 batteries (fictional)

Values are design assumptions for the example, not datasheet data.

```yaml schemagen
device: '^MAIN-BATTERY\b'
part: Kestrel 14 V LiFePO4 main battery 20 Ah
kind: battery
source: {v_oc: 13.6, r_int: 0.02, provenance: design}
connectors:
  - {id: "+", match: '^\+$', type: power_out, i_max: 100}
  - {id: "-", match: '^-$', type: ground, i_max: 100}
```

```yaml schemagen
device: '^BACKUP-BATTERY\b'
part: Kestrel 14 V LiFePO4 backup battery 5 Ah
kind: battery
source: {v_oc: 13.6, r_int: 0.06, provenance: design}
connectors:
  - {id: "+", match: '^\+$', type: power_out, i_max: 30}
  - {id: "-", match: '^-$', type: ground, i_max: 30}
```

The HV pack is a stub: only the DC-DC converter's input is wired here; the traction wiring is a separate project.

```yaml schemagen
device: '^HV-BATTERY-PACK\b'
part: Kestrel 400 V traction pack (stub)
kind: battery
source: {v_oc: 400, r_int: 0.2, provenance: design}
connectors:
  - {id: "+", match: '^\+$', type: power_out}
  - {id: "-", match: '^-$', type: ground}
```
