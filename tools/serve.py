#!/usr/bin/env python3
"""Local recording server for the Hörbuch-Werkstatt.

Usage: python3 tools/serve.py [port]   (default 8765), then open http://localhost:8765
       python3 tools/serve.py reprocess [book]   re-trim all takes from their raw recordings
Needs: ffmpeg (takes -> wav, assemble), optional edge-tts (Chinese names).

API
  GET  /api/data                                  all books (fresh parse of buecher/)
  GET  /api/takes/<book>/<chapter-n>              takes.json for a chapter
  POST /api/take/<book>/<chapter-n>/<line>        body = audio blob; saves + converts to wav.
                                                  Header X-Cuts: "1.2,4.5" splits one recording onto consecutive lines,
                                                  X-Keep: n keeps only the first n segments
  POST /api/select/<book>/<chapter-n>/<line>/<k>  select take k (-1 = none)
  DELETE /api/take/<book>/<chapter-n>/<line>/<k>  delete take k
  DELETE /api/chapter/<book>/<chapter-n>          delete all takes, raw recordings and assembled files of a chapter
  POST /api/assemble/<book>/<chapter-n>           concat selected takes -> wav + Audacity labels
  POST /api/color/<book>/<figure-file>            body = #rrggbb, writes "- Farbe:" into the Steckbrief
  GET  /api/say?t=<chinese>                       mp3 via edge-tts (cached)
  GET  /buecher/<book>/figuren/<img>              character photos
  GET  /audio/<book>/<chapter-n>/<file>           take audio
"""
import json, re, subprocess, sys, time, urllib.parse, wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

ROOT = build.ROOT
APP = ROOT / "app"
BOOKS = ROOT / "buecher"
CACHE = BOOKS / ".cache"
GAP = {"line": 0.5, "cont": 0.15, "pause": 1.5, "scene": 2.0}  # seconds of silence after each element (cont = before a "+" continuation)
TRIM_HEAD, TRIM_TAIL = 0.0, 0.0     # fixed seconds cut from each take before silence detection (0 = rely on MIN_VOICE)
HEAD = dict(db=-42, pad=0.12, min_voice=0.05)   # leading (levels after denoise: floor ~-55 dB, soft onsets ~-31 dB)
TAIL = dict(db=-45, pad=0.25, min_voice=0.05)   # trailing: keeps the decay of the last syllable
DENOISE = ROOT / "tools" / "models" / "sh.rnnn"   # RNNoise model for ffmpeg arnndn; set to None to disable
FADE = 0.03                                     # fade-out seconds against abrupt ends
VOICE = "zh-CN-XiaoxiaoNeural"
SAFE = re.compile(r"^[A-Za-z0-9_\-]+$")


def chapter_dir(book, n):
    assert SAFE.match(book) and SAFE.match(n)
    d = BOOKS / book / "audio" / f"kapitel-{int(n):02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_takes(d):
    p = d / "takes.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_takes(d, t):
    (d / "takes.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")


def wav_duration(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def ffmpeg(*args):
    return subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)


def decode(raw, tmp):
    return ffmpeg("-i", str(raw), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(tmp))


def cut(tmp, wav, start=None, end=None):
    """tmp (decoded wav) -> wav segment: keyboard click trimmed at both ends, leading/trailing silence stripped."""
    total = wav_duration(tmp)
    a = (start or 0.0) + TRIM_HEAD
    b = (end if end is not None else total) - TRIM_TAIL
    b = max(a + 0.05, min(b, total))
    sr = lambda c: f"silenceremove=start_periods=1:start_threshold={c['db']}dB:start_silence={c['pad']}:start_duration={c['min_voice']}:detection=peak"
    dn = f"arnndn=m={DENOISE}," if DENOISE and Path(DENOISE).exists() else ""
    # two passes: ffmpeg yields an empty stream when silenceremove -> areverse -> silenceremove run in one graph
    mid = wav.with_suffix(".mid.wav")
    r = ffmpeg("-i", str(tmp), "-af", f"atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,{dn}{sr(HEAD)}", "-c:a", "pcm_s24le", str(mid))
    if not r.returncode:
        r = ffmpeg("-i", str(mid), "-af", f"areverse,{sr(TAIL)},afade=t=in:d={FADE},areverse,afade=t=in:d=0.01", "-c:a", "pcm_s24le", str(wav))
    mid.unlink(missing_ok=True)
    return r


def convert(raw, wav, start=None, end=None):
    tmp = raw.with_suffix(".tmp.wav")
    r = decode(raw, tmp)
    if not r.returncode:
        r = cut(tmp, wav, start, end)
    tmp.unlink(missing_ok=True)
    return r


def line_order(chap):
    return [i for i, l in enumerate(chap["lines"]) if l["t"] == "line"]


def add_take(takes, d, chap, line, wav_name, src, rng):
    rec = takes.setdefault(str(line), {"takes": [], "selected": -1})
    wav = d / wav_name
    rec["takes"].append({"wav": wav.name, "dur": round(wav_duration(wav), 2), "at": int(time.time()), "src": src, "range": rng})
    rec["selected"] = len(rec["takes"]) - 1
    if chap and line < len(chap["lines"]):
        rec["text"] = chap["lines"][line]["text"]
    return rec


