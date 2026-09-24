# 16. SALI LMSS: reuse by mapping, not adoption — and verify the namespace

Status: accepted · 2026-09-25 · M2

## Context

SALI LMSS is the public standard for areas of law and legal services. Reuse beats
invention, and a reviewer from a firm that has looked at SALI will ask whether the
lab did. The firm's own practice areas are not SALI's, though: they are how the
firm is organised, and knowledge management must be able to change them without
waiting for a standard's release.

## Decision

- The firm keeps its own SKOS schemes. `config/sali-mapping.yaml` says how each
  concept relates to SALI with the SKOS mapping relations — and **none is an
  exactMatch**. The firm's Financial Institutions group is broader than SALI's
  Banking Law (`narrowMatch` to Banking Law and to Insurance Law); TMT includes
  technology, which SALI's TME does not (`closeMatch`); transactions are broader
  than M&A (`narrowMatch`).
- `scripts/sali-subset.py` imports only the mapped concepts and their parents from
  **a pinned commit** (`3f9ac0c`, 2026-03-10), checks every mapped IRI exists in it,
  and records the file's sha256. Loaded into `g:vocab/sali`.
- **The namespace was read from the release, not assumed.** It is
  `http://lmss.sali.org/` — not the `https://sali.org/` that would have been the
  guess. A test fails if the guess ever appears.

## Consequences

- A query can reason across the firm's scheme and SALI's through the mappings,
  and the mapping relation says how much that reasoning can be trusted.
- One framing difference is worth knowing: SALI files Regulatory Investigation
  under "Regulatory Services (Non-Dispute)"; a firm treats an investigation as
  contentious. The mapping holds; reasoning over parents would inherit the framing.
- LMSS is MIT-licensed. The subset is committed with its provenance; the full
  17 MB ontology is not. `docs/sources.md` is the register.
