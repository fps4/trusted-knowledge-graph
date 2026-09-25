# 9. Decide, then retrieve — never a post-filter

Status: accepted · 2026-09-25

## Context

The easy implementation of access control on a graph is to run the query and drop
the rows the caller may not see. It is also the implementation that leaks: the
query has already touched the restricted data, an aggregate has already counted
it, and whether a row is dropped depends on the result having a column that says
which matter it came from.

## Decision

Step 5 is four sub-steps, in this order:

1. **Candidates** — the template's candidate form: which matters, and which
   derived graphs, the question would reach. Identifiers only; no evidence.
2. **Lineage** — for each candidate derived graph, the matters it derives from.
3. **Decision** — one call to OPA with the principal, the candidates and the
   lineage map. Allow or deny per matter and per graph, with grounds.
4. **Bound query** — the template bound with `VALUES ?matter { …permitted… }` and
   every derived-graph variable filtered to the permitted set.

**The query that produces evidence cannot name a denied matter.** A test asserts
it for the demo's barrier.

## Consequences

- Two queries per question instead of one. At this scale that is milliseconds;
  at the programme's, the candidate query is the one to watch.
- Aggregates are computed by the store over the permitted set, never adjusted in
  Python afterwards.
- `considered` in the audit record is exactly the candidate set — what the
  traversal reached before anything was decided.
