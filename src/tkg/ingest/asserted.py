"""The capture step: facts told by a named person, with no document behind them.

Each fact is written into its own graph, g:asserted/<person>/<date>, and the
graph is described in g:prov — derived from what, attributed to whom. That
lineage is the only thing that lets a barrier reach a fact whose subject is not a
matter, so a fact whose lineage does not resolve is refused here, before the
shapes and long before the store. See docs/decisions/0008 and 0014.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml
from rdflib import RDF, Dataset, Literal, Namespace, URIRef
from rdflib.namespace import XSD

from .. import iri

SSF = Namespace(iri.FIRM)
PROV = Namespace("http://www.w3.org/ns/prov#")

SCHEMES = {"outcome", "expertise"}


class LineageError(ValueError):
    pass


def _ref(ref: str, graphs: dict[str, str]) -> str:
    """matter/M-…, person/P-…, outcome/…, expertise/…, or asserted/<person>/<date>."""
    kind, _, rest = ref.partition("/")
    if kind == "matter":
        return iri.matter(rest)
    if kind == "person":
        return iri.person(rest)
    if kind in SCHEMES:
        return iri.concept(kind, rest)
    if kind == "asserted":
        target = iri.G_ASSERTED + rest
        if target not in graphs.values():
            raise LineageError(f"derived from {ref}, which is not a graph in this file")
        return target
    raise LineageError(f"cannot resolve {ref!r}")


def load(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())["facts"]


def build(facts: list[dict]) -> Dataset:
    graphs: dict[str, str] = {}
    for f in facts:
        g = iri.asserted_graph(f["by"], str(f["told_on"]))
        if g in graphs.values():
            raise LineageError(f"{f['id']}: one fact per graph, and {g} is taken")
        graphs[f["id"]] = g

    ds = Dataset()
    prov = ds.graph(URIRef(iri.G_PROV))
    for f in facts:
        g_iri = graphs[f["id"]]
        if not f.get("derived_from"):
            raise LineageError(f"{f['id']}: no lineage — it would escape every barrier")
        graph = ds.graph(URIRef(g_iri))
        node = URIRef(iri.fact(f["id"]))
        told_on = f["told_on"]
        on = told_on if isinstance(told_on, date) else date.fromisoformat(str(told_on))
        graph.add((node, RDF.type, SSF.Fact))
        graph.add((node, SSF.factSubject, URIRef(_ref(f["subject"], graphs))))
        graph.add((node, SSF.factPredicate, SSF[f["predicate"]]))
        graph.add((node, SSF.factObject, URIRef(_ref(f["object"], graphs))))
        graph.add((node, SSF.confidence, Literal(Decimal(str(f["confidence"])))))
        graph.add((node, SSF.reviewState, Literal(f["review"])))
        graph.add((node, SSF.assertedBy, URIRef(iri.person(f["by"]))))
        graph.add((node, SSF.assertedOn, Literal(on, datatype=XSD.date)))

        subject = URIRef(g_iri)
        prov.add((subject, RDF.type, SSF.DerivedGraph))
        prov.add((subject, PROV.wasAttributedTo, URIRef(iri.person(f["by"]))))
        for source in f["derived_from"]:
            prov.add((subject, PROV.wasDerivedFrom, URIRef(_ref(source, graphs))))
    return ds


def write(ds: Dataset, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = sorted(
        line for line in ds.serialize(format="nquads").splitlines() if line.strip()
    )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)
