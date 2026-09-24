"""Every relation a template asserts over has an owner in config/relations.yaml."""

import re

import yaml

from tkg.semantic.templates import TEMPLATES

RELATIONS = yaml.safe_load(open("/app/config/relations.yaml"))["relations"]
STRUCTURAL = {"matterRef", "factSubject", "factPredicate", "factObject", "reviewState",
              "confidence", "assertedBy", "accountType", "accountSince", "assignmentMatter",
              "assignmentRole", "validFrom", "validTo"}


def test_every_listed_template_uses_its_relation():
    for r in RELATIONS:
        for tid in r["templates"]:
            assert f"ssf:{r['predicate']}" in TEMPLATES[tid].where, (r["predicate"], tid)


def test_every_relation_a_template_uses_is_owned():
    owned = {r["predicate"] for r in RELATIONS}
    for t in TEMPLATES.values():
        used = set(re.findall(r"ssf:(\w+)", t.where)) - STRUCTURAL
        used = {u for u in used if u[0].islower()}
        assert used <= owned, (t.id, used - owned)


def test_every_relation_has_an_owner_and_a_time_semantics():
    for r in RELATIONS:
        assert r["owner"] and r["time"] in {"current-state", "point-in-time", "valid-time"}
