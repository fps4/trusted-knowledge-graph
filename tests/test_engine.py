"""The seven steps against fake stores: the decision is made before retrieval, the
bound query never names a denied matter, and the record never holds one in clear."""

import json
import re

import pytest

from tkg import iri
from tkg.access.decide import Decision, PolicyUnavailable
from tkg.audit.chain import Hasher, Writer, read, verify
from tkg.resolver.engine import Resolver

OPEN, SHUT = "M-2021-0043", "M-2022-0117"
TOLD_OPEN = iri.asserted_graph("P-0101", "2022-03-04")
TOLD_SHUT = iri.asserted_graph("P-0101", "2023-07-05")
B03 = {"rule": "B-03", "kind": "barrier", "owner": "Head of Risk", "set_on": "2022-03-14",
       "set_by": "Risk", "source": "config/barriers.yaml", "review": "every 12 months"}


def _uri(v):
    return {"type": "uri", "value": v}


def _lit(v):
    return {"type": "literal", "value": v}


class FakeFuseki:
    def __init__(self):
        self.queries = []

    def query(self, sparql):
        self.queries.append(sparql)
        if "SELECT DISTINCT" in sparql:
            rows = []
            only = re.search(r"FILTER \(\?matter = <[^>]*/(M-\d{4}-\d{4})>\)", sparql)
            for m, g in ((OPEN, TOLD_OPEN), (SHUT, TOLD_SHUT)):
                if only and only.group(1) != m:
                    continue
                row = {}
                if "?matter" in sparql.split("WHERE")[0]:
                    row["matter"] = _uri(iri.matter(m))
                if "?fg" in sparql.split("WHERE")[0]:
                    row["fg"] = _uri(g)
                rows.append(row)
            return {"results": {"bindings": rows}}
        if "wasDerivedFrom+" in sparql:
            return {"results": {"bindings": [
                {"g": _uri(g), "src": _uri(iri.matter(m))}
                for g, m in ((TOLD_OPEN, OPEN), (TOLD_SHUT, SHUT)) if f"<{g}>" in sparql
            ]}}
        permitted = re.findall(r"id/matter/(M-\d{4}-\d{4})>", sparql.split("VALUES")[-1][:400])
        if "VALUES" not in sparql:  # CQ-08: no matter; rows from permitted graphs
            graphs = [g for g in (TOLD_OPEN, TOLD_SHUT) if f"<{g}>" in sparql]
            return {"results": {"bindings": [
                {"topicLabel": _lit("x"), "fg": _uri(g)} for g in graphs]}}
        return {"results": {"bindings": [
            {"matterRef": _lit(m), "n": _lit("1"), "leadLabel": _lit("Mara de Vries"),
             "g": _uri(iri.G_SPINE_PMS)} for m in permitted]}}


class FakeOpa:
    def __init__(self, disclosure="withheld-count", principal=None, down=False):
        self.disclosure, self.principal, self.down = disclosure, principal or [], down

    def decide(self, principal, matters, lineage_map):
        if self.down:
            raise PolicyUnavailable("connection refused")
        denied = {SHUT}
        return Decision(
            policy_version="test+1",
            disclosure=self.disclosure,
            principal=self.principal,
            matters={m: {"allow": m not in denied, "grounds": [] if m not in denied else [B03]}
                     for m in matters},
            graphs={g: {"allow": not (set(ms) & denied),
                        "grounds": [{**B03, "via": SHUT}] if set(ms) & denied else []}
                    for g, ms in lineage_map.items()},
        )


PERSONAS = {"sanne": {"principal": "sanne@lab.invalid"}, "mara": {"principal": "mara@lab.invalid"}}


@pytest.fixture
def make(tmp_path):
    def _make(**opa):
        fuseki = FakeFuseki()
        resolver = Resolver(fuseki, FakeOpa(**opa), Writer(tmp_path / "d.jsonl"),
                            Hasher(b"s" * 32), b"k" * 64, PERSONAS)
        return resolver, fuseki, tmp_path / "d.jsonl"
    return _make


