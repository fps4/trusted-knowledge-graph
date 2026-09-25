# 13. Denied identifiers are salted hashes — in every field

Status: accepted · 2026-09-25

## Context

A record that says *Sanne was denied facts derived from M-2022-0117* tells anyone
who reads it that M-2022-0117 exists and that Sanne is walled off from it — which
is what the barrier exists to prevent. The audit log of a barrier system is itself
confidential.

The obvious fix — hash the identifiers in the decisions — misses the fields nobody
thinks of. "Who led M-2022-0117?" puts the denied matter in a slot. The candidate
set lists it before any decision is made. A free-text question can name the client.

## Decision

- Denied matters and derived graphs are written as `h:` + HMAC-SHA256 under a salt
  in `secrets/audit.salt`, in **every** field: `slots`, `considered`, `decisions`.
  Permitted identifiers stay in the clear — the person was shown them.
- Rule ids, counts, owners and dates stay in the clear. They make the log useful
  for oversight without making it a directory of the firm's walls.
- **Free text is not logged.** A question in the lawyer's own words can name a
  client, and client names cannot be reliably redacted by string matching. The
  record holds the template and its slots, which is enough to re-run it.
- Each record carries a `salt_id`, so rotating the salt does not make older
  records unresolvable.
- The test is blunt: after the leak suite, no denied identifier appears in clear
  anywhere in the log.

## Consequences

- Only a holder of the salt can resolve a hash — the `risk` persona, whose
  own reads are written into the same chain.
- The salt never enters git. Without it the hashes are noise; with it the log is a
  sensitive record, and it is treated as one.
