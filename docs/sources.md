# Sources and licences

Everything in this repository that was not written for it, with its licence,
checked before it was committed. The firm, its people, clients, matters and
documents are invented and generated from `config/estate.yaml`.

| Source | What is used | Where | Licence | Pinned | Checked |
|---|---|---|---|---|---|
| [SALI LMSS](https://github.com/sali-legal/LMSS) — the Legal Matter Specification Standard | 13 concepts the firm maps to, and their 7 parents: labels, definitions, subclass links | `vocab/sali-lmss-subset.ttl`, via `scripts/sali-subset.py` | MIT (repository licence) | commit `3f9ac0c9357b2a971582ae79ede243511d47811d` (2026-03-10); file sha256 in the subset header | 2026-09-25 |

The full LMSS ontology (~17 MB) is fetched by the script and not committed.
No public legal material — decisions, legislation, EU instruments — is used; it was
cut (ADR 0024). Any that is added gets a row here before it is committed.
