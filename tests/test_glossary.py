"""The glossary compiles to SKOS, every entry has an owner, and SALI is mapped, not guessed."""

import re
from pathlib import Path

import pytest
from rdflib import Graph

from tkg.ingest.loader import validate
from tkg.semantic import glossary
from tkg.semantic.templates import TEMPLATES, TERM_QUESTIONS

CONFIG = Path("/app/config")
SALI = Path("/app/vocab/sali-lmss-subset.ttl")


@pytest.fixture(scope="module")
def compiled():
    terms, mapping = glossary.load_config(CONFIG)
    return terms, mapping, glossary.build_turtle(terms, mapping)


def test_the_glossary_is_valid_turtle(compiled):
    *_, ttl = compiled
    assert len(Graph().parse(data=ttl, format="turtle")) > 50


def test_active_client_has_four_readings_and_four_owners(compiled):
    terms, *_ = compiled
    active = next(t for t in terms["terms"] if t["id"] == "active-client")
    assert len(active["readings"]) == 4
    assert len({r["owner"] for r in active["readings"]}) == 4
    assert active["on_ambiguous"] == "ask"


def test_every_reading_is_served_by_a_template_that_exists(compiled):
    terms, *_ = compiled
    for t in terms["terms"]:
        for r in t.get("readings", []):
            assert r["template"] in TEMPLATES, r
            assert TEMPLATES[r["template"]].listed is False


def test_every_term_question_names_a_term_in_the_glossary(compiled):
    terms, *_ = compiled
    ids = {t["id"] for t in terms["terms"]}
    assert all(q.term in ids for q in TERM_QUESTIONS.values())


def test_every_mapped_sali_concept_was_imported(compiled):
    _, mapping, _ = compiled
    imported = set(re.findall(r"<http://lmss\.sali\.org/(\w+)> a owl:Class, skos:Concept",
                              SALI.read_text()))
    mapped = {link["sali"] for scheme in ("practice-area", "matter-type")
              for links in mapping[scheme].values() for link in links}
    assert mapped and mapped <= imported


def test_the_sali_namespace_is_the_published_one_not_a_guess(compiled):
    _, mapping, ttl = compiled
    assert mapping["source"]["namespace"] == "http://lmss.sali.org/"
    assert "https://sali.org/" not in ttl
    assert re.match(r"^[0-9a-f]{40}$", mapping["source"]["commit"])


def test_a_mapping_relation_must_be_a_skos_mapping_relation():
    with pytest.raises(glossary.TermError):
        glossary.build_turtle({"terms": []},
                              {"practice-area": {"tmt": [{"match": "sameAs", "sali": "X"}]}})


def test_a_term_without_an_owner_does_not_load(compiled):
    terms, mapping, _ = compiled
    broken = {"terms": [{**terms["terms"][1], "owner": ""}]}
    ttl = glossary.build_turtle(broken, {}).replace('ssf:owner ""', "")
    data = Graph().parse(data=ttl, format="turtle")
    data.parse("/app/ontology/firm.ttl")
    result = validate(data, Path("/app/ontology/shapes.ttl"), Path("/app/ontology/firm.ttl"))
    assert not result.conforms
    assert "owner" in result.report


def test_free_text_is_refused_before_it_reaches_a_query():
    with pytest.raises(glossary.TermError):
        glossary.safe('client" } DROP ALL #')
    assert glossary.safe("active client") == "active client"
