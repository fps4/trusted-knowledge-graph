"""The business glossary: compiled to SKOS, resolved over SPARQL.

A term has an owner who is not an engineer. A term that means different things to
different owners has readings, one per owner, each served by its own template,
and says what a question that does not choose a reading gets. Resolution happens
at step 2, against g:glossary in the store — the same store, the same query path,
as everything else. See docs/decisions/0015.

The glossary also carries the mapping from the firm's own vocabularies to SALI
LMSS, whose imported subset lives in g:vocab/sali. docs/decisions/0016.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from .. import iri

HEADER = """@prefix ssf:  <https://lab.fps4.dev/firm/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""

SAFE_TEXT = re.compile(r"^[\w\s\-'’.,&()/]{1,80}$")
SALI = "http://lmss.sali.org/"
MATCHES = {"exactMatch", "closeMatch", "broadMatch", "narrowMatch"}
SCHEMES = {"practice-area", "matter-type"}


class TermError(ValueError):
    pass


def _esc(text: str) -> str:
    return " ".join(str(text).split()).replace("\\", "\\\\").replace('"', '\\"')


def _expand(curie: str) -> str:
    from .templates import expand

    return expand(curie)


def term_iri(term_id: str) -> str:
    return f"{iri.GLOSSARY}term/{term_id}"


def build_turtle(glossary: dict, mapping: dict) -> str:
    lines = [HEADER]
    scheme = f"<{iri.GLOSSARY}terms>"
    lines.append(f'{scheme} a skos:ConceptScheme ; skos:prefLabel "Business glossary" .')
    for t in glossary["terms"]:
        node = f"<{term_iri(t['id'])}>"
        body = [
            f"{node} a skos:Concept, ssf:BusinessTerm ; skos:inScheme {scheme}",
            f'skos:prefLabel "{_esc(t["label"])}"',
            f'skos:definition "{_esc(t["definition"])}"',
            f'ssf:owner "{_esc(t["owner"])}"',
        ]
        body += [f'skos:altLabel "{_esc(a)}"' for a in t.get("alt", [])]
        if t.get("on_ambiguous"):
            body.append(f'ssf:onAmbiguous "{_esc(t["on_ambiguous"])}"')
        if t.get("question"):
            body.append(f'ssf:servedBy "{_esc(t["question"])}"')
        for slot, value in (t.get("means") or {}).items():
            body.append(
                f'ssf:means [ ssf:meansSlot "{_esc(slot)}" ; ssf:meansValue <{_expand(value)}> ]'
            )
        for r in t.get("readings", []):
            body.append(f"ssf:hasReading <{term_iri(t['id'])}/{r['id']}>")
        lines.append(" ;\n    ".join(body) + " .")
        for r in t.get("readings", []):
            lines.append(
                f"<{term_iri(t['id'])}/{r['id']}> a skos:Concept, ssf:Reading ;\n"
                f"    skos:broader {node} ;\n"
                f'    ssf:readingKey "{_esc(r["id"])}" ;\n'
                f'    skos:prefLabel "{_esc(r["label"])}" ;\n'
                f'    skos:definition "{_esc(r["definition"])}" ;\n'
                f'    ssf:owner "{_esc(r["owner"])}" ;\n'
                f'    ssf:servedBy "{_esc(r["template"])}" .'
            )
    for scheme_name in SCHEMES:
        for concept, links in (mapping.get(scheme_name) or {}).items():
            for link in links:
                if link["match"] not in MATCHES:
                    raise TermError(f"{concept}: {link['match']} is not a SKOS mapping relation")
                lines.append(
                    f"<{iri.concept(scheme_name, concept)}> skos:{link['match']} "
                    f"<{SALI}{link['sali']}> ."
                )
    return "\n".join(lines) + "\n"


def load_config(config_dir) -> tuple[dict, dict]:
    glossary = yaml.safe_load((config_dir / "glossary.yaml").read_text())
    mapping = yaml.safe_load((config_dir / "sali-mapping.yaml").read_text())
    return glossary, mapping


# ── resolution ───────────────────────────────────────────────────────────────
@dataclass
class Reading:
    key: str
    label: str
    definition: str
    owner: str
    template: str


@dataclass
class Term:
    id: str
    label: str
    definition: str
    owner: str
    on_ambiguous: str | None = None
    question: str | None = None
    readings: list[Reading] = field(default_factory=list)
    means: dict[str, str] = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "term": self.id,
            "label": self.label,
            "definition": self.definition,
            "owner": self.owner,
            "on_ambiguous": self.on_ambiguous,
            "question": self.question,
            "readings": [r.__dict__ for r in self.readings],
            "means": {k: iri.shorten(v) for k, v in self.means.items()},
        }


