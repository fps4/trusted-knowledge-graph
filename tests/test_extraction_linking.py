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
