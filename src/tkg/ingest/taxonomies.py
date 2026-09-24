"""The concept schemes, generated from config/estate.yaml.

M0 keeps these bare: a prefLabel and a scheme. M2 replaces this generator with an
authored SKOS file carrying owners, alternative labels, the multi-reading entries
and the mapping onto SALI LMSS. Generating them now means the estate config stays
the single source of the vocabulary until there is a reason for it not to be.
"""

from __future__ import annotations

from .. import iri

HEADER = """@prefix ssf:  <https://lab.fps4.dev/firm/> .
@prefix gl:   <https://lab.fps4.dev/glossary/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""

SCHEMES = {
    "practice-area": ("practice_areas", "Practice areas"),
    "matter-type": ("matter_types", "Matter types"),
    "client-type": ("client_types", "Client types"),
    "outcome": ("outcomes", "Matter outcomes"),
    "expertise": ("expertise", "Areas of expertise"),
}


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_turtle(cfg: dict) -> str:
    lines = [HEADER]
    for scheme, (cfg_key, label) in SCHEMES.items():
        scheme_iri = f"<{iri.GLOSSARY}{scheme}>"
        lines.append(f'{scheme_iri} a skos:ConceptScheme ; skos:prefLabel "{_esc(label)}" .')
        for item in cfg[cfg_key]:
            concept = f"<{iri.concept(scheme, item['id'])}>"
            lines.append(
                f'{concept} a skos:Concept ; skos:inScheme {scheme_iri} ;\n'
                f'    skos:prefLabel "{_esc(item["label"])}" ;\n'
                f'    rdfs:label "{_esc(item["label"])}" .'
            )
    for office in cfg["offices"]:
        lines.append(
            f'<{iri.office(office)}> a ssf:Office ; rdfs:label "{_esc(office)}" .'
        )
    for j in cfg["jurisdictions"]:
        lines.append(
            f'<{iri.jurisdiction(j["id"])}> a ssf:Jurisdiction ;'
            f' rdfs:label "{_esc(j["label"])}" ; skos:notation "{_esc(j["id"])}" .'
        )
    return "\n".join(lines) + "\n"
