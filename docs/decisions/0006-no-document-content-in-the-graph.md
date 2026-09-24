# 6. "The graph holds no document content" is a shape, not a sentence

Status: accepted · 2026-09-24 · M0

## Context

The architecture states as a principle that the graph holds assertions and
identifiers, and that document content stays where it belongs. Stated that way it
is unfalsifiable: a reviewer cannot tell a design principle from a thing that
merely happens to be true today.

The failure it guards against is real and gradual. Nobody decides to build a
second copy of the document system. Someone adds a summary field because it makes
a query easier, and eighteen months later the graph is a search index with worse
security.

## Decision

A SHACL shape with a SPARQL constraint: no literal on any of the firm's classes
may exceed 500 characters. It runs in the load gate, before anything reaches the
store, and `tests/test_shapes.py` asserts that a 501-character literal fails.

## Consequences

- The rule can be shown failing, which is the only way to show it holds.
- 500 is arbitrary and chosen to be obviously wrong to breach: names, references
  and labels are far below it, prose is far above. It is a tripwire, not a budget.
- It constrains later milestones deliberately. When extraction arrives, a fact
  will carry a pointer to its source document and an offset — not the passage. The
  passage belongs to the index, and the bytes belong to the document store.
