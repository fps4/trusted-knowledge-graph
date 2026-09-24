# 21. The document store enforces its own access — two points, one policy file

Status: accepted · 2026-09-25 · M3

## Context

"Does the graph become a way around the DMS?" is the question a security review
will ask. A graph that decides access and then fetches bytes with an admin key has
one enforcement point, and every bug in it is a breach.

## Decision

- PDFs live in MinIO, standing in for the DMS, **keyed `doc/<matter>/<docId>.pdf`**,
  so a rule about a matter is a rule about a prefix. Tagged with matter, type and
  confidentiality as well.
- `make policy` compiles, from the same data OPA evaluates, **one MinIO user and
  policy per persona**: allow `doc/*`, deny the prefixes of every matter that
  persona is walled from; deny everything to the service identity and to Risk.
- Citations carry a **presigned URL minted with the asking persona's own
  credentials**, valid for five minutes — never an admin key. There is no tool that
  turns an identifier into bytes.
- The barrier suite checks that **OPA and the store agree on every persona and
  every document**, and that a restricted document fetched with the credentials of
  someone walled from it — the stolen-identifier case — yields nothing.

## Consequences

- The graph refuses the fact; the store refuses the bytes, on its own policy, with
  no knowledge of the graph. Even a link Sanne signs herself for a restricted
  document returns 403.
- **A presigned URL is a bearer token for its lifetime.** Anyone Mara forwards her
  link to can open it for five minutes. That is the property of presigned URLs; in
  the programme the DMS link would carry the user's own session. Said here.
- The store's root credentials are in `.env`; the persona policies demonstrate the
  pattern, not a hardened boundary.
- MinIO stopped publishing release-tagged community images; the lab pins the last
  one by digest (RELEASE.2025-09-07). The design needs *a* store with its own
  policy engine, not this one.
