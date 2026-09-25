# 28. A document inherits the matters it cites

Status: accepted · 2026-09-25

## Context

The first comparison filtered nothing: the vector path searched the whole index.
The plan had said "document-level filtering only — the assumption that the DMS
already filters", and with that filter its leaks drop to zero, because no
document in the corpus mentioned another matter. The comparison was against a
weaker baseline than the one a firm would actually run.

The realistic leak is a **knowledge note**: a precedent note filed on an open,
unrestricted matter, citing a walled matter by its file number, with that
matter's client and outcome. The note is open in the DMS — it sits on an open
matter — so document-level trimming lets it through. So did our own index filter,
which checked the passage's own matter.

## Decision

- **Thirty knowledge notes** are generated from the estate: three citing each
  restricted matter, fifteen citing unrestricted ones as a control, each filed on
  an open, unrestricted matter of the same type. Own random stream, numbered after
  every other document: the 742 existing documents are byte-identical. The
  manifest records exactly what a note says — `citesMatter` (subject: the note's
  matter) and the cited matter's type, client and outcome (subject: the cited
  matter).
- **Extraction** gains `citesMatter` and an optional `subject`: a fact may be
  about a matter the document cites, never about one it does not. Linking accepts
  an exact matter reference only.
- **Lineage.** `g:doc/<noteId>` is `prov:wasDerivedFrom` every matter the note
  cites, as well as its own matter and document. The note's facts — and the note —
  are walled wherever any cited matter is (ADR 0008 applied, not changed; the
  policy is unchanged).
- **The index** stores every matter a passage depends on — its own, then what its
  document cites, from the linked extraction — and a count. The resolver's filter
  requires *all* of them to be permitted: `terms_set` on `matters` against
  `matter_count`, in the bool filter and inside the kNN filter. The passage must
  still be *from* a matter the question reached.
- **The permit** carries, besides the question's matters, the matters its permitted
  derived graphs cite (`cited`). They are permitted by construction — a graph is
  allowed only if every matter in its lineage is — so they widen what a passage may
  *depend on*, never which matters it may be *from*.
- **CQ-10** withholds a document whose extracted graph was not permitted, with a
  `guard` graph variable: `FILTER NOT EXISTS { GRAPH ?xg { … ?doc } FILTER (?xg NOT
  IN permitted) }`. The note's row is not listed, no link is minted for it, and it
  is counted as withheld by lineage. The guarded graphs are the candidates `?fg`
  already reached, so they were decided before the query ran.
- **The document store is not changed.** The DMS genuinely does not know what a
  document cites, and adding per-object denies would make the lab's DMS better than
  the one it stands for. The agreement check becomes: exact where a document cites
  nothing; where it cites a matter, the graph may be *stricter* than the store,
  never *broader*. The gate fails only on broader.
- **Three comparisons**, the same questions: no filter; a document-level ACL (the
  passage's own matter against what the person may see, computed independently of
  OPA); and the lineage filter. The battery's vector path runs behind the
  document-level ACL — the fairer baseline — and still reports the unfiltered leak
  count.

## Consequences

- The DMS is weaker than the graph on every note citing a walled matter, and the
  leak report says so as a finding. Classification write-back to the DMS is the
  programme's fix; the lab does not pretend to have it.
- Lineage is only as good as extraction: a citation the model misses leaves the
  note's graph derived from its own matter only. The barrier suite and the battery
  read what a note cites from the manifest, not the extraction, so a missed
  citation shows as a leak rather than a pass.
- A permit from a question that never reached a note's graph (CQ-01, say) cannot
  open that note's passage even where the person may see the cited matter. That is
  an over-refusal on the safe side, and it is stated rather than fixed.
- Notes on the demo's matters change two answers: CQ-10 on M-2024-0286 now holds a
  note citing M-2022-0117, which Sanne must not be shown.
