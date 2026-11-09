# Interface cards: switches and the battery contactor (fictional)

Every panel switch is a single-pole toggle between pin 1 and pin 2.

```yaml schemagen
device: '^SW-'
part: panel toggle switch, SPST 20 A
kind: switch
contacts:
  - {a: ".1", b: ".2"}
```

```yaml schemagen
device: '^K-BATTERY-CONTACTOR\b'
part: 14 V battery contactor, 100 A continuous
kind: relay
coil: {a1: "coil.+", a2: "coil.-", r: 48, v_pickup: 8, v_dropout: 3}
contacts:
  - {com: ".30", "no": ".87"}
```
