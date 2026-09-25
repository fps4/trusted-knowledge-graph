"""Slots are the only way into a query, and they are checked. Every graph a query
touches is declared, and the binder constrains every one."""

import pytest

from tkg import iri
from tkg.semantic.templates import GRAPH_VAR_RE, TEMPLATES, SlotError


def test_every_template_binds_with_its_defaults():
    for template in TEMPLATES.values():
        slots = template.check_slots({})
        query = template.bind(slots, [], [])
        assert "{{" not in query, f"{template.id} left a placeholder unbound"
        assert query.startswith("PREFIX")
        assert set(slots) == {s.name for s in template.slots}


def test_a_bound_value_reaches_the_query():
    t = TEMPLATES["CQ-01"]
    query = t.bind(t.check_slots({"client": iri.client("C-0071")}), [], [])
    assert "<https://lab.fps4.dev/id/client/C-0071>" in query


def test_short_forms_expand_to_identifiers_in_this_estate():
    t = TEMPLATES["CQ-06"]
    assert t.check_slots({"matter": "M-2022-0117"})["matter"] == iri.matter("M-2022-0117")
    assert TEMPLATES["CQ-01"].check_slots({"client": "C-0042"})["client"] == iri.client("C-0042")
    got = TEMPLATES["CQ-02"].check_slots({"jurisdiction": "id:jurisdiction/GB"})
    assert got["jurisdiction"] == iri.jurisdiction("GB")


def test_a_slot_that_is_not_an_identifier_in_this_estate_is_refused():
    with pytest.raises(SlotError):
        TEMPLATES["CQ-01"].check_slots({"client": "https://example.org/evil"})


def test_a_slot_cannot_smuggle_sparql():
    with pytest.raises(SlotError):
        TEMPLATES["CQ-01"].check_slots({"client": "https://lab.fps4.dev/id/client/X> } DROP ALL #"})


def test_a_date_slot_must_be_a_date():
    with pytest.raises(SlotError):
        TEMPLATES["CQ-02"].check_slots({"since": "last tuesday"})


def test_an_unknown_slot_is_refused_rather_than_ignored():
    with pytest.raises(SlotError):
        TEMPLATES["CQ-01"].check_slots({"clientt": iri.client("C-0042")})


def test_every_row_level_template_reports_the_graph_each_row_came_from():
    for template in TEMPLATES.values():
        if template.kind == "aggregate":
            continue  # an aggregate over graphs, not a row-level citation
        assert {"g", "fg"} & set(template.columns), f"{template.id} returns facts with no source"


def test_every_graph_variable_is_declared_and_constrained():
    """An undeclared GRAPH ?x could match a graph nobody decided on."""
    for template in TEMPLATES.values():
        used = set(GRAPH_VAR_RE.findall(template.where))
        assert used == set(template.graphs), f"{template.id}: {used ^ set(template.graphs)}"
        for var in used:
            assert "{{graph:" + var + "}}" in template.where, f"{template.id} ?{var}"


def test_every_matter_template_carries_the_access_placeholder():
    for template in TEMPLATES.values():
        if template.matter_var:
            assert "{{access:" + template.matter_var + "}}" in template.where, template.id


def test_the_bound_query_cannot_name_a_matter_it_was_not_given():
    t = TEMPLATES["CQ-02"]
    query = t.bind(t.check_slots({}), [iri.matter("M-2021-0043")], [])
    assert "M-2022-0117" not in query
    assert "VALUES ?matter { <https://lab.fps4.dev/id/matter/M-2021-0043> }" in query


def test_no_permitted_derived_graph_means_none_is_read():
    t = TEMPLATES["CQ-08"]
    assert "FILTER (false)" in t.bind(t.check_slots({}), [], [])


def test_the_candidate_query_reaches_but_selects_identifiers_only():
    t = TEMPLATES["CQ-02"]
    query = t.candidates(t.check_slots({}))
    assert "SELECT DISTINCT ?matter ?fg ?rg WHERE" in query  # reviews reached too
    assert "VALUES ?matter" not in query


