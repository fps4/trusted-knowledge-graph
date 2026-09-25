# 1. The systems of record are a database, not flat exports

Status: accepted · 2026-09-24

## Context

The obvious way to stand up a spine is three CSV files and a loader that reads
them. It is quicker, it has no container, and it produces the same triples.

But the design claims something specific: *matters, clients and people come from
the systems of record, mapped rather than extracted, with a declarative mapping
that is versioned*. R2RML over a file is a weaker cousin of that claim, and the
interesting question downstream — whether the spine can be a **view** over the
source systems rather than a copy of them — cannot even be asked without a
database to point at.

## Decision

Three Postgres schemas — `pms`, `crm`, `hr` — seeded by the generator and read by
the lab through a role that holds `SELECT` and nothing else. The spine is built by
R2RML mappings in `mappings/*.r2rml.ttl`, executed by morph-kgc against the live
database.

## Consequences

- One more container, and a seeding step before mapping.
- The read-only role is not decoration: a firm's DBA says yes to a reader and not
  to a role that could write back, and the lab should be shaped like the thing it
  is arguing for.
- It makes the virtual-spine question testable later: SPARQL rewritten to SQL over
  these same schemas, compared against the materialised load. That comparison is
  the finding that would change the commercial shape of a real programme, and it
  needs a real database underneath it.
- The mapping is a reviewable diff rather than a pull request against loader code.
