# 18. Reading the decision record is an access decision

Status: accepted · 2026-09-25 · M2

## Context

The record answers the questions that arrive months later: who has been shown
anything derived from this matter, what did this person see that week, why was
this refused. An audit trail that anyone can read is a directory of the firm's
walls; one that its readers are exempt from has a hole exactly where someone
would look.

## Decision

- **OPA decides who may read the record**, from a rule in `barriers.yaml` (AU-01)
  like every other access rule. Only the `risk` role may. Every other persona —
  including the one asking about their own screening — is refused, and the
  attempt is recorded.
- **Risk resolves hashes.** The resolver holds the salt and can hash every
  identifier in the estate to compare; Risk sees in the clear who was walled off
  from what. Risk still sees no matter content: its own ask() is refused (ID-03).
- **Risk's reads are written into the same chain, by the same writer**, and what
  Risk asked about is hashed in that record. The barrier suite checks it.
- **Aggregates record what they counted** (`returned.counted`), so "who has been
  shown anything derived from this matter" includes a count it contributed to.
- The three questions are `audit_subject`, `audit_person`, `audit_trace` on the
  resolver, the MCP surface and `tkg audit`.

## Consequences

- `reports/audit.md` shows in the clear what the record hashes. It is committed
  only because the estate is synthetic, and it says so at the top.
- The person-centred question uses the record's timestamps; the chain protects
  their order, not their accuracy against a clock.
