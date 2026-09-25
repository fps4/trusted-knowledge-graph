"""Extraction proposes strings; linking turns them into identifiers — exactly, or not at all."""

from pathlib import Path

import pytest
from rdflib import Graph

from tkg import iri
from tkg.ingest import estate as estate_mod
from tkg.ingest.docgraph import Lookups
from tkg.ingest.extract import PREDICATES, schema


@pytest.fixture(scope="module")
def lookups():
    cfg = estate_mod.load_config(Path("/app/config/estate.yaml"))
    return Lookups.from_estate(estate_mod.build(cfg, 20260924), cfg)


def test_a_full_name_links(lookups):
    assert lookups.link("ledBy", "Mara de Vries") == (iri.person("P-0101"), "linked")


def test_a_surname_alone_does_not(lookups):
    assert lookups.link("ledBy", "de Vries")[0] is None


def test_the_crm_spelling_stays_unlinked_and_says_why(lookups):
    target, why = lookups.link("forClient", "Delta Fondsen Stichting")
    assert target is None and why.startswith("CRM spelling")


def test_the_practice_management_name_links(lookups):
    assert lookups.link("forClient", "Stichting Delta Fondsen")[0] == iri.client("C-0042")


def test_vocabulary_by_id_or_label(lookups):
    assert lookups.link("hadOutcome", "settled-fine")[0] == iri.concept("outcome", "settled-fine")
    assert lookups.link("inJurisdiction", "Netherlands")[0] == iri.jurisdiction("NL")
    assert lookups.link("hadOutcome", "a good result")[0] is None


def test_the_extraction_schema_can_only_say_what_the_shapes_accept():
    shapes = Graph().parse("/app/ontology/shapes.ttl")
    allowed = {str(o).rsplit("/", 1)[-1] for o in shapes.objects()
               if str(o).startswith(iri.FIRM)}
    enum = set(schema({})["properties"]["facts"]["items"]["properties"]["predicate"]["enum"])
    assert enum == set(PREDICATES)
    assert enum <= allowed


# ── citations: a document cites a matter by its file number (ADR 0028) ──────────
from rdflib import URIRef  # noqa: E402

from tkg.ingest.docgraph import LinkStats, doc_facts, linked_facts  # noqa: E402
from tkg.ingest.documents import Document  # noqa: E402

NOTE = Document("DOC-9001", "M-2024-0286", "knowledge-note", "2025-01-01", "t", "p", "")


def _row(*facts):
    return {"model": "test", "facts": [
        {"confidence": 0.9, "evidence": "", **f} for f in facts]}


def test_a_matter_reference_links_exactly(lookups):
    assert lookups.link("citesMatter", "M-2022-0117") == (iri.matter("M-2022-0117"), "linked")
    assert lookups.link("citesMatter", "m-2022-0117")[0] == iri.matter("M-2022-0117")
    assert lookups.link("citesMatter", "M-2099-0001")[0] is None
    assert lookups.link("citesMatter", "the Rhine Capital matter")[0] is None


def test_a_fact_about_a_cited_matter_keeps_that_matter_as_subject(lookups):
    facts = linked_facts(NOTE, _row(
        {"predicate": "citesMatter", "object": "M-2022-0117"},
        {"predicate": "hadOutcome", "object": "settled-fine", "subject": "M-2022-0117"},
        {"predicate": "matterType", "object": "regulatory-investigation"},
    ), "", lookups)
    got = {(f["predicate"], f["subject"]) for f in facts}
    assert got == {("citesMatter", "M-2024-0286"), ("hadOutcome", "M-2022-0117"),
                   ("matterType", "M-2024-0286")}


def test_a_fact_about_a_matter_the_document_does_not_cite_is_rejected(lookups):
    stats = LinkStats()
    facts = linked_facts(NOTE, _row(
        {"predicate": "hadOutcome", "object": "settled-fine", "subject": "M-2022-0117"},
        {"predicate": "hadOutcome", "object": "settled-fine", "subject": "M-2099-0001"},
    ), "", lookups, stats)
    assert facts == [] and sum(stats.rejected.values()) == 2


def test_a_document_cannot_cite_its_own_matter_or_cite_on_another_matters_behalf(lookups):
    stats = LinkStats()
    facts = linked_facts(NOTE, _row(
        {"predicate": "citesMatter", "object": "M-2024-0286"},
        {"predicate": "citesMatter", "object": "M-2022-0117"},
        {"predicate": "citesMatter", "object": "M-2021-0043", "subject": "M-2022-0117"},
    ), "", lookups, stats)
    assert [(f["subject"], f["object"]) for f in facts] == [
        ("M-2024-0286", iri.matter("M-2022-0117"))]
    assert sum(stats.rejected.values()) == 2


def test_a_note_is_derived_from_every_matter_it_cites(lookups):
    ds, stats = doc_facts([NOTE], {NOTE.doc_id: _row(
        {"predicate": "citesMatter", "object": "M-2022-0117"},
        {"predicate": "hadOutcome", "object": "settled-fine", "subject": "M-2022-0117"},
    )}, {}, lookups)
    prov = ds.graph(URIRef(iri.G_PROV))
    derived = {str(o) for o in prov.objects(URIRef(iri.doc_graph(NOTE.doc_id)),
                                            URIRef("http://www.w3.org/ns/prov#wasDerivedFrom"))}
    assert derived == {iri.document(NOTE.doc_id), iri.matter("M-2024-0286"),
                       iri.matter("M-2022-0117")}
    assert stats.cites == {NOTE.doc_id: ["M-2022-0117"]}
    subjects = {str(o) for o in ds.graph(URIRef(iri.doc_graph(NOTE.doc_id))).objects(
        None, URIRef(iri.FIRM + "factSubject"))}
    assert subjects == {iri.matter("M-2024-0286"), iri.matter("M-2022-0117")}


def test_a_document_that_cites_nothing_is_derived_from_its_own_matter_only(lookups):
    doc = Document("DOC-9002", "M-2021-0043", "closing-letter", "2023-01-01", "t", "p", "")
    ds, stats = doc_facts([doc], {doc.doc_id: _row(
        {"predicate": "hadOutcome", "object": "settled-fine"})}, {}, lookups)
    prov = ds.graph(URIRef(iri.G_PROV))
    derived = {str(o) for o in prov.objects(URIRef(iri.doc_graph(doc.doc_id)),
                                            URIRef("http://www.w3.org/ns/prov#wasDerivedFrom"))}
    assert derived == {iri.document(doc.doc_id), iri.matter("M-2021-0043")}
    assert stats.cites == {}


def test_the_schema_offers_a_subject_but_does_not_require_one():
    item = schema({})["properties"]["facts"]["items"]
    assert "subject" in item["properties"] and "subject" not in item["required"]
    assert "citesMatter" in item["properties"]["predicate"]["enum"]