def test_a_question_that_reaches_no_matter_or_derived_graph_has_no_candidates():
    t = TEMPLATES["CQ-04"]
    assert t.candidates(t.check_slots({})) == ""


# ── CQ-10 withholds a document whose extracted graph was not permitted (ADR 0028) ─
def test_the_guard_withholds_nothing_in_the_candidate_query():
    t = TEMPLATES["CQ-10"]
    query = t.candidates(t.check_slots({"matter": "M-2024-0286"}))
    assert "FILTER NOT EXISTS { GRAPH ?xg { ?xf ssf:fromDocument ?doc } FILTER (false) }" in query
    assert "?xg" not in query.split("WHERE")[0]  # reaches nothing; ?fg is the candidate


def test_the_guard_withholds_a_document_whose_graph_was_not_permitted():
    t = TEMPLATES["CQ-10"]
    ok = iri.doc_graph("DOC-0585")
    query = t.bind(t.check_slots({"matter": "M-2024-0286"}),
                   [iri.matter("M-2024-0286")], [ok])
    assert f"FILTER (?xg NOT IN (<{ok}>))" in query
    # Nothing permitted: any document with an extracted graph is withheld.
    bare = t.bind(t.check_slots({"matter": "M-2024-0286"}), [iri.matter("M-2024-0286")], [])
    assert "FILTER NOT EXISTS { GRAPH ?xg { ?xf ssf:fromDocument ?doc }  }" in bare


def test_a_guard_is_not_a_derived_graph_the_template_reaches():
    assert TEMPLATES["CQ-10"].derived == ("fg",)


def test_cq10_run_over_a_real_dataset_withholds_only_the_note_citing_a_walled_matter():
    """The bound query, executed by rdflib over the documents' own graphs."""
    from pathlib import Path

    from rdflib import Dataset

    from tkg.ingest import estate as estate_mod
    from tkg.ingest.docgraph import Lookups, dms_metadata, doc_facts
    from tkg.ingest.documents import Document

    cfg = estate_mod.load_config(Path("/app/config/estate.yaml"))
    lookups = Lookups.from_estate(estate_mod.build(cfg, 20260924), cfg)
    host = "M-2024-0286"
    letter = Document("DOC-9001", host, "engagement-letter", "2024-01-01", "t", "p", "")
    note = Document("DOC-9002", host, "knowledge-note", "2025-01-01", "t", "p", "")
    rows = {
        letter.doc_id: {"model": "m", "facts": [
            {"predicate": "ledBy", "object": "Mara de Vries", "confidence": 1, "evidence": ""}]},
        note.doc_id: {"model": "m", "facts": [
            {"predicate": "citesMatter", "object": "M-2022-0117", "confidence": 1,
             "evidence": ""}]},
    }
    facts, _ = doc_facts([letter, note], rows, {}, lookups)

    class Snapshot(Dataset):
        # rdflib's in-memory store adds contexts while a nested GRAPH ?x is being
        # iterated; iterating a snapshot keeps the evaluation honest and stable.
        def contexts(self, triple=None):
            return iter(list(super().contexts(triple)))

    ds = Snapshot(default_union=False)
    for source in (dms_metadata([letter, note]), facts):
        for quad in source.quads((None, None, None, None)):
            ds.add(quad)
    t = TEMPLATES["CQ-10"]
    slots = t.check_slots({"matter": host})

    def listed(permitted_graphs):
        query = t.bind(slots, [iri.matter(host)], permitted_graphs)
        return {str(r["docId"]) for r in ds.query(query)}

    both = [iri.doc_graph(letter.doc_id), iri.doc_graph(note.doc_id)]
    assert listed(both) == {"DOC-9001", "DOC-9002"}
    # Walled from M-2022-0117: the note's graph is denied by lineage, so the note goes.
    assert listed([iri.doc_graph(letter.doc_id)]) == {"DOC-9001"}
