"""Slots are the only way into a query, and they are checked."""

import pytest

from tkg import iri
from tkg.semantic.templates import TEMPLATES, SlotError


def test_every_template_binds_with_its_defaults():
    for template in TEMPLATES.values():
        query, slots = template.bind()
        assert "{{" not in query, f"{template.id} left a slot unbound"
        assert query.startswith("PREFIX")
        assert set(slots) == {s.name for s in template.slots}


def test_a_bound_value_reaches_the_query():
    query, _ = TEMPLATES["CQ-01"].bind({"client": iri.client("C-0071")})
    assert "<https://lab.fps4.dev/id/client/C-0071>" in query


def test_a_slot_that_is_not_an_identifier_in_this_estate_is_refused():
    with pytest.raises(SlotError):
        TEMPLATES["CQ-01"].bind({"client": "https://example.org/evil"})


def test_a_slot_cannot_smuggle_sparql():
    with pytest.raises(SlotError):
        TEMPLATES["CQ-01"].bind({"client": "https://lab.fps4.dev/id/client/X> } DROP ALL #"})


def test_a_date_slot_must_be_a_date():
    with pytest.raises(SlotError):
        TEMPLATES["CQ-02"].bind({"since": "last tuesday"})


def test_an_unknown_slot_is_refused_rather_than_ignored():
    with pytest.raises(SlotError):
        TEMPLATES["CQ-01"].bind({"clientt": iri.client("C-0042")})


def test_every_template_reports_the_graph_each_row_came_from():
    for template in TEMPLATES.values():
        if template.id == "CQ-05":
            continue  # an aggregate over graphs, not a row-level citation
        assert "g" in template.columns, f"{template.id} returns facts with no source"