def test_rows_come_back_with_what_was_withheld_and_why(make):
    resolver, fuseki, _ = make()
    r = resolver.ask("sanne", "CQ-02", {})
    assert r["outcome"] == "answered-with-withheld"
    assert [row["matterRef"] for row in r["rows"]] == [OPEN]
    assert r["explain"]["blocked"] == {"direct": 1, "by_lineage": 1}
    assert r["explain"]["rules"][0]["rule"] == "B-03"
    assert "via" not in json.dumps(r["explain"]), "grounds must not say which matter"
    evidence = [q for q in fuseki.queries if "VALUES ?matter" in q]
    assert evidence and all(SHUT not in q for q in evidence)


def test_the_record_holds_the_denied_matter_only_as_a_hash(make):
    resolver, _, log = make()
    resolver.ask("sanne", "CQ-06", {"matter": SHUT})
    text = log.read_text()
    assert SHUT not in text and TOLD_SHUT not in text
    record = read(log)[-1]
    assert record["slots"]["matter"].startswith("h:")
    assert record["outcome"] == "refused"
    assert verify(log).ok


def test_an_aggregate_over_a_restricted_set_is_refused_before_it_is_run(make):
    resolver, fuseki, _ = make()
    r = resolver.ask("sanne", "CQ-07", {})
    assert r["outcome"] == "refused-aggregate"
    assert not any("GROUP BY" in q for q in fuseki.queries)


def test_silent_aggregates_are_computed_over_what_you_can_see_and_say_so(make):
    resolver, _, _ = make(disclosure="silent")
    r = resolver.ask("sanne", "CQ-07", {})
    assert r["outcome"] == "answered"
    assert r["scope"] == "Computed over the matters you can see."
    assert "explain" not in r


def test_silent_mode_says_nothing_about_what_was_withheld(make):
    resolver, _, _ = make(disclosure="silent")
    r = resolver.ask("sanne", "CQ-02", {})
    assert r["outcome"] == "answered" and "explain" not in r


def test_lineage_decides_facts_that_name_no_matter(make):
    resolver, _, _ = make()
    r = resolver.ask("sanne", "CQ-08", {"person": "P-0101"})
    assert [row["fg"] for row in r["rows"]] == [iri.shorten(TOLD_OPEN)]
    assert r["explain"]["blocked"] == {"direct": 0, "by_lineage": 1}


def test_who_is_asking_decides_before_any_matter_does(make):
    resolver, fuseki, _ = make(principal=[{"rule": "ID-02", "kind": "identity"}])
    r = resolver.ask("sanne", "CQ-02", {})
    assert r["outcome"] == "refused" and r["explain"]["rules"][0]["rule"] == "ID-02"
    assert not any("VALUES ?matter" in q for q in fuseki.queries)


def test_no_policy_engine_means_no_answer_and_a_record_that_says_so(make):
    resolver, _, log = make(down=True)
    r = resolver.ask("sanne", "CQ-02", {})
    assert r["outcome"] == "refused-policy-unavailable" and "rows" not in r
    assert read(log)[-1]["outcome"] == "refused-policy-unavailable"


def test_explain_answers_from_the_stored_record_and_only_to_the_asker(make):
    resolver, _, _ = make()
    live = resolver.ask("sanne", "CQ-06", {"matter": SHUT})
    later = resolver.explain("sanne", live["trace"])
    assert later["outcome"] == "shown"
    assert later["rules"] == live["explain"]["rules"]
    assert later["blocked"] == live["explain"]["blocked"]
    assert resolver.explain("mara", live["trace"])["outcome"] == "refused"
    assert resolver.explain("sanne", "t-nope")["outcome"] == "refused"


def test_passages_needs_a_permit_and_only_your_own(make):
    resolver, _, log = make()
    mine = resolver.ask("sanne", "CQ-01", {"client": "C-0042"})["permit"]
    theirs = resolver.ask("mara", "CQ-01", {"client": "C-0042"})["permit"]
    assert resolver.passages("sanne", mine, "")["outcome"] == "no-index"
    assert resolver.passages("sanne", theirs, "")["outcome"] == "refused-permit"
    assert resolver.passages("sanne", "junk", "")["outcome"] == "refused-permit"
    assert verify(log).records == 5


def test_a_rejected_slot_value_is_not_recorded(make):
    resolver, _, log = make()
    r = resolver.ask("sanne", "CQ-02", {"since": "the day Rhine Capital called"})
    assert r["outcome"] == "refused-invalid"
    assert "Rhine" not in log.read_text()