def next_take_name(d, takes, line):
    k = len(takes.get(str(line), {"takes": []})["takes"]) + 1
    while (d / f"L{line:03d}-t{k}.wav").exists():
        k += 1
    return f"L{line:03d}-t{k}.wav"


def reprocess(book=None):
    """Re-run the cut on every take from its raw recording (after changing TRIM/SILENCE settings)."""
    n = 0
    for bdir in BOOKS.iterdir():
        if book and bdir.name != book or not (bdir / "audio").is_dir():
            continue
        for cdir in (bdir / "audio").iterdir():
            if not (cdir / "takes.json").exists():
                continue
            takes = load_takes(cdir)
            for rec in takes.values():
                for t in rec["takes"]:
                    wav = cdir / t["wav"]
                    src = cdir / t["src"] if t.get("src") else next((wav.with_suffix(e) for e in (".webm", ".ogg", ".raw.wav") if wav.with_suffix(e).exists()), None)
                    rng = t.get("range") or [None, None]
                    if src and src.exists() and not convert(src, wav, *rng).returncode:
                        t["dur"] = round(wav_duration(wav), 2); n += 1
            save_takes(cdir, takes)
    return n


def find_chapter(book, n):
    for b in build.collect():
        if b["slug"] == book:
            for c in b["chapters"]:
                if c["n"] == int(n):
                    return c
    return None


