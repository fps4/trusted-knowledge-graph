"""Told facts carry their lineage, or they do not load."""

from pathlib import Path

import pytest

from tkg import iri
from tkg.ingest import asserted

CONFIG = Path("/app/config/asserted.yaml")


def test_every_told_fact_has_a_graph_and_lineage():
    facts = asserted.load(CONFIG)
    ds = asserted.build(facts)
    prov = ds.graph(asserted.URIRef(iri.G_PROV))
    for f in facts:
        g = asserted.URIRef(iri.asserted_graph(f["by"], str(f["told_on"])))
        assert list(prov.objects(g, asserted.PROV.wasDerivedFrom)), f["id"]


def test_the_demo_matter_that_is_still_open_has_no_outcome():
    subjects = {f["subject"] for f in asserted.load(CONFIG) if f["predicate"] == "hadOutcome"}
    assert "matter/M-2024-0286" not in subjects


def test_lineage_is_transitive_in_the_fixture():
    """F-0005 derives from a graph, not a matter — the case that proves traversal."""
    f5 = next(f for f in asserted.load(CONFIG) if f["id"] == "F-0005")
    assert f5["derived_from"][0].startswith("asserted/")


def test_a_fact_with_no_lineage_is_refused():
    with pytest.raises(asserted.LineageError, match="escape every barrier"):
        asserted.build([{"id": "F-X", "by": "P-0101", "told_on": "2024-01-01",
                         "subject": "matter/M-1", "predicate": "hadOutcome",
                         "object": "outcome/no-action", "confidence": 1, "review": "confirmed",
                         "derived_from": []}])


def test_lineage_to_a_graph_that_does_not_exist_is_refused():
    with pytest.raises(asserted.LineageError, match="not a graph"):
        asserted.build([{"id": "F-X", "by": "P-0101", "told_on": "2024-01-01",
                         "subject": "person/P-0101", "predicate": "hasExpertise",
                         "object": "expertise/afm-settlement", "confidence": 1,
                         "review": "confirmed", "derived_from": ["asserted/P-9/2020-01-01"]}])
