# 26. `make gate` is the deploy gate, and review is a decision on the record

Status: accepted · 2026-09-25

## Gate

There is no CI (ADR 0003's loopback stack is not built to be reached, and an unused
workflow file is a claim the repo cannot back). The gate is a command that must pass
before the repository is pushed or the link is sent:

1. the committed policy is what `barriers.yaml` and the systems of record compile to;
2. the barrier suite: zero leaks, zero wrong refusals, every door holds;
3. OPA and the document store agree on every persona and every document;
4. stolen document identifiers yield nothing;
5. no denied identifier in clear anywhere in the decision record;
6. the eval: the graph path leaks nothing, and scores at or above `reports/baseline.json`;
7. the decision record's hash chain is intact.

Not checked, and said: OPA's own decision log as an independent second stream (cut,
ADR 0024). The baseline is recorded deliberately (`make baseline`), never
automatically — lowering the bar is a decision someone takes.

## Review

A fact that was told or extracted is a claim until a person confirms it. `tkg review
list|confirm|reject` goes through the resolver as the reviewer: the access decision
applies (you cannot review what you cannot see — and "walled" and "no such fact"
get the same answer), the request is on the chain, and the review becomes its own
graph `g:review/<factId>`, derived from the fact's graph, so it inherits every wall
the fact has. Answers show the reviewed state and stop asserting a rejected fact;
the fact stays in the graph for the record. Decisions persist in
`data/reviews/decisions.jsonl` and `make load` replays them.

The HTML workbench the plan wanted was cut to this CLI (ADR 0024). The resolver now
writes to the knowledge layer in exactly one place — review graphs — and nowhere else.
