"""Namespaces and identifier shapes.

The base IRI is one this lab owns and deliberately does not dereference. A
linked-data repo that ships IRIs implying a live vocabulary service is making a
claim it cannot keep.
"""

BASE = "https://lab.fps4.dev/"

FIRM = BASE + "firm/"
ID = BASE + "id/"
GLOSSARY = BASE + "glossary/"
GRAPH = BASE + "graph/"

# Named graphs are the unit of provenance and, from M1, the unit of access.
G_SPINE_PMS = GRAPH + "spine/pms"
G_SPINE_CRM = GRAPH + "spine/crm"
G_SPINE_HR = GRAPH + "spine/hr"
G_ONTOLOGY = GRAPH + "ontology"
# Statements about graphs, not inside them: lineage, attribution.
G_PROV = GRAPH + "prov"
# One graph per fact told by a person: g:asserted/<personRef>/<date>.
G_ASSERTED = GRAPH + "asserted/"

# The business glossary, and the slice of SALI LMSS it maps to.
G_GLOSSARY = GRAPH + "glossary"
G_SALI = GRAPH + "vocab/sali"

SPINE_GRAPHS = (G_SPINE_PMS, G_SPINE_CRM, G_SPINE_HR)
VOCAB_GRAPHS = (G_ONTOLOGY, G_GLOSSARY, G_SALI)

PREFIXES = """PREFIX ssf:  <https://lab.fps4.dev/firm/>
PREFIX id:   <https://lab.fps4.dev/id/>
PREFIX gl:   <https://lab.fps4.dev/glossary/>
PREFIX g:    <https://lab.fps4.dev/graph/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX lmss: <http://lmss.sali.org/>
"""


def person(ref: str) -> str:
    return f"{ID}person/{ref}"


def client(ref: str) -> str:
    return f"{ID}client/{ref}"


def matter(ref: str) -> str:
    return f"{ID}matter/{ref}"


def office(name: str) -> str:
    return f"{ID}office/{name}"


def jurisdiction(code: str) -> str:
    return f"{ID}jurisdiction/{code}"


def fact(ref: str) -> str:
    return f"{ID}fact/{ref}"


def asserted_graph(person_ref: str, on: str) -> str:
    return f"{G_ASSERTED}{person_ref}/{on}"


def matter_ref(matter_iri: str) -> str | None:
    """M-2022-0117 from its IRI, or None if it is not a matter."""
    prefix = f"{ID}matter/"
    return matter_iri[len(prefix) :] if matter_iri.startswith(prefix) else None


def concept(scheme: str, ident: str) -> str:
    return f"{GLOSSARY}{scheme}/{ident}"


def shorten(iri: str) -> str:
    """A readable form for terminal output, without losing what it refers to."""
    for long, short in (
        (ID, "id:"),
        (GLOSSARY, "gl:"),
        (GRAPH, "g:"),
        (FIRM, "ssf:"),
        ("http://lmss.sali.org/", "lmss:"),
    ):
        if iri.startswith(long):
            return short + iri[len(long) :]
    return iri
