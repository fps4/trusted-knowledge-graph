# 17. The router decides graph, index, hybrid or refuse — and says why

Status: accepted · 2026-09-25 · M2

## Context

The architecture puts a route between term resolution and binding. Until M3 there
is no index, so the honest router has one working destination — which is exactly
when a router is tempting to fake.

## Decision

Step 3 takes two inputs, both known before any evidence is touched: what the
question needs (`facts`, `passages` or `both`, declared on the template) and
whether every term resolved. It returns a route and a reason, and both go into the
trace and the answer:

| needs | term ambiguous | index | route |
|---|---|---|---|
| any | yes | any | refuse — with the readings |
| facts | no | any | graph |
| passages | no | not yet | refuse — "the index arrives in M3" |
| passages / both | no | yes | index / hybrid |

## Consequences

- Every answer carries its route and reason; `refused-ambiguous` and
  `refused-no-index` are outcomes the eval can score.
- In M2 every template needs facts, so every answered question routes to the
  graph. The index and hybrid routes are tested, not exercised. Said here, not
  implied by a diagram.
