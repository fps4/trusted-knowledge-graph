# 23. Extraction by Claude, through the Batches API, into committed fixtures

Status: accepted · 2026-09-25

## Context

A fact extracted by a model is a claim: it needs a source, a confidence and a
review state, and it must be measurable. The demo must run offline.

## Decision

- One request per document through the **Message Batches API** (half price; this is
  fixture generation, not a request path), model `claude-opus-5-5` at low effort,
  configurable by `TKG_MODEL`.
- **Structured output** whose predicate field is an enum of exactly the predicates
  the ontology lets a fact carry: an unknown predicate cannot be expressed. The
  model sees one document's text — never the ground truth — and returns objects as
  strings, a confidence, and the shortest supporting quote.
- **Linking is deterministic and conservative**: exact full name, exact client name,
  vocabulary identifier. Anything else stays unlinked, with the reason, and the
  extraction report counts it. A guessed link turns recall loss into precision loss.
- Facts land in `g:doc/<docId>` with `fromDocument`, `extractedBy`, a character
  offset for the evidence — never the passage — and review state `extracted`.
- Results are committed to `data/fixtures/extraction.jsonl`; `make load` needs no
  key. A refused document is recorded as refused, not retried elsewhere: server-side
  refusal fallbacks are not available on the Batches API.

## Consequences

- `reports/extraction.md` scores against the manifest per relation, per document
  type, at three thresholds, and lists what could not be linked and why.
- The client named as the CRM spells it is the linking failure the lab expects:
  identity resolution is deliberately not done (ADR 0024), and it shows as recall.
