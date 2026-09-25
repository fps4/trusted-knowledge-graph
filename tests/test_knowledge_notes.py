"""Knowledge notes: open matters citing closed ones — added without moving anything.

A precedent note filed on an open, unrestricted matter cites a restricted one by
its file number. The DMS lets it through, and so does any filter on a passage's
own matter; the graph must not. docs/decisions/0028.
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from tkg.ingest import documents as documents_mod
from tkg.ingest import estate as estate_mod

CONFIG = Path("/app/config/estate.yaml")
# sha256 of data/fixtures/documents.jsonl before knowledge notes existed: 742 documents.
BEFORE = "9867c3a75ce0b9675dd466c4f5ea1dd725c7ccf2942d248c80f3b1c89b78c2ff"


@pytest.fixture(scope="module")
def world():
    cfg = estate_mod.load_config(CONFIG)
    est = estate_mod.build(cfg, 20260924)
    docs = documents_mod.build(est, cfg, 20260924)
    return cfg, est, docs, [d for d in docs if d.doc_type == "knowledge-note"]


def _line(d) -> str:
    return json.dumps(asdict(d), ensure_ascii=False, sort_keys=True) + "\n"


def test_the_existing_documents_are_byte_identical(world):
    _, _, docs, notes = world
    before = [d for d in docs if d.doc_type != "knowledge-note"]
    assert len(before) == 742 and docs[:742] == before
    assert hashlib.sha256("".join(map(_line, before)).encode()).hexdigest() == BEFORE


def test_notes_come_after_every_other_document(world):
    _, _, docs, notes = world
    assert [d.doc_id for d in notes] == [f"DOC-{n:04d}" for n in range(743, 743 + len(notes))]


def test_notes_are_deterministic(world):
    cfg, est, _, notes = world
    again = documents_mod.knowledge_notes(est, cfg, 20260924)
    assert [(d.matter, d.date, d.text) for d in again] == \
        [(d.matter, d.date, d.text) for d in notes]


def test_three_notes_cite_each_restricted_matter_and_fifteen_are_controls(world):
    _, est, _, notes = world
    restricted = {r.matter_ref for r in est.restrictions}
    cited = [documents_mod.cited_matters(d) for d in notes]
    assert all(len(c) == 1 for c in cited)
    for ref in restricted:
        assert sum(1 for c in cited if c == [ref]) == 3
    assert sum(1 for c in cited if c[0] not in restricted) == 15


def test_a_note_is_filed_on_an_open_unrestricted_matter_of_the_same_type(world):
    _, est, _, notes = world
    matters = {m.matter_ref: m for m in est.matters}
    restricted = {r.matter_ref for r in est.restrictions}
    for d in notes:
        host, cited = matters[d.matter], matters[documents_mod.cited_matters(d)[0]]
        assert host.closed_on is None and d.matter not in restricted
        assert host.matter_type == cited.matter_type and host.matter_ref != cited.matter_ref
        assert d.confidentiality == "Private and confidential"


def test_the_demo_barrier_is_cited_from_a_matter_sanne_can_see(world):
    _, est, _, notes = world
    restricted = {r.matter_ref for r in est.restrictions}
    hosts = [d.matter for d in notes if documents_mod.cited_matters(d) == ["M-2022-0117"]]
    # Sanne is walled only by rules on restricted matters; an unrestricted host is hers.
    assert hosts and all(h not in restricted for h in hosts)


def test_the_manifest_states_exactly_what_the_note_says(world):
    cfg, est, _, notes = world
    matters = {m.matter_ref: m for m in est.matters}
    clients = {c.client_ref: c.name for c in est.clients}
    types = {t["id"]: t["label"].lower() for t in cfg["matter_types"]}
    for d in notes:
        ref = documents_mod.cited_matters(d)[0]
        cited = matters[ref]
        assert sorted((f["predicate"], f["subject"], f["object"]) for f in d.facts) == sorted([
            ("matterType", d.matter, f"gl:matter-type/{matters[d.matter].matter_type}"),
            ("citesMatter", d.matter, ref),
            ("matterType", ref, f"gl:matter-type/{cited.matter_type}"),
            ("forClient", ref, cited.client_ref),
            ("hadOutcome", ref, f"gl:outcome/{est.outcomes[ref]}"),
        ])
        # The file number, the client as practice management spells it, the type.
        assert ref in d.text and clients[cited.client_ref] in d.text
        assert f"this {types[cited.matter_type]}" in d.text
        said = documents_mod._outcome_sentence(
            est.outcomes[ref], documents_mod.REGULATOR.get(cited.jurisdiction, "the regulator"))
        assert said in d.text
