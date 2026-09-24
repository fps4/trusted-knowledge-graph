# 5. A NULL produces no triple, and the load gate is what found out

Status: accepted · 2026-09-24 · M0

## Context

On the first run of the complete pipeline, SHACL rejected the load. Matters with
no closing date had arrived as `"None"^^xsd:date` — the Python `None` stringified
by the mapping engine and typed as a date.

A matter that is still open is not a matter that closed on a day called "None".
The distinction is the whole reason the graph knows when things were true, and an
open matter is precisely the case the demo's third scenario turns on.

## Decision

`na_values` on the mapping configuration is set explicitly, `None` included, so an
absent value produces **no triple at all**. The shapes keep `sh:datatype xsd:date`
on every date, so a regression fails the load rather than reaching the store.
`tests/test_shapes.py` pins the case.

## Consequences

- The load contract earned its place on day one, against a real defect, rather
  than in an argument about whether validation is worth the effort.
- It is worth telling this story rather than quietly fixing it: a gate that has
  never caught anything is indistinguishable from one that does not work.
- Nullable columns are now something to check when a mapping changes, not
  something to assume. `left_on`, `to_date`, `job_title` and
  `relationship_partner_ref` are all in the same position.
