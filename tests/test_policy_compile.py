"""The compiler refuses to write a policy the system of record does not back."""

import pytest

from tkg.access.compile import PolicyError, Records, compile_policy

PEOPLE = {"personas": [
    {"id": "sanne", "principal": "sanne@lab.invalid", "kind": "person", "person_ref": "P-2"},
    {"id": "percy", "principal": "percy@lab.invalid", "kind": "service"},
]}


def barriers(**over):
    rule = {
        "id": "B-03", "matter": "M-1", "kind": "barrier",
        "insiders": {"matter_team": True},
        "screened": {"people": ["P-2"], "practice_areas": ["fi"]},
        "set_on": "2022-03-14", "set_by": "Risk", "owner": "Head of Risk", "review": "12 months",
    }
    rule.update(over)
    return {"version": "2026-09-25", "disclosure": "withheld-count", "baseline": [],
            "rules": [rule]}


def records(restrictions=None, team=None):
    return Records(
        restrictions=restrictions if restrictions is not None
        else [{"matter_ref": "M-1", "rule_id": "B-03", "kind": "barrier"}],
        teams={"M-1": set(team or {"P-1", "P-3"})},
        people={
            "P-1": {"grade": "partner", "office": "AMS", "practice_area": "am"},
            "P-2": {"grade": "associate", "office": "LON", "practice_area": "fi"},
            "P-3": {"grade": "associate", "office": "AMS", "practice_area": "fi"},
        },
    )


def test_a_consistent_policy_compiles_and_resolves_the_team():
    data = compile_policy(barriers(), PEOPLE, records())["barriers"]
    rule = data["restrictions"]["M-1"][0]
    assert rule["insiders"] == ["P-1", "P-3"]
    assert data["principals"]["sanne@lab.invalid"]["practice_area"] == "fi"
    assert data["policy_version"].startswith("2026-09-25+")


def test_the_version_changes_when_the_team_does():
    a = compile_policy(barriers(), PEOPLE, records())["barriers"]["policy_version"]
    b = compile_policy(barriers(), PEOPLE, records(team={"P-1"}))["barriers"]["policy_version"]
    assert a != b


def test_a_rule_the_system_of_record_has_never_heard_of_is_refused():
    with pytest.raises(PolicyError, match="never heard of"):
        compile_policy(barriers(), PEOPLE, records(restrictions=[]))


def test_a_restriction_with_no_rule_is_refused():
    extra = [{"matter_ref": "M-1", "rule_id": "B-03", "kind": "barrier"},
             {"matter_ref": "M-2", "rule_id": "B-99", "kind": "barrier"}]
    with pytest.raises(PolicyError, match="nothing would enforce it"):
        compile_policy(barriers(), PEOPLE, records(restrictions=extra))


def test_a_kind_mismatch_is_refused():
    with pytest.raises(PolicyError, match="need-to-know"):
        compile_policy(barriers(kind="need-to-know"), PEOPLE, records())


def test_a_matter_mismatch_is_refused():
    with pytest.raises(PolicyError, match="M-9"):
        compile_policy(barriers(matter="M-9"), PEOPLE, records())


def test_a_named_person_both_inside_and_screened_is_a_contradiction():
    with pytest.raises(PolicyError, match="both inside and screened"):
        compile_policy(barriers(), PEOPLE, records(team={"P-1", "P-2"}))


def test_the_disclosure_mode_must_be_one_of_the_two():
    bad = barriers()
    bad["disclosure"] = "whatever"
    with pytest.raises(PolicyError, match="disclosure"):
        compile_policy(bad, PEOPLE, records())


def test_the_real_rules_file_parses_and_names_its_owner():
    import yaml

    cfg = yaml.safe_load(open("/app/config/barriers.yaml"))
    assert cfg["disclosure"] in {"withheld-count", "silent"}
    assert all(r["owner"] and r["set_on"] for r in cfg["rules"])
    assert {b["id"] for b in cfg["baseline"]} >= {"ID-01", "ID-02", "ID-03", "LN-01"}
