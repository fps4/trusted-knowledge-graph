"""Passages, and the filter that goes inside the query."""

from tkg.index import chunk


def test_short_documents_are_one_passage_that_keeps_the_header():
    out = chunk("DOC-1", "M-1", "closing-letter", "Our ref: M-1\n\nDear Sirs,\n\nIt settled.")
    assert len(out) == 1 and out[0].text.startswith("Our ref: M-1")


def test_long_documents_split_on_paragraphs():
    text = "\n\n".join("x" * 400 for _ in range(4))
    assert len(chunk("DOC-1", "M-1", "memo", text)) == 4
