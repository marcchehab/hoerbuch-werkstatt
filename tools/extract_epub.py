#!/usr/bin/env python3
"""Extract an EPUB into plain-text chapters.

Usage: python3 tools/extract_epub.py buecher/<slug>/original/<book>.epub
Writes buecher/<slug>/original/text/NNN-<title>.md, one per spine item.
No dependencies.
"""
import html, re, sys, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

def strip(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", "", h)
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"(?i)</(p|div|h[1-6]|li|blockquote|tr)>", "\n\n", h)
    h = re.sub(r"(?s)<[^>]+>", "", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t ]+", " ", h)
    h = re.sub(r"\n{3,}", "\n\n", h)
    return "\n".join(l.strip() for l in h.split("\n")).strip()

def main(path):
    epub = Path(path)
    out = epub.parent / "text"
    out.mkdir(exist_ok=True)
    z = zipfile.ZipFile(epub)
    cont = ET.fromstring(z.read("META-INF/container.xml"))
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    opf_path = cont.find(".//c:rootfile", ns).attrib["full-path"]
    base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
    opf = ET.fromstring(z.read(opf_path))
    ons = {"o": "http://www.idpf.org/2007/opf"}
    items = {i.attrib["id"]: i.attrib["href"] for i in opf.find("o:manifest", ons)}
    n = 0
    for ref in opf.find("o:spine", ons):
        href = items.get(ref.attrib["idref"])
        if not href or not href.endswith(("html", "xhtml")):
            continue
        raw = z.read(base + href).decode("utf-8", "replace")
        m = re.search(r"(?is)<h[1-6][^>]*>(.*?)</h[1-6]>", raw)
        title = strip(m.group(1)).replace("\n", " ") if m else ""
        text = strip(raw)
        if len(text) < 200:
            continue
        n += 1
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "abschnitt"
        (out / f"{n:03d}-{slug}.md").write_text(text, encoding="utf-8")
        print(f"{n:03d} {len(text):6d}  {title[:60]}")

if __name__ == "__main__":
    main(sys.argv[1])
