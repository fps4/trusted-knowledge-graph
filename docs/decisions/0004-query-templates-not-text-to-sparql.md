# 4. Queries come from templates bound to competency questions

Status: accepted · 2026-09-24 · M0

## Context

The tempting design is to let a language model write SPARQL from the question.
It demos well and it is what most graph-plus-LLM projects do.

It also means every answer is produced by a query nobody reviewed, over a schema
the model inferred, with no way to say which definition of a term was used.

## Decision

The resolver holds a small library of templates, each bound to a competency
question the practice groups agreed the graph must answer. A question is served
by picking a template and filling its slots. Slot values are validated — an
identifier must be an identifier in this estate, a date must be a date — and a
value that is neither is refused rather than interpolated.

This is the same position as a governed metric registry: **every answer comes
from a registered definition, never from ad-hoc query generation.**

## Consequences

- The set of answerable questions is finite and visible: `tkg cq` lists it.
- Query injection through a slot is not mitigated, it is impossible — a test
  asserts that a value carrying `} DROP ALL #` is refused.
- Free-form text-to-SPARQL is not abandoned; it comes back later as the *measured
  comparison*, behind a flag, so the cost of the disciplined path is a number
  rather than an assertion.
- Competency questions stop being scoping paperwork and become the query surface,
  which is what makes them worth writing with practice groups.
