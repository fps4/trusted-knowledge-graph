"""The estate has to be reproducible, and its mess has to be real."""

from pathlib import Path

import pytest

from tkg.ingest import estate as estate_mod

CONFIG = Path("/app/config/estate.yaml")


@pytest.fixture(scope="module")
def cfg() -> dict:
    return estate_mod.load_config(CONFIG)


def test_same_seed_produces_the_same_estate(cfg):
    a = estate_mod.build(cfg, 20260924)
    b = estate_mod.build(cfg, 20260924)
    assert [m.matter_ref for m in a.matters] == [m.matter_ref for m in b.matters]
    assert [p.person_ref for p in a.people] == [p.person_ref for p in b.people]
    assert [c.name for c in a.clients] == [c.name for c in b.clients]


def test_a_different_seed_produces_a_different_estate(cfg):
    a = estate_mod.build(cfg, 20260924)
    b = estate_mod.build(cfg, 1)
    assert [m.matter_ref for m in a.matters] != [m.matter_ref for m in b.matters]


def test_the_demo_fixtures_are_where_the_demo_script_says(cfg):
    est = estate_mod.build(cfg, 20260924)
    people = {p.person_ref: p for p in est.people}
    assert people["P-0101"].family_name == "de Vries"
    assert people["P-0102"].family_name == "Okonjo"
    matters = {m.matter_ref: m for m in est.matters}
    assert matters["M-2021-0043"].lead_person_ref == "P-0101"
    # Still open: no closing date, and later no outcome fact. The answer has to
    # say so rather than infer one.
    assert matters["M-2024-0286"].closed_on is None


def test_two_colleagues_share_a_family_name(cfg):
    est = estate_mod.build(cfg, 20260924)
    surnames = [p.family_name for p in est.people]
    assert any(surnames.count(name) > 1 for name in set(surnames)), (
        "matching people on a label has to be demonstrably wrong, not just argued"
    )


def test_the_crm_spells_some_organisations_differently(cfg):
    est = estate_mod.build(cfg, 20260924)
    pms_names = {c.name for c in est.clients}
    drifted = [a for a in est.accounts if a.name not in pms_names]
    assert drifted, "a firm's two systems never agree; the lab must not either"


def test_the_crm_has_not_heard_of_every_client(cfg):
    est = estate_mod.build(cfg, 20260924)
    assert len(est.accounts) < len(est.clients)


def test_five_matters_sit_behind_a_barrier(cfg):
    est = estate_mod.build(cfg, 20260924)
    assert len({r.matter_ref for r in est.restrictions}) == 5


def test_both_kinds_of_rule_are_in_the_system_of_record(cfg):
    est = estate_mod.build(cfg, 20260924)
    kinds = {r.rule_id: r.kind for r in est.restrictions}
    assert kinds["B-03"] == "barrier"
    assert "need-to-know" in kinds.values()
