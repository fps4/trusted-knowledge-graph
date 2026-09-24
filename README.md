# trusted-knowledge-graph

**A knowledge layer a lawyer can act on and an AI can stand on.** A legal-shaped
estate, a graph anchored to systems of record rather than scraped out of text, and
— from M1 — one resolver that decides what a given person may see before any
evidence is assembled.

```
  SYSTEMS OF RECORD        R2RML          THE SPINE              ONE QUESTION
                                                          
  practice mgmt ─┐                     matters · clients    "Have we advised a Dutch
  CRM            ├──► mappings/  ──►   people · assignments  fund manager on an AFM
  HR             ┘    *.r2rml.ttl      with valid-time       investigation since 2021,
                      declarative,                           and who led it?"
                      versioned        every fact cites
                                       its source graph      → answered, with sources
```

> **Status: M0.** The spine is loaded and five competency questions are answered
> from it. There are no documents, no extraction, no access control and no audit
> log yet — those are M1 to M4. What is here runs.

```sh
make build && make up && make load && make demo
```

## Honesty statement

Written before the numbers, and it stays at the top.

- **No real firm, no real person, no real client, no real matter.** The estate is
  invented and generated deterministically from `config/estate.yaml`. Nothing here
  is legal advice or a statement about any organisation.
- **This is not production experience.** It is a pattern, implemented and measured.
- **Laptop scale.** Around 400 matters and, later, ~2,000 documents — not 1.2
  million. No throughput claim, no cost claim, no latency claim is made anywhere.
- **Apache Jena Fuseki is a lab choice.** It is a real quad store with a real
  SPARQL endpoint, which is why it is here rather than an embedded library; it is
  not a recommendation for any particular production estate.
- **Do not expose this stack to a network.** Every port binds to loopback, and the
  services have no authentication because they are not reachable.
- **Authored AI-assisted**, with the design record in `docs/decisions/` leading the
  code, as in the sibling labs.

## What M0 shows

- **The systems of record are a database**, not three CSV exports — so the spine is
  built by declarative R2RML over live tables, which is what the design claims.
- **SHACL is the load contract.** `tkg load` validates before it writes; a load that
  violates the shapes does not land. That includes the rule the whole design rests
  on: no literal over 500 characters, because the graph holds assertions and
  identifiers, never document content.
- **Every fact cites its source graph.** `g:spine/pms`, `g:spine/crm`, `g:spine/hr`.
- **The model does not write SPARQL.** Queries come from templates bound to
  competency questions — the same position as a governed metric registry.
- **The mess is in the data, on purpose.** The same organisation is spelled
  differently in the practice-management system and the CRM, and two colleagues
  share a family name. Nothing resolves them yet, so `CQ-04` shows accounts that
  look like clients you have already seen. That is correct: a merge is a decision
  with a name on it, and it belongs to a later milestone.

## Layout

| | |
|---|---|
| `config/estate.yaml` | the whole synthetic firm, including the deliberate mess |
| `sql/` | the three schemas standing in for practice management, CRM and HR |
| `mappings/*.r2rml.ttl` | the spine mappings — data in git, not code |
| `ontology/firm.ttl` | a small OWL profile |
| `ontology/shapes.ttl` | the load contract |
| `src/tkg/` | generator, mapper, loader, templates, resolver, CLI |
| `docs/decisions/` | why, recorded before the code |

MIT.
