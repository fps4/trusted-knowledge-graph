# 14. A fact with a confidence is a reified node, not RDF-star

Status: accepted · 2026-09-25 · M1

## Context

M1 brings in the first facts that are not rows in a system of record: outcomes
told by a partner, with nobody's document behind them — the capture step. A fact
like that needs a source, a confidence and a review state, and the spine's plain
triples have nowhere to put them.

RDF-star is the elegant answer. Support for it varies by store and version, and
the lab's claim is that the ontology, shapes and queries carry to whichever store
the firm runs.

## Decision

A small `ssf:Fact` node: `factSubject`, `factPredicate`, `factObject`,
`confidence`, `reviewState`, `assertedBy`, `assertedOn`. One fact per named graph
`g:asserted/<person>/<date>`, and the graph's lineage in `g:prov`.

## Consequences

- Works on any SPARQL 1.1 store. Costs one join per fact, and queries read
  slightly worse than they would with RDF-star.
- The review state is data. An unconfirmed fact is returned and says it is
  unconfirmed; deciding what to do with it is the lawyer's call, not the system's.
- The same node carries extracted facts in M3, with a document instead of a person
  as their source.
