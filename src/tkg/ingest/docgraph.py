"""Documents into the graph: metadata, and the facts extracted from them.

The document store's metadata — id, matter, type, date, object key — becomes
g:spine/dms. Never the text. Each document's extracted facts go into their own
graph, g:doc/<docId>, derived from the document and from its matter, so a fact
extracted from a restricted matter's document is restricted by lineage whatever
it is about. docs/decisions/0008.

Linking extracted strings to identifiers is deterministic and conservative:
an exact full name, an exact client name, a vocabulary identifier. Anything else
stays unlinked, with the reason — a surname shared by two colleagues, a client
spelled the way the CRM spells it. Guessing would turn a recall problem into a
precision problem, and the second is the one that hurts a lawyer.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from rdflib import RDF, Dataset, Literal, Namespace, URIRef
from rdflib.namespace import XSD

from .. import iri
from ..dms import key as object_key
from .documents import Document
from .estate import Estate

SSF = Namespace(iri.FIRM)
PROV = Namespace("http://www.w3.org/ns/prov#")
PIPELINE = "extract/1"


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


@dataclass
class Lookups:
    people: dict[str, list[str]]  # normalised full name -> person refs
    clients: dict[str, str]  # normalised PMS name -> client ref
    crm_names: set[str]  # normalised CRM account names
    vocab: dict[str, dict[str, str]]  # scheme -> id or normalised label -> iri

    @classmethod
    def from_estate(cls, est: Estate, cfg: dict) -> Lookups:
        people: dict[str, list[str]] = {}
        for p in est.people:
            people.setdefault(_norm(f"{p.given_name} {p.family_name}"), []).append(p.person_ref)
        vocab: dict[str, dict[str, str]] = {}
        for scheme, key in (("matterType", "matter_types"), ("hadOutcome", "outcomes")):
            prefix = "matter-type" if scheme == "matterType" else "outcome"
            vocab[scheme] = {}
            for x in cfg[key]:
                target = iri.concept(prefix, x["id"])
                vocab[scheme][_norm(x["id"])] = target
                vocab[scheme][_norm(x["label"])] = target
        vocab["inJurisdiction"] = {}
        for j in cfg["jurisdictions"]:
            vocab["inJurisdiction"][_norm(j["id"])] = iri.jurisdiction(j["id"])
            vocab["inJurisdiction"][_norm(j["label"])] = iri.jurisdiction(j["id"])
        return cls(
            people=people,
            clients={_norm(c.name): c.client_ref for c in est.clients},
            crm_names={_norm(a.name) for a in est.accounts},
            vocab=vocab,
        )

    def link(self, predicate: str, obj: str) -> tuple[str | None, str]:
        name = _norm(obj)
        if predicate in ("ledBy", "workedOn"):
            refs = self.people.get(name, [])
            if len(refs) == 1:
                return iri.person(refs[0]), "linked"
            return None, "name matches no one" if not refs else f"name matches {len(refs)} people"
        if predicate == "forClient":
            if name in self.clients:
                return iri.client(self.clients[name]), "linked"
            if name in self.crm_names:
                return None, "CRM spelling — identity not resolved"
            return None, "organisation not found"
        target = self.vocab.get(predicate, {}).get(name)
        return (target, "linked") if target else (None, "not in the vocabulary")


@dataclass
class LinkStats:
    linked: int = 0
    unlinked: Counter = field(default_factory=Counter)
    rejected: Counter = field(default_factory=Counter)


def linked_facts(doc: Document, row: dict, text: str, lookups: Lookups,
                 stats: LinkStats | None = None) -> list[dict]:
    """Extracted facts for one document, with identifiers — or without, and why."""
    out = []
    for f in row.get("facts", []):
        if f["predicate"] not in {"forClient", "ledBy", "matterType", "inJurisdiction",
                                  "workedOn", "hadOutcome"}:
            if stats:
                stats.rejected["predicate not in the ontology"] += 1
            continue
        target, why = lookups.link(f["predicate"], f["object"])
        if target is None:
            if stats:
                stats.unlinked[why] += 1
            continue
        if stats:
            stats.linked += 1
        start = text.find(f["evidence"]) if f.get("evidence") else -1
        out.append({
            "predicate": f["predicate"], "object": target,
            "confidence": max(0.0, min(1.0, float(f["confidence"]))),
            "span": (start, start + len(f["evidence"])) if start >= 0 else None,
        })
    return out


def dms_metadata(docs: list[Document]) -> Dataset:
    ds = Dataset()
    g = ds.graph(URIRef(iri.G_SPINE_DMS))
    for d in docs:
        node = URIRef(iri.document(d.doc_id))
        g.add((node, RDF.type, SSF.Document))
        g.add((node, SSF.documentMatter, URIRef(iri.matter(d.matter))))
        g.add((node, SSF.docType, Literal(d.doc_type)))
        g.add((node, SSF.documentDate, Literal(d.date, datatype=XSD.date)))
        g.add((node, SSF.objectKey, Literal(object_key(d))))
    return ds


def doc_facts(docs: list[Document], extraction: dict[str, dict], texts: dict[str, str],
              lookups: Lookups) -> tuple[Dataset, LinkStats]:
    ds = Dataset()
    prov = ds.graph(URIRef(iri.G_PROV))
    stats = LinkStats()
    for d in docs:
        row = extraction.get(d.doc_id)
        if not row:
            continue
        facts = linked_facts(d, row, texts.get(d.doc_id, ""), lookups, stats)
        if not facts:
            continue
        graph_iri = URIRef(iri.doc_graph(d.doc_id))
        graph = ds.graph(graph_iri)
        for n, f in enumerate(facts, start=1):
            node = URIRef(iri.fact(f"{d.doc_id}-{n}"))
            graph.add((node, RDF.type, SSF.Fact))
            graph.add((node, SSF.factSubject, URIRef(iri.matter(d.matter))))
            graph.add((node, SSF.factPredicate, SSF[f["predicate"]]))
            graph.add((node, SSF.factObject, URIRef(f["object"])))
            graph.add((node, SSF.confidence, Literal(Decimal(str(round(f["confidence"], 3))))))
            graph.add((node, SSF.reviewState, Literal("extracted")))
            graph.add((node, SSF.fromDocument, URIRef(iri.document(d.doc_id))))
            graph.add((node, SSF.extractedBy, Literal(f"{row['model']} · {PIPELINE}")))
            if f["span"]:
                graph.add((node, SSF.charStart, Literal(f["span"][0], datatype=XSD.integer)))
                graph.add((node, SSF.charEnd, Literal(f["span"][1], datatype=XSD.integer)))
        prov.add((graph_iri, RDF.type, SSF.DerivedGraph))
        prov.add((graph_iri, PROV.wasDerivedFrom, URIRef(iri.document(d.doc_id))))
        prov.add((graph_iri, PROV.wasDerivedFrom, URIRef(iri.matter(d.matter))))
        prov.add((graph_iri, PROV.wasAttributedTo, Literal(f"{row['model']} · {PIPELINE}")))
    return ds, stats


def reviews(rows: list[dict], existing_graphs: set[str]) -> tuple[Dataset, int]:
    """Replay review decisions — the durable record of who confirmed or rejected what —
    into g:review/<factId>. A review whose fact no longer exists is skipped, not kept."""
    ds = Dataset()
    prov = ds.graph(URIRef(iri.G_PROV))
    latest: dict[str, dict] = {}
    for r in rows:
        latest[r["fact"]] = r  # the last decision on a fact is the one that stands
    skipped = 0
    for fact_id, r in sorted(latest.items()):
        if r["graph"] not in existing_graphs:
            skipped += 1
            continue
        g_iri = URIRef(iri.review_graph(fact_id))
        g = ds.graph(g_iri)
        node = URIRef(f"{iri.ID}review/{fact_id}")
        g.add((node, RDF.type, SSF.Review))
        g.add((node, SSF.reviews, URIRef(iri.fact(fact_id))))
        g.add((node, SSF.verdict, Literal(r["verdict"])))
        g.add((node, SSF.reviewedBy, URIRef(iri.person(r["by"]))))
        g.add((node, SSF.reviewedOn, Literal(r["on"], datatype=XSD.date)))
        prov.add((g_iri, RDF.type, SSF.DerivedGraph))
        prov.add((g_iri, PROV.wasDerivedFrom, URIRef(r["graph"])))
        prov.add((g_iri, PROV.wasAttributedTo, URIRef(iri.person(r["by"]))))
    return ds, skipped
