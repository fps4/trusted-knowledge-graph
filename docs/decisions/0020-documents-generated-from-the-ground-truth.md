# 20. The firm's documents are generated from the ground truth — the manifest is the gold set

Status: accepted · 2026-09-25 · M3

## Context

Extraction quality cannot be measured without knowing what each document says,
and on a real corpus that knowledge costs lawyer hours. Measuring on nothing is
worse than measuring on something synthetic, provided the synthetic part is said.

## Decision

- 742 documents — an engagement letter per matter, advice memos for about a third,
  closing letters for most closed matters — written by templates from the estate.
  `data/fixtures/documents.jsonl` holds each document's text **and the facts it was
  generated to carry**. That manifest is the gold set.
- **Outcomes live only in documents.** The estate draws an outcome for every closed
  matter and writes it nowhere structured; a closed matter with no closing letter
  has an outcome the lab can never learn.
- The mess is carried through: some documents name the client as the CRM spells it.
  Titles name the client, as a real letter's "Re:" line does.
- The demo's matters always receive a memo and a closing letter; the random draw
  still happens, so nothing else moves.
- Templates, not a language model, write the text: deterministic, reviewable, free.
  `make load` refuses a fixture that is not what the estate generates today.

## Consequences

- The prose is more regular than a firm's. Extraction scores are an upper bound, and
  the report says so above the table. The method is what transfers.
- Regenerating the documents invalidates the extraction fixture; the load check
  makes that loud rather than silent.
