# 12. One hash-chained record per request, written once, by one writer

Status: accepted · 2026-09-25 · M1

## Context

`explain()` answers the person standing there. The questions that arrive later —
who has been shown anything derived from this matter, what did this person see
that week, why was this refused — are asked by someone who was not there, and
they are only answerable from a record that could not have been edited since.

## Decision

- The resolver builds one trace per request through every step, and writes it
  **once**, at completion, answered or refused, as one line of JSON in
  `./audit/decisions.jsonl`.
- Each record carries `prev_hash` and `hash = sha256(canonical JSON of the record
  without its hash)`. `tkg verify-audit` recomputes the chain and names the first
  record that fails.
- **One writer.** The CLI jobs call the resolver over HTTP as a persona rather
  than running the engine themselves, and the writer takes an exclusive file lock
  and re-reads the last hash under it, so a second process cannot fork the chain.
- `explain(trace)` reads the stored record. The live explanation and the later one
  are the same object.

## Consequences

- An edited, deleted or reordered record breaks every hash after it.
- **Removing the tail is not detectable from the file alone** — a chain proves
  nothing about records that were never followed. `verify-audit` prints the head
  hash so it can be held elsewhere; in the programme, immutable retention does
  that job. Said here rather than implied away.
- The chain is tamper-evident, not tamper-proof. It is the difference between
  "we write a log" and "we can show the log has not been edited".
