"""The eval's side of ADR 0028: who may see a citing document, what counts as a leak,
and the rule between the graph and the document store."""

from tkg.eval.battery import leaked_passages, score_graph
from tkg.eval.leak import doc_matters, graph_is_broader, walled_documents
from tkg.eval.truth import Truth
from tkg.ingest.documents import Document


def _doc(doc_id, matter, cites=()):
    return Document(doc_id, matter, "knowledge-note" if cites else "closing-letter",
                    "2025-01-01", "t", "p", "",
                    [{"predicate": "citesMatter", "subject": matter, "object": c} for c in cites])


DOCS = [_doc("DOC-1", "M-OPEN"), _doc("DOC-2", "M-OPEN", ["M-WALL"]), _doc("DOC-3", "M-WALL")]


def test_a_document_depends_on_its_own_matter_and_what_it_cites():
    assert doc_matters(DOCS) == {"DOC-1": {"M-OPEN"}, "DOC-2": {"M-OPEN", "M-WALL"},
                                 "DOC-3": {"M-WALL"}}


def test_a_note_citing_a_walled_matter_is_walled_though_filed_on_an_open_one():
    assert walled_documents(doc_matters(DOCS), {"M-WALL"}) == {"DOC-2", "DOC-3"}
    assert walled_documents(doc_matters(DOCS), set()) == set()


def test_a_leak_is_a_passage_that_depends_on_a_walled_matter():
    passages = [{"doc_id": "DOC-1", "matter_id": "M-OPEN"},
                {"doc_id": "DOC-2", "matter_id": "M-OPEN"}]
    assert leaked_passages(passages, {"M-WALL"}, doc_matters(DOCS)) == ["DOC-2"]
    # Without the manifest, only the passage's own matter is known — the old count.
    assert leaked_passages(passages, {"M-WALL"}) == []


def test_the_graph_may_be_stricter_than_the_store_only_where_a_document_cites():
    # Nothing cited: exact agreement, either way round.
    assert graph_is_broader(False, True, True) is None
    assert graph_is_broader(False, False, False) is None
    assert graph_is_broader(False, False, True) == "disagree"
    assert graph_is_broader(False, True, False) == "disagree"
    # Cites a walled matter: the store opening what the graph withholds is a finding.
    assert graph_is_broader(True, False, True) == "weaker"
    # The graph broader than the store is always a failure.
    assert graph_is_broader(True, True, False) == "disagree"


def test_a_document_list_leaves_out_a_note_citing_a_walled_matter():
    truth = Truth("documents", ["M-OPEN"], {"M-OPEN": ["DOC-1", "DOC-2"]}, "",
                  {"DOC-2": ["M-WALL"]})
    right = {"outcome": "answered-with-withheld", "rows": [{"docId": "DOC-1"}]}
    wrong = {"outcome": "answered", "rows": [{"docId": "DOC-1"}, {"docId": "DOC-2"}]}
    assert score_graph(truth, right, {"M-WALL"}, []).outcome == "correct"
    assert score_graph(truth, wrong, {"M-WALL"}, []).outcome == "confidently wrong"
    assert score_graph(truth, wrong, set(), []).outcome == "correct"
