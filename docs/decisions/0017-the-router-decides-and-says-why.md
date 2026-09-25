# 17. The router decides graph, index, hybrid or refuse — and says why

Status: accepted · 2026-09-25

## Context

The architecture puts a route between term resolution and binding. Most questions
need facts, some need passages, and a few need both; a router that always says
"graph" would be easy to fake and would hide the choice.

## Decision

Step 3 takes two inputs, both known before any evidence is touched: what the
question needs (`facts`, `passages` or `both`, declared on the template) and
whether every term resolved. It returns a route and a reason, and both go into the
trace and the answer:

| needs | term ambiguous | index | route |
|---|---|---|---|
| any | yes | any | refuse — with the readings |
| facts | no | any | graph |
| passages / both | no | not reachable | refuse — "needs passages, and the index is not available" |
| passages / both | no | yes | index / hybrid |

## Consequences

- Every answer carries its route and reason; `refused-ambiguous` and
  `refused-no-index` are outcomes the eval can score.
- CQ-10 needs facts and passages and routes hybrid; every other template needs facts
  and routes to the graph. The index-only route is tested, not exercised by any
  template. Said here, not implied by a diagram.
