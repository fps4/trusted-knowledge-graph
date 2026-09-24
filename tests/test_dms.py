"""The second enforcement point is compiled from the same data as the first."""

import json
from pathlib import Path

from tkg import dms
from tkg.access.compile import denied_for

DATA = json.loads(Path("/app/build/opa/data.json").read_text()) if Path(
    "/app/build/opa/data.json").exists() else None


def test_a_walled_matter_is_a_denied_prefix():
    policy = dms.persona_policy({"M-2022-0117"})
    deny = [s for s in policy["Statement"] if s["Effect"] == "Deny"][0]
    assert deny["Resource"] == ["arn:aws:s3:::dms/doc/M-2022-0117/*"]


def test_no_walls_means_no_deny_statement():
    assert [s["Effect"] for s in dms.persona_policy(set())["Statement"]] == ["Allow"]


def test_seeing_nothing_is_a_deny_on_everything():
    policy = dms.persona_policy(None)
    assert policy["Statement"] == [{"Effect": "Deny", "Action": ["s3:GetObject"],
                                    "Resource": ["arn:aws:s3:::dms/*"]}]


def test_the_compiled_denials_match_the_demo():
    if DATA is None:
        return
    assert "M-2022-0117" in denied_for(DATA, "sanne.okonjo@lab.invalid")
    assert "M-2022-0117" not in denied_for(DATA, "mara.devries@lab.invalid")
    assert "M-2023-0018" in denied_for(DATA, "kim.bakker@lab.invalid")
    assert denied_for(DATA, "percy-svc@lab.invalid") is None
    assert denied_for(DATA, "risk@lab.invalid") is None
    assert denied_for(DATA, "nobody@lab.invalid") is None
