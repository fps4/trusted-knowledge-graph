"""Passages, and the filter that goes inside the query."""

from tkg.index import chunk


def test_short_documents_are_one_passage_that_keeps_the_header():
    out = chunk("DOC-1", "M-1", "closing-letter", "Our ref: M-1\n\nDear Sirs,\n\nIt settled.")
    assert len(out) == 1 and out[0].text.startswith("Our ref: M-1")


def test_long_documents_split_on_paragraphs():
    text = "\n\n".join("x" * 400 for _ in range(4))
    assert len(chunk("DOC-1", "M-1", "memo", text)) == 4


# ── the filter: own matter, or every matter a passage depends on (ADR 0028) ────
import pytest  # noqa: E402

from tkg.index import filters  # noqa: E402


def test_a_passage_carries_its_own_matter_first_then_what_it_cites():
    out = chunk("DOC-1", "M-1", "knowledge-note", "Our ref: M-1\n\ncites M-2", ["M-2", "M-1"])
    assert out[0].matters == ["M-1", "M-2"]
    assert chunk("DOC-2", "M-1", "memo", "x")[0].matters == ["M-1"]


def test_no_filter_is_no_filter():
    assert filters(None) == [] and filters(["M-1"], mode="none") == []


def test_a_document_level_acl_looks_at_the_passages_own_matter_only():
    assert filters(["M-2", "M-1"], mode="doc-acl") == [{"terms": {"matter_id": ["M-1", "M-2"]}}]


def test_the_lineage_filter_needs_every_matter_a_passage_depends_on():
    clauses = filters(["M-1", "M-2"], scope=["M-1"])
    assert clauses == [
        {"terms": {"matter_id": ["M-1"]}},
        {"terms_set": {"matters": {"terms": ["M-1", "M-2"],
                                   "minimum_should_match_field": "matter_count"}}},
    ]
    # With no separate scope, a passage may be from any permitted matter.
    assert filters(["M-1"])[0] == {"terms": {"matter_id": ["M-1"]}}


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        filters(["M-1"], mode="post-filter")


class _Client:
    def __init__(self):
        self.body = None

    def search(self, index, body):
        self.body = body
        return {"hits": {"hits": []}}


def test_the_filter_goes_inside_both_the_bool_and_the_knn_clause():
    from tkg.index import Index

    index = Index.__new__(Index)
    index.client = _Client()
    index.search("q", [0.0], ["M-1", "M-2"], scope=["M-1"])
    query = index.client.body["query"]["bool"]
    expected = filters(["M-1", "M-2"], scope=["M-1"])
    assert query["filter"] == expected
    knn = next(c["knn"]["embedding"] for c in query["should"] if "knn" in c)
    assert knn["filter"] == {"bool": {"filter": expected}}
    index.search("q", [0.0], None)
    assert "filter" not in index.client.body["query"]["bool"]
