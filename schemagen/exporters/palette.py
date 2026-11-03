"""One wire palette for every output. Other tools (spreadsheets, schematic editors) read it with `schemagen palette`."""
import csv, json, sys

# WireViz / IEC 60757 colour codes used by schemagen, with the hex value WireViz draws.
HEX = {"BK": "#000000", "WH": "#ffffff", "GY": "#999999", "PK": "#ff66cc", "RD": "#ff0000", "OG": "#ff8000",
       "YE": "#ffff00", "OL": "#708000", "GN": "#00ff00", "TQ": "#00ffff", "LB": "#a0dfff", "BU": "#0066ff",
       "VT": "#8000ff", "BN": "#895956", "BG": "#ceb673", "IV": "#f5f0d0", "SL": "#708090", "CU": "#d6775e",
       "SN": "#aaaaaa", "SR": "#84878c", "GD": "#ffcf80"}


def entries(cfg):
    """[(function class, colour code, base hex, stripe hex or '')] for the project palette."""
    out = []
    for k, code in cfg.colours.items():
        base, stripe = code[:2], code[2:4]
        out.append((k, code, HEX.get(base, ""), HEX.get(stripe, "") if stripe else ""))
    return out


def write(cfg, fmt="csv", fh=sys.stdout):
    rows = entries(cfg)
    if fmt == "json":
        json.dump({k: {"code": c, "hex": h, "stripe_hex": s} for k, c, h, s in rows}, fh, indent=1); fh.write("\n")
    else:
        cw = csv.writer(fh); cw.writerow(["function class", "code", "hex", "stripe hex"]); cw.writerows(rows)
