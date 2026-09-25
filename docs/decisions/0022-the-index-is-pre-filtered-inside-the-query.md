# 22. The index holds passages, and is filtered inside the query

Status: accepted · 2026-09-25

## Context

"The graph holds no document content" is true; the index cannot say the same —
retrieval over text needs the text. The precise claim is: the graph holds none,
the index holds permission-trimmed passages, the store holds the bytes.

## Decision

- OpenSearch, one document per passage: chunk id, document, matter, type, text,
  a 384-d embedding (`BAAI/bge-small-en-v1.5`, CPU). Passages come from the text
  extracted back out of the rendered PDFs, not from the source strings. The
  documents are short, so each is one passage.
- **Every resolver query carries the permitted matters as a filter inside the
  query** — in the `bool` filter for BM25 and inside the `knn` clause itself — so a
  restricted passage is never scored, ranked or cached. `passages()` takes the
  permit's matters as that filter.
- Embeddings are computed at load from a model **baked into the image**, and cached
  by content hash. The plan's fixture existed to keep the run offline; the baked
  model does that without committing vectors.
- The **vector-only path** (`make naive`) is kept as the comparison: top-5 over the
  whole index, no decision at all — how a retrieval layer built by a service
  account behaves. It is not part of the system and is not audited.

## Consequences

- On client-named questions about a restricted matter, asked as someone walled from
  it, the vector-only path returned walled passages on 8 of 8; the graph-grounded
  path leaked 0 of 160 answers. That comparison is the lab's headline.
- The security plugin is off. Correct for a loopback lab; a finding anywhere else.
