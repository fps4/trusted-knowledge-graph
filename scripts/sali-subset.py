#!/usr/bin/env python3
"""Import the SALI LMSS concepts the firm maps to — and only those.

Run by hand, with network, when the mapping changes:

    python3 scripts/sali-subset.py            # fetches the pinned release
    python3 scripts/sali-subset.py LMSS.owl   # or reads a local copy

Reads config/sali-mapping.yaml, fetches LMSS.owl at the pinned commit, checks
that every mapped IRI exists in it, and writes vocab/sali-lmss-subset.ttl: each
mapped concept with its label, definition and parent, and the file's provenance.
Standard library only, so it runs on any host with python3. LMSS is MIT-licensed;
see docs/sources.md.
"""

import hashlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}
R = "{%s}" % NS["rdf"]


def mapping() -> tuple[dict, set[str]]:
    text = (ROOT / "config" / "sali-mapping.yaml").read_text()
    source = dict(re.findall(r"^  (url|commit|committed|licence|namespace): (\S+)", text, re.M))
    ids = set(re.findall(r"sali: (\w+)", text))
    return source, ids


def esc(s: str) -> str:
    return " ".join(s.split()).replace("\\", "\\\\").replace('"', '\\"')


def main() -> None:
    source, ids = mapping()
    if len(sys.argv) > 1:
        raw = Path(sys.argv[1]).read_bytes()
    else:
        with urllib.request.urlopen(source["url"], timeout=120) as response:
            raw = response.read()
    digest = hashlib.sha256(raw).hexdigest()
    root = ET.fromstring(raw)
    base = source["namespace"]
    classes = {}
    for c in root.findall("owl:Class", NS):
        label = c.find("rdfs:label", NS)
        definition = c.find("skos:definition", NS)
        classes[c.get(R + "about")] = {
            "label": label.text if label is not None else None,
            "definition": definition.text if definition is not None else None,
            "parents": [
                s.get(R + "resource") for s in c.findall("rdfs:subClassOf", NS)
                if s.get(R + "resource")
            ],
        }
    missing = sorted(i for i in ids if base + i not in classes)
    if missing:
        sys.exit(f"not in this LMSS release: {', '.join(missing)}")

    lines = [
        "# SALI LMSS — the subset this firm maps to. Generated; do not edit.",
        f"# source   {source['url']}",
        f"# commit   {source['commit']} ({source['committed']})",
        f"# sha256   {digest}",
        f"# licence  {source['licence']} — see docs/sources.md",
        "# regenerate with: python3 scripts/sali-subset.py",
        "",
        "@prefix lmss: <http://lmss.sali.org/> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "@prefix owl:  <http://www.w3.org/2002/07/owl#> .",
        "",
    ]
    parents = set()
    for i in sorted(ids):
        c = classes[base + i]
        lines.append(f"<{base}{i}> a owl:Class, skos:Concept ;")
        lines.append(f'    rdfs:label "{esc(c["label"])}" ; skos:prefLabel "{esc(c["label"])}" ;')
        if c["definition"]:
            lines.append(f'    skos:definition "{esc(c["definition"])[:480]}" ;')
        for p in c["parents"]:
            parents.add(p)
        subclass = " , ".join(f"<{p}>" for p in c["parents"])
        lines.append(f"    rdfs:subClassOf {subclass} .")
        lines.append("")
    for p in sorted(parents - {base + i for i in ids}):
        label = classes.get(p, {}).get("label") or p
        lines.append(f'<{p}> a owl:Class ; rdfs:label "{esc(label)}" .')
    out = ROOT / "vocab" / "sali-lmss-subset.ttl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(ids)} concepts, {len(parents)} parents → {out.relative_to(ROOT)} (sha256 {digest[:12]}…)")


if __name__ == "__main__":
    main()
