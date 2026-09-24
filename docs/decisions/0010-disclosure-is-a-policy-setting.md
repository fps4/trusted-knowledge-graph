# 10. Disclosure is a policy setting, and a refusal is itself a disclosure

Status: accepted · 2026-09-25 · M1

## Context

When a screened lawyer asks a question whose answer depends on a matter they
cannot see, the system can say so — "two facts were withheld under B-03" — or say
nothing. Saying so is useful to the lawyer and tells them the firm acts on the
other side of something. Saying nothing is discreet and lets them believe an
incomplete answer is complete.

Neither is obviously right, and it is not the lab's decision to make.

## Decision

`disclosure:` in `barriers.yaml` — owned by whoever owns the rules — with two
modes, both implemented:

| Shape | `withheld-count` | `silent` |
|---|---|---|
| Direct — about a matter you cannot see | refused, with the grounds | no facts, as if it did not exist |
| Second hop — some rows depend on it | permitted rows, plus "N withheld under B-03" | permitted rows only |
| Aggregate — a count over a set containing it | **refused** | computed over the permitted set and **labelled** as such |

The demo runs `withheld-count`, because the scene needs the grounds on screen.
The caller cannot choose the mode; a setting the caller can flip is not a policy.

## Consequences

- **A refusal is a one-bit disclosure.** Refusing the aggregate tells the screened
  lawyer that a restricted matter of that type exists. That is exactly the trade
  this setting is about, and it is stated rather than discovered.
- A `silent` aggregate is never silently partial: it says what it was computed
  over.
- The question goes to the firm, not into the code.
