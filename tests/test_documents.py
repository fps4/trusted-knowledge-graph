"""The documents are the ground truth, written down — and the manifest says so exactly."""

from pathlib import Path

import pytest

from tkg.ingest import documents as documents_mod
from tkg.ingest import estate as estate_mod

CONFIG = Path("/app/config/estate.yaml")


@pytest.fixture(scope="module")
def world():
    cfg = estate_mod.load_config(CONFIG)
    est = estate_mod.build(cfg, 20260924)
    return cfg, est, documents_mod.build(est, cfg, 20260924)


def test_generation_is_deterministic(world):
    cfg, est, docs = world
    again = documents_mod.build(est, cfg, 20260924)
    assert [d.__dict__ for d in docs] == [d.__dict__ for d in again]


def test_every_outcome_in_a_document_is_the_true_one(world):
    _, est, docs = world
    for d in docs:
        for f in d.facts:
            if f["predicate"] == "hadOutcome":
                assert f["object"] == f"gl:outcome/{est.outcomes[f['subject']]}"


def test_an_open_matter_has_no_outcome_anywhere(world):
    _, est, docs = world
    assert "M-2024-0286" not in est.outcomes
    # A note filed on it states another matter's outcome — never its own.
    assert not [f for d in docs for f in d.facts
                if f["predicate"] == "hadOutcome" and f["subject"] == "M-2024-0286"]


def test_the_demo_matters_carry_what_the_scenes_need(world):
    _, _, docs = world
    kinds = {d.doc_type for d in docs if d.matter == "M-2022-0117"}
    assert {"engagement-letter", "advice-memo", "closing-letter"} <= kinds


def test_a_restricted_matters_documents_say_so(world):
    _, est, docs = world
    restricted = {r.matter_ref for r in est.restrictions}
    for d in docs:
        assert d.confidentiality.startswith("STRICTLY") == (d.matter in restricted)


def test_the_told_outcomes_agree_with_the_ground_truth(world):
    _, est, _ = world
    assert est.outcomes["M-2022-0117"] == "settled-fine"
    assert est.outcomes["M-2022-0022"] == "formal-warning"


def test_the_committed_fixture_is_what_the_estate_generates(world):
    _, _, docs = world
    committed = documents_mod.read(Path("/app/data/fixtures/documents.jsonl"))
    assert [d.__dict__ for d in committed] == [d.__dict__ for d in docs]


def test_a_pdf_renders_to_the_same_bytes_every_time(world):
    from tkg import dms

    d = world[2][0]
    assert dms.render_pdf(d) == dms.render_pdf(d)
    assert d.matter in dms.pdf_text(dms.render_pdf(d))
