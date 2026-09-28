# 29. A person is found by name through a template, not through the glossary

Status: accepted · 2026-09-28

## Context

Every question about a person takes an identifier — CQ-04 and CQ-08 want `P-0101`.
People ask about "Mara", not P-0101. Nothing turned a name into an identifier: the
assistant tried `resolve_term("Mara")`, the glossary rightly did not know her, and it
stopped and asked the user for her person id. That is the correct behaviour with the
tools it had, but it was a question the lab could answer and did not.

Two shortcuts were rejected. Putting people into the glossary makes a term mean two
things: a word whose meaning an owner decides, and a directory. Listing names in the
assistant's instructions answers outside the access path and goes stale.

## Decision

- **CQ-12 finds people by name**: a case-insensitive match on the HR label, returning
  identifier, office, grade, practice area, and joining and leaving dates, from
  `g:spine/hr`. It reaches no matter, so no barrier applies — as for CQ-04.
- **A name is a `text` slot.** Letters, spaces, `-`, `'` and `.`, up to 60
  characters; anything else is refused without being echoed. Nothing that can close
  a SPARQL string gets in.
- **The name is not logged in clear.** A name typed into a slot could be a client's,
  which ADR 0013 keeps out of the record. The record holds a salted hash of it and
  the identifiers of the people it found.
- **Several matches are listed, not chosen from.** The assistant is told to find a
  named person with CQ-12 first, and to ask which one is meant when more than one
  matches.

## Consequences

- A lookup by name is one extra step before the question about the person, and it
  is recorded like any other question.
- The hashed name can be compared between records, not read. Re-running a lookup from
  the record needs the people it found, which the record keeps, not the name.