TERMS = """
SELECT ?term ?label ?def ?owner ?amb ?question ?rkey ?rlabel ?rdef ?rowner ?rtemplate ?slot ?value
WHERE {
  GRAPH <%(glossary)s> {
    ?term a ssf:BusinessTerm ; skos:prefLabel ?label ; skos:definition ?def ; ssf:owner ?owner .
    %(match)s
    OPTIONAL { ?term ssf:onAmbiguous ?amb }
    OPTIONAL { ?term ssf:servedBy ?question }
    OPTIONAL {
      ?term ssf:hasReading ?reading .
      ?reading ssf:readingKey ?rkey ; skos:prefLabel ?rlabel ; skos:definition ?rdef ;
               ssf:owner ?rowner ; ssf:servedBy ?rtemplate .
    }
    OPTIONAL { ?term ssf:means [ ssf:meansSlot ?slot ; ssf:meansValue ?value ] }
  }
}
ORDER BY ?term ?rkey
"""

CONCEPTS = """
SELECT ?concept ?label ?scheme ?match ?other ?otherLabel WHERE {
  GRAPH ?vg {
    ?concept skos:prefLabel ?label .
    FILTER (LCASE(STR(?label)) = LCASE("%(text)s"))
    OPTIONAL { ?concept skos:inScheme ?scheme }
  }
  FILTER (?vg IN (<%(ontology)s>, <%(sali)s>))
  OPTIONAL {
    GRAPH <%(glossary)s> {
      { ?concept ?match ?other } UNION { ?other ?match ?concept }
      FILTER (?match IN (skos:exactMatch, skos:closeMatch, skos:broadMatch, skos:narrowMatch))
    }
    GRAPH ?og { ?other skos:prefLabel ?otherLabel }
    FILTER (?og IN (<%(ontology)s>, <%(sali)s>))
  }
}
"""


def _terms(rows: list[dict]) -> list[Term]:
    out: dict[str, Term] = {}
    for row in rows:
        v = {k: c["value"] for k, c in row.items()}
        tid = v["term"].rsplit("/", 1)[-1]
        term = out.setdefault(
            tid,
            Term(tid, v["label"], v["def"], v["owner"], v.get("amb"), v.get("question")),
        )
        if "rkey" in v and all(r.key != v["rkey"] for r in term.readings):
            term.readings.append(
                Reading(v["rkey"], v["rlabel"], v["rdef"], v["rowner"], v["rtemplate"])
            )
        if "slot" in v:
            term.means[v["slot"]] = v["value"]
    return list(out.values())


def safe(text: str) -> str:
    text = " ".join(text.split())
    if not SAFE_TEXT.match(text):
        raise TermError("a term is a few words — letters, digits, spaces and simple punctuation")
    return text.replace("\\", "\\\\").replace('"', '\\"')


def lookup(fuseki, text: str) -> list[Term]:
    match = (
        '{ ?term skos:prefLabel ?l } UNION { ?term skos:altLabel ?l }\n'
        f'    FILTER (LCASE(STR(?l)) = LCASE("{safe(text)}"))'
    )
    query = iri.PREFIXES + TERMS % {"glossary": iri.G_GLOSSARY, "match": match}
    return _terms(fuseki.query(query)["results"]["bindings"])


def by_id(fuseki, term_id: str) -> Term | None:
    if not re.match(r"^[a-z0-9-]+$", term_id):
        return None
    match = f"FILTER (?term = <{term_iri(term_id)}>)"
    query = iri.PREFIXES + TERMS % {"glossary": iri.G_GLOSSARY, "match": match}
    found = _terms(fuseki.query(query)["results"]["bindings"])
    return found[0] if found else None


def concepts(fuseki, text: str) -> list[dict]:
    """Not a business term — perhaps a concept in a vocabulary, and how it maps."""
    query = iri.PREFIXES + CONCEPTS % {
        "text": safe(text),
        "ontology": iri.G_ONTOLOGY,
        "sali": iri.G_SALI,
        "glossary": iri.G_GLOSSARY,
    }
    out: dict[str, dict] = {}
    for row in fuseki.query(query)["results"]["bindings"]:
        v = {k: c["value"] for k, c in row.items()}
        hit = out.setdefault(
            v["concept"],
            {"concept": iri.shorten(v["concept"]), "label": v["label"],
             "scheme": iri.shorten(v.get("scheme", "")) or None, "mappings": []},
        )
        if "other" in v:
            link = {"relation": "skos:" + v["match"].rsplit("#", 1)[-1],
                    "to": iri.shorten(v["other"]), "label": v.get("otherLabel")}
            if link not in hit["mappings"]:
                hit["mappings"].append(link)
    return list(out.values())
