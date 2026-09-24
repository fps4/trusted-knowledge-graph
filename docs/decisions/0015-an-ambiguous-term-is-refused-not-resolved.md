# 15. An ambiguous term is refused, not resolved

Status: accepted · 2026-09-25 · M2

## Context

"Active client" has four defensible meanings in a firm: a client with an open
matter (the practice groups), a client billed in the last year (Finance), an
account with a relationship partner (Business Development), and anyone the firm
has ever acted for (Risk, because that is what a conflict check needs). They give
four different numbers. A language model asked "how many active clients do we
have?" picks one, silently and confidently, and the answer is wrong for three of
the four people who might have asked.

## Decision

- **The glossary is data with owners.** `config/glossary.yaml` compiles to SKOS in
  `g:glossary`. Every term and every reading has exactly one owner, and a shape
  fails the load when one does not.
- **A term with readings says what an unchosen reading gets** — `on_ambiguous`:
  `ask` (refused, readings listed back), `refuse`, or `default:<reading>`.
- **Resolution is step 2**, over SPARQL against the store, and the router refuses
  at step 3 before anything is retrieved.
- **`resolve_term()` returns every reading with its owner and its count** — each
  count decided for the person asking, through the same access path as any answer.
- **Terms carry slot values** (`means`): "AIFM" resolves to the fund-manager client
  type rather than to the model's guess. `ask(..., terms=[...])` records which
  definitions an answer rests on.

## Consequences

- The glossary is the thing that stops the AI guessing, and its owners are not
  engineers. That is the sentence for the room.
- The lab's readings are invented; their *shape* is not. Related entities — which
  the Risk reading should include — are not modelled, and the definition says so.
- Resolution is by exact label or alternative label. Fuzzy matching would
  reintroduce the guess this is here to remove.
