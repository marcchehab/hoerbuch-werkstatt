#!/usr/bin/env python3
"""Measure levels of the newest takes: raw noise floor, denoised floor, speech peak, and how much
quiet the cut leaves at the start/end. Usage: python3 tools/levels.py buecher/<book>/audio/kapitel-NN [n]"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import serve

def peaks(src, st=0, dur=None, ms=10, extra=""):
    args = ["ffmpeg", "-loglevel", "error", "-ss", str(st)] + (["-t", str(dur)] if dur else []) + ["-i", str(src), "-af",
            f"{extra}asetnsamples={48*ms},astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level:file=-", "-f", "null", "-"]
    out = subprocess.run(args, capture_output=True, text=True).stdout
    return [float(l.split("=")[1]) for l in out.splitlines() if "Peak_level=" in l and "-inf" not in l]

def pct(v, p):
    v = sorted(v); return v[min(len(v)-1, int(len(v)*p))] if v else float("nan")

d = Path(sys.argv[1]); n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
takes = json.load(open(d / "takes.json"))
allt = sorted(((x, k) for k, v in takes.items() for x in v["takes"]), key=lambda t: t[0]["at"])[-n:]
dn = f"arnndn=m={serve.DENOISE}," if serve.DENOISE else ""
for x, k in allt:
    src = d / x["src"]; a, b = (x.get("range") or [0, None])
    raw = peaks(src, a, (b - a) if b else None); den = peaks(src, a, (b - a) if b else None, extra=dn)
    cut = peaks(d / x["wav"]); speech = pct(cut, 0.95)
    lead = next((i for i, v in enumerate(cut) if v > speech - 25), 0) * 10
    tail = next((i for i, v in enumerate(reversed(cut)) if v > speech - 25), 0) * 10
    print(f"Zeile {k:>3} {x['wav']:<14} roh: Boden {pct(raw,0.2):5.0f} dB · entrauscht: Boden {pct(den,0.2):5.0f} dB · Sprache {speech:4.0f} dB · Ruhe vorne {lead:4d} ms, hinten {tail:4d} ms · {x['dur']}s")