def assemble(book, n):
    d = chapter_dir(book, n)
    ch = find_chapter(book, n)
    takes = load_takes(d)
    silence = {}
    for kind, sec in GAP.items():
        s = d / f".silence-{kind}.wav"
        if not s.exists():
            ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(sec), "-c:a", "pcm_s24le", str(s))
        silence[kind] = s
    parts, labels, t, missing = [], [], 0.0, []
    for i, l in enumerate(ch["lines"]):
        nxt = ch["lines"][i + 1] if i + 1 < len(ch["lines"]) else None
        kind = "cont" if (l["t"] == "line" and nxt and nxt.get("cont")) else l["t"]
        if l["t"] == "line":
            rec = takes.get(str(i))
            k = rec.get("selected", -1) if rec else -1
            if rec and 0 <= k < len(rec["takes"]):
                f = d / rec["takes"][k]["wav"]
                dur = wav_duration(f)
                parts.append(f)
                labels.append((t, t + dur, f"{i:03d} {l['who']}: {l['text'][:60]}"))
                t += dur
            else:
                missing.append(i)
                continue
        parts.append(silence[kind])
        t += GAP[kind]
    if not labels:
        return {"error": "keine ausgewählten Aufnahmen"}
    lst = d / ".concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    out = d / f"kapitel-{int(n):02d}.wav"
    r = ffmpeg("-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "pcm_s24le", str(out))
    if r.returncode:
        return {"error": r.stderr}
    lab = d / f"kapitel-{int(n):02d}.labels.txt"
    lab.write_text("".join(f"{a:.3f}\t{b:.3f}\t{name}\n" for a, b, name in labels), encoding="utf-8")
    return {"wav": str(out.relative_to(ROOT)), "labels": str(lab.relative_to(ROOT)), "duration": t, "missing": missing}


def say(text):
    CACHE.joinpath("namen").mkdir(parents=True, exist_ok=True)
    f = CACHE / "namen" / f"{text}.mp3"
    if not f.exists():
        subprocess.run(["edge-tts", "-v", VOICE, "-t", text, "--write-media", str(f)], capture_output=True)
    return f if f.exists() else None


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(APP), **kw)

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, p, ctype):
        if not p or not Path(p).exists():
            self.send_error(404); return
        data = Path(p).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        parts = u.path.strip("/").split("/")
        if u.path == "/api/data":
            return self.send_json(build.collect())
        if u.path == "/api/config":
            return self.send_json({"gap": GAP})
        if parts[:2] == ["api", "takes"] and len(parts) == 4:
            return self.send_json(load_takes(chapter_dir(parts[2], parts[3])))
        if u.path == "/api/say":
            t = urllib.parse.parse_qs(u.query).get("t", [""])[0]
            return self.send_file(say(t) if t else None, "audio/mpeg")
        if parts[0] == "buecher" and len(parts) == 4 and parts[2] == "figuren" and SAFE.match(parts[1]):
            p = BOOKS / parts[1] / "figuren" / urllib.parse.unquote(parts[3])
            ext = p.suffix.lower().lstrip(".")
            return self.send_file(p if p.suffix.lower() in build.IMG_EXT else None, f"image/{'jpeg' if ext=='jpg' else ext}")
        if parts[0] == "audio" and len(parts) == 4:
            p = chapter_dir(parts[1], parts[2]) / urllib.parse.unquote(parts[3])
            return self.send_file(p if p.suffix in (".wav", ".webm", ".ogg") else None, "audio/wav" if p.suffix == ".wav" else "audio/webm")
        return super().do_GET()

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if parts[:2] == ["api", "take"] and len(parts) == 5:
            # single take, or a continuous recording with cut points (X-Cuts: "1.23,4.56") mapped onto consecutive lines
            book, ch, line = parts[2], parts[3], int(parts[4])
            d = chapter_dir(book, ch)
            takes = load_takes(d)
            chap = find_chapter(book, ch)
            cuts = [float(x) for x in self.headers.get("X-Cuts", "").split(",") if x.strip()]
            ext = "wav" if body[:4] == b"RIFF" else "ogg" if body[:4] == b"OggS" else "webm"
            if not cuts:
                name = next_take_name(d, takes, line)
                raw = d / name.replace(".wav", f".raw.{ext}")
                raw.write_bytes(body)
                r = convert(raw, d / name)
                if r.returncode:
                    return self.send_json({"error": r.stderr}, 500)
                rec = add_take(takes, d, chap, line, name, raw.name, None)
                save_takes(d, takes)
                return self.send_json({"lines": {str(line): rec}})
            raw = d / f"S{line:03d}-{int(time.time())}.{ext}"
            raw.write_bytes(body)
            tmp = raw.with_suffix(".tmp.wav")
            if decode(raw, tmp).returncode:
                return self.send_json({"error": "decode failed"}, 500)
            order = line_order(chap)
            pos = order.index(line) if line in order else 0
            bounds = [0.0] + cuts + [wav_duration(tmp)]
            keep = int(self.headers.get("X-Keep") or len(bounds) - 1)  # segments to keep (cancel drops the last one)
            out = {}
            for k in range(min(keep, len(bounds) - 1)):
                if pos + k >= len(order):
                    break
                ln = order[pos + k]
                name = next_take_name(d, takes, ln)
                if cut(tmp, d / name, bounds[k], bounds[k + 1]).returncode:
                    continue
                out[str(ln)] = add_take(takes, d, chap, ln, name, raw.name, [bounds[k], bounds[k + 1]])
            tmp.unlink(missing_ok=True)
            save_takes(d, takes)
            return self.send_json({"lines": out})
        if parts[:2] == ["api", "select"] and len(parts) == 6:
            d = chapter_dir(parts[2], parts[3])
            takes = load_takes(d)
            rec = takes.get(parts[4])
            if rec:
                rec["selected"] = int(parts[5]); save_takes(d, takes)
            return self.send_json(rec or {})
        if parts[:2] == ["api", "assemble"] and len(parts) == 4:
            return self.send_json(assemble(parts[2], parts[3]))
        if parts[:2] == ["api", "color"] and len(parts) == 5 and SAFE.match(parts[2]):
            p = BOOKS / parts[2] / "figuren" / urllib.parse.unquote(parts[4])
            hexcol = body.decode().strip()
            if p.exists() and re.match(r"^#[0-9a-fA-F]{6}$", hexcol):
                txt = p.read_text(encoding="utf-8")
                if re.search(r"^- Farbe:.*$", txt, re.M):
                    txt = re.sub(r"^- Farbe:.*$", f"- Farbe: {hexcol}", txt, count=1, flags=re.M)
                else:
                    txt = re.sub(r"^(# .*\n)", rf"\1- Farbe: {hexcol}\n", txt, count=1, flags=re.M)
                p.write_text(txt, encoding="utf-8")
                return self.send_json({"ok": True})
            return self.send_json({"error": "bad request"}, 400)
        self.send_error(404)

    def do_DELETE(self):
        parts = self.path.strip("/").split("/")
        if parts[:2] == ["api", "chapter"] and len(parts) == 4:
            d = chapter_dir(parts[2], parts[3])
            n = 0
            for f in d.iterdir():
                if f.suffix in (".wav", ".webm", ".ogg", ".txt", ".json"):
                    f.unlink(); n += 1
            return self.send_json({"deleted": n})
        if parts[:2] == ["api", "take"] and len(parts) == 6:
            d = chapter_dir(parts[2], parts[3])
            takes = load_takes(d)
            rec = takes.get(parts[4])
            k = int(parts[5])
            if rec and 0 <= k < len(rec["takes"]):
                t = rec["takes"].pop(k)
                (d / t["wav"]).unlink(missing_ok=True)
                src = t.get("src") or Path(t["wav"]).with_suffix(".webm").name
                still_used = any(x.get("src") == src for r in takes.values() for x in r["takes"])
                if not still_used:
                    (d / src).unlink(missing_ok=True)
                if not rec["takes"]:
                    del takes[parts[4]]
                elif rec["selected"] >= len(rec["takes"]):
                    rec["selected"] = len(rec["takes"]) - 1
                save_takes(d, takes)
            return self.send_json(takes.get(parts[4], {}))
        self.send_error(404)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reprocess":
        print(f"{reprocess(sys.argv[2] if len(sys.argv) > 2 else None)} Takes neu verarbeitet"); sys.exit()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Hörbuch-Werkstatt: http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
