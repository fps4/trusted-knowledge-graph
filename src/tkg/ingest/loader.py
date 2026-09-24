"""Validate, then load. In that order, and the order is the point.

SHACL is the load contract: a load that violates the shapes does not land, and
the violation report is the error message. Validating before anything reaches the
store is what makes that true rather than aspirational.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
from rdflib import Dataset, Graph

from .. import iri

TIMEOUT = httpx.Timeout(120.0)


@dataclass
class ValidationResult:
    conforms: bool
    report: str
    triples: int


def union_graph(quads_paths: list[Path], extra_turtle: list[Path | str]) -> Graph:
    ds = Dataset()
    for quads_path in quads_paths:
        ds.parse(str(quads_path), format="nquads")
    union = Graph()
    for _s, _p, _o, _g in ds.quads((None, None, None, None)):
        union.add((_s, _p, _o))
    for extra in extra_turtle:
        if isinstance(extra, Path):
            union.parse(str(extra), format="turtle")
        else:
            union.parse(data=extra, format="turtle")
    return union


def validate(data: Graph, shapes_path: Path, ontology_path: Path) -> ValidationResult:
    from pyshacl import validate as shacl_validate

    shapes = Graph().parse(str(shapes_path), format="turtle")
    ontology = Graph().parse(str(ontology_path), format="turtle")
    conforms, _graph, text = shacl_validate(
        data_graph=data,
        shacl_graph=shapes,
        ont_graph=ontology,
        advanced=True,          # sh:sparql constraints — the no-content rule needs this
        inference="none",
        abort_on_first=False,
        meta_shacl=False,
    )
    return ValidationResult(conforms=conforms, report=text, triples=len(data))


class Fuseki:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def _post(self, path: str, *, content: bytes | str, content_type: str, params=None):
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(
                f"{self.base}{path}",
                content=content,
                params=params or {},
                headers={"Content-Type": content_type},
            )
            response.raise_for_status()
            return response

    def drop_all(self) -> None:
        self._post("/update", content="DROP ALL", content_type="application/sparql-update")

    def load_quads(self, path: Path) -> None:
        self._post("/data", content=path.read_bytes(), content_type="application/n-quads")

    def load_turtle(self, turtle: str, graph: str) -> None:
        self._post(
            "/data", content=turtle.encode(), content_type="text/turtle", params={"graph": graph}
        )

    def query(self, sparql: str) -> dict:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(
                f"{self.base}/sparql",
                data={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
            )
            response.raise_for_status()
            return response.json()

    def count(self) -> int:
        result = self.query("SELECT (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } }")
        return int(result["results"]["bindings"][0]["n"]["value"])

    def graphs(self) -> list[tuple[str, int]]:
        result = self.query(
            "SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g ORDER BY ?g"
        )
        return [
            (row["g"]["value"], int(row["n"]["value"])) for row in result["results"]["bindings"]
        ]

    def ping(self) -> bool:
        try:
            self.count()
            return True
        except Exception:
            return False


def push(
    fuseki: Fuseki,
    quads_paths: list[Path],
    ontology_path: Path,
    taxonomy_ttl: str,
    glossary_ttl: str = "",
    sali_path: Path | None = None,
) -> None:
    fuseki.drop_all()
    for quads_path in quads_paths:
        fuseki.load_quads(quads_path)
    fuseki.load_turtle(ontology_path.read_text(), iri.G_ONTOLOGY)
    fuseki.load_turtle(taxonomy_ttl, iri.G_ONTOLOGY)
    if glossary_ttl:
        fuseki.load_turtle(glossary_ttl, iri.G_GLOSSARY)
    if sali_path is not None:
        fuseki.load_turtle(sali_path.read_text(), iri.G_SALI)
