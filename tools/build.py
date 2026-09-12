#!/usr/bin/env python3
"""Bundle buecher/*/ into app/data.js (static mode) or return it as Python (used by serve.py).

Usage: python3 tools/build.py
No dependencies. Skips buecher/_vorlage and anything without skript/*.md.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "buecher"
OUT = ROOT / "app" / "data.js"

HEAD_RE = re.compile(r"^##\s*(?:Kapitel\s*)?(\d+)\s*[–\-:]?\s*(.*)$")
LINE_RE = re.compile(r"^([A-ZÄÖÜ][A-ZÄÖÜ0-9 .\-']*?)\s*(?:\(([^)]*)\))?\s*:\s*(.+)$")
META_RE = re.compile(r"^-\s*([^:]+):\s*(.*)$")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


def parse_meta(path):
    meta = {}
    if not path.exists():
        return meta
    for ln in path.read_text(encoding="utf-8").splitlines():
        m = META_RE.match(ln.strip())
        if m:
            meta[m.group(1).strip().lower()] = m.group(2).strip()
    return meta


def parse_script(path):
    number, title, lines = None, "", []
    for raw in path.read_text(encoding="utf-8").splitlines():
        ln = raw.strip()
        if not ln:
            continue
        m = HEAD_RE.match(ln)
        if m and number is None:
            number, title = int(m.group(1)), m.group(2).strip()
            continue
        if ln.startswith("[") and ln.endswith("]"):
            body = ln[1:-1]
            if body.upper().startswith("SZENE"):
                lines.append({"t": "scene", "text": body.split(":", 1)[1].strip() if ":" in body else ""})
            else:
                lines.append({"t": "pause"})
            continue
        if ln.startswith("+ ") or ln.startswith("+\t"):
            prev = next((l for l in reversed(lines) if l["t"] == "line"), None)
            lines.append({"t": "line", "who": prev["who"] if prev else "ERZÄHLER", "note": "", "unsure": False, "cont": True, "text": ln[1:].strip()})
            continue
        m = LINE_RE.match(ln)
        if m:
            name, note, text = m.group(1).strip(), (m.group(2) or "").strip(), m.group(3).strip()
            unsure = False
            parts = [p.strip() for p in note.split(",")] if note else []
            if "?" in parts:
                parts.remove("?"); unsure = True
            lines.append({"t": "line", "who": name, "note": ", ".join(parts), "unsure": unsure, "cont": False, "text": text})
        else:
            lines.append({"t": "line", "who": "ERZÄHLER", "note": "", "unsure": False, "cont": False, "text": ln})
    if number is None:
        m = re.search(r"(\d+)", path.stem)
        number = int(m.group(1)) if m else 0
    return {"n": number, "file": path.name, "title": title, "lines": lines}


def parse_figure(path, slug):
    text = path.read_text(encoding="utf-8")
    name = path.stem.upper()
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        name = m.group(1).strip()
    sections, cur = {"": []}, ""
    for ln in text.splitlines():
        if ln.startswith("## "):
            cur = ln[3:].strip(); sections[cur] = []
        elif ln.startswith("# "):
            continue
        else:
            sections[cur].append(ln)
    def fields(block):
        out = []
        for ln in block:
            m = META_RE.match(ln.strip())
            if m and m.group(2).strip():
                out.append([m.group(1).strip(), m.group(2).strip()])
        return out
    info = fields(sections.get("", []))
    special = {k.lower(): v for k, v in info}
    info = [f for f in info if f[0].lower() not in ("farbe", "zeichen", "foto")]
    foto = special.get("foto")
    if not foto:
        for ext in IMG_EXT:
            if (path.with_suffix(ext)).exists():
                foto = path.with_suffix(ext).name
                break
    return {
        "name": name,
        "file": path.name,
        "color": special.get("farbe", ""),
        "zeichen": special.get("zeichen", ""),
        "foto": f"/buecher/{slug}/figuren/{foto}" if foto else "",
        "info": info,
        "voice": fields(sections.get("Stimme", [])),
        "chris": "\n".join(sections.get("Chris", [])).strip(),
    }


def collect():
    books = []
    for bdir in sorted(BOOKS.iterdir()):
        if not bdir.is_dir() or bdir.name == "_vorlage" or bdir.name.startswith("."):
            continue
        scripts = sorted((bdir / "skript").glob("*.md"))
        if not scripts:
            continue
        meta = parse_meta(bdir / "buch.md")
        chapters = sorted((parse_script(p) for p in scripts), key=lambda c: c["n"])
        figures = [parse_figure(p, bdir.name) for p in sorted((bdir / "figuren").glob("*.md")) if not p.name.startswith("_")]
        books.append({
            "slug": bdir.name,
            "title": meta.get("titel", bdir.name),
            "author": meta.get("autor", ""),
            "dialect": meta.get("dialekt", ""),
            "demo": bdir.name.startswith("_"),
            "chapters": chapters,
            "figures": figures,
        })
    return books


def build():
    books = collect()
    OUT.write_text("window.HOERBUCH_DATA = " + json.dumps(books, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    n = sum(len(b["chapters"]) for b in books)
    print(f"{len(books)} Bücher, {n} Kapitel → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
