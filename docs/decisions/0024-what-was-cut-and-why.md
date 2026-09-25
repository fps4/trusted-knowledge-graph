# 24. What was cut, and why — the cut list, applied

Status: accepted · 2026-09-25

The build plan ordered what would be cut under pressure. What was cut is listed
here rather than left to be discovered, each with what it costs.

| Cut | Instead | What it costs |
|---|---|---|
| Free-form text-to-SPARQL comparison | — | The price of the template discipline is argued (ADR 0004), not measured |
| OPA's decision log as a second audit stream, cross-checked | The resolver's hash-chained record only | A governance claim backed by one stream. Not implied otherwise anywhere |
| Ontop virtual-spine test | — (untested) | The finding that would change the programme's commercial shape remains an argument. The materialised spine is what runs |
| Splink identity resolution | Exact-match linking; unlinked facts counted | Clients spelled as the CRM spells them stay unlinked — visible as recall loss in `reports/extraction.md` |
| Public legal corpus (ECLI, ELI, EUR-Lex) | — | UC-2 answers from the firm's own documents only; `docs/sources.md` has no public-material rows |
| Review workbench (HTML) | `tkg review` — list, confirm, reject, through the resolver and on the record | The component the Head of Data would care about most is a CLI. Cut last, and still cut |

What was **not** cut, as the plan required: the barrier suite, `explain()`,
per-fact provenance, the no-content shape, the hashed denied identifiers, the
scored comparison.
