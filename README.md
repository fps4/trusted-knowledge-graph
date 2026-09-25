# trusted-knowledge-graph

**A knowledge layer a lawyer can act on and an AI can stand on.** A legal-shaped
estate, a graph anchored to systems of record rather than scraped out of text, and
one resolver that decides what a given person may see before any evidence is
assembled — and writes down what it decided.

```
  SYSTEMS OF RECORD      R2RML       THE GRAPH            THE RESOLVER               WHO ASKS

  practice mgmt ─┐                 spine: matters,      1 plan  2 terms  3 route    Claude Code
  CRM            ├─► mappings/ ─►  clients, people      4 bind                      one session
  HR             ┘                 + told facts with    5 DECIDE ◄── OPA ◄── barriers.yaml
                                     their lineage      6 passages (M3)             per person,
                                                        7 compose or refuse  ◄───── over MCP
                                                              │
                                                              ▼
                                                  one hash-chained record per request
```

> **Status: M4, two runs short.** Everything below runs and `make gate` passes.
> Two numbers need a model and are not in yet: extraction scored against the gold
> set (`make extract`), and the vector path's composed answers and verdicts
> (`make eval-live`). Until they are, `reports/extraction.md` does not exist and the
> vector column below counts only what needs no model — its leaks.

```sh
make build && make up-stores && make load && make policy   # first run
make demo        # the scenes, asked as the personas, through the resolver
make reports     # eval, leak, glossary, audit and extraction reports from a fresh record
make gate        # the deploy gate — non-zero on any failure
```

## Honesty statement

Written before the numbers, and it stays at the top.

- **No real firm, no real person, no real client, no real matter.** The estate is
  invented and generated deterministically from `config/estate.yaml`. Nothing here
  is legal advice or a statement about any organisation.
- **This is not production experience.** It is a pattern, implemented and measured.
- **Laptop scale.** Around 400 matters and, later, ~2,000 documents — not 1.2
  million. No throughput claim, no cost claim, no latency claim is made anywhere.
- **Identity is asserted, not federated.** Each persona's MCP container holds a key
  and mints a short-lived assertion; the resolver verifies it. In the design this
  is the OAuth on-behalf-of flow against a real identity provider. **This is the one
  place the lab is weaker than the architecture it demonstrates**, and anyone who
  can read `secrets/` can be anyone. ([ADR 0011](docs/decisions/0011-identity-is-asserted-not-federated.md))
- **Claude is not in the barrier suite.** The suite asks through the same HTTP
  boundary Claude uses, as each person; it does not test what a language model says
  about the answer. That the boundary holds is measured. That a model reports it
  faithfully was observed, not measured.
- **The hash chain is tamper-evident, not tamper-proof**, and it cannot show that
  its tail was cut. `make verify-audit` prints the head hash so it can be held
  elsewhere. ([ADR 0012](docs/decisions/0012-one-chained-record-per-request.md))
- **Apache Jena Fuseki and OPA are lab choices.** OPA is the component the design
  names; Fuseki is a real quad store rather than an embedded library. Neither is a
  recommendation for any particular production estate.
- **Do not expose this stack to a network.** Every port binds to loopback, and the
  stores have no authentication because they are not reachable.
- **The documents are template-written**, from the estate. Their prose is more
  regular than a firm's, so extraction scores are an upper bound; the method is what
  transfers.
- **Two verdicts are a model's.** The vector path's answers are composed by Claude
  and graded by Claude against a truth computed from the estate; both are committed
  with their reasons. Leaks are counted mechanically and need no judge.
- **A presigned link is a bearer token for five minutes.** Anyone its holder forwards
  it to can open it until it expires.
- **Authored AI-assisted**, with the design record in `docs/decisions/` leading the
  code, as in the sibling labs.

## What M3 and M4 show

**Documents with a gold set.** 742 documents — engagement letters, advice memos,
closing letters — written from the ground truth, rendered to PDF and read back,
each recording the facts it was generated to carry. Outcomes exist *only* in closing
letters, as in a firm. That manifest is what extraction is scored against
([ADR 0020](docs/decisions/0020-documents-generated-from-the-ground-truth.md)).

**Two enforcement points, one policy file.** The PDFs sit in a document store with
one user and policy per person, compiled from the same `barriers.yaml` as OPA's
data. The graph refuses the fact; the store refuses the bytes, on its own policy.
Every citation carries a link that opens the PDF, signed with the asking person's
own credentials for five minutes — and a link Sanne signs herself for a walled
document returns 403. OPA and the store agree on every person × document pair
([ADR 0021](docs/decisions/0021-the-document-store-enforces-its-own-access.md)).

**The index is filtered inside the query.** One passage per document, BM25 and
embeddings, with the permitted matters inside both clauses; `passages()` needs the
permit. The index *does* hold document text — the graph holds none, the index holds
permission-trimmed passages, the store holds the bytes
([ADR 0022](docs/decisions/0022-the-index-is-pre-filtered-inside-the-query.md)).

**The comparison.** Asked "what was the outcome of the AFM investigation into Rhine
Capital Partners?", the ordinary vector path returns the closing letter of the
matter Sanne is screened from, first. Across client-named questions about every
restricted matter, asked as each person walled from it, the vector path put walled
passages in front of the model on **8 of 8**; the resolver leaked on **0 of 160**.

**The battery and the gate.** Thirty questions with known answers, computed from the
estate rather than the graph, asked both ways and scored four ways — correct,
refused, confidently wrong, leaked ([ADR 0025](docs/decisions/0025-the-eval-scores-four-outcomes-on-both-paths.md)).
`make gate` holds the policy, the suite, the two enforcement points, the record and
the eval to a baseline, and exits non-zero on any failure
([ADR 0026](docs/decisions/0026-the-gate-and-review.md)).

**Review.** `tkg review list|confirm|reject` — through the resolver, as the reviewer,
on the record. A review is its own graph derived from the fact's, so it is walled
wherever the fact is; answers stop asserting a rejected fact.

**What was cut** — text-to-SPARQL, OPA's log as a second stream, the Ontop test,
Splink, the public corpus, the HTML workbench — is listed with what each costs in
[ADR 0024](docs/decisions/0024-what-was-cut-and-why.md).

## What M2 shows

**A word is not the model's to interpret.** "Active client" means four different
things to four owners — a client with an open matter (the practice groups),
invoiced in the last year (Finance), in the CRM with a relationship partner (BD),
ever acted for (Risk, because a conflict check needs former clients). Four
numbers. `resolve_term("active client")` returns all four with their owners and
counts; a question that names the term without choosing a reading is refused at
the router, with the readings listed back. Asked through Claude Code, the model
does what the refusal tells it: shows the readings and asks which one.
([ADR 0015](docs/decisions/0015-an-ambiguous-term-is-refused-not-resolved.md))

**Words fill slots, not guesses.** "AIFM" resolves to the fund-manager client type;
"AFM investigation" to a regulatory investigation in the Netherlands — with the
caveat, in its definition, that the lab records jurisdiction, not the regulator.
An answer records which glossary terms it rests on, and their owners.

**Reuse by mapping.** The firm's practice areas and matter types are mapped to
[SALI LMSS](https://github.com/sali-legal/LMSS) with SKOS relations that say how
close each is — none is an exact match. The subset is imported from a pinned
commit, and the namespace was read from the release rather than assumed: it is
`http://lmss.sali.org/`, not the `https://sali.org/` one would guess.
([ADR 0016](docs/decisions/0016-sali-lmss-by-mapping-not-adoption.md),
[`reports/glossary.md`](reports/glossary.md))

**Every answer says how it was routed.** graph · index · hybrid · refuse, with the
reason. Until the index exists (M3), a question that needs passages is refused and
says so. ([ADR 0017](docs/decisions/0017-the-router-decides-and-says-why.md))

**The record has its own access model.** OPA decides who may read it, from a rule
in `barriers.yaml`: Risk & Compliance, nobody else. Risk resolves the salted
hashes and answers the three questions — who has ever been shown anything derived
from M-2022-0117, what did Sanne see, why was that trace refused — and gets the
same grounds Sanne was shown at the time, from the same record. Risk sees no
matter content, and Risk's own reads go into the same chain.
([ADR 0018](docs/decisions/0018-reading-the-record-is-an-access-decision.md),
[`reports/audit.md`](reports/audit.md))

**What M2 found.** Refusing an aggregate over a set you cannot fully see is right
for "who has the most AFM experience". For a firm-wide count it means nobody gets
an answer: every lawyer in the lab is walled from *something* the Finance and Risk
readings of "active client" count, so both are refused for all three of them. In a
real firm, with hundreds of need-to-know matters, every firm-wide metric would be.
The options and their side channels are in
[ADR 0019](docs/decisions/0019-aggregates-over-walls-an-open-decision.md) — an open
decision, for the firm, not the lab.

## What M1 shows

**The same question, two people.** Mara, a partner, asks whether the firm has
advised a Dutch fund manager on an AFM investigation since 2021, who led it and what
the outcome was. She gets five matters, each citing the system it came from — two
outcomes confirmed, one *unconfirmed* and saying so, and two matters with no outcome,
because none was recorded and the answer does not invent one. Sanne, screened from one of
those matters, asks the identical question and gets four, and is told one matter and
one derived fact were withheld under rule B-03, with its owner and the date it was
set.

**Three refusals, and why each is the right one.**

| Sanne asks | Outcome | Why |
|---|---|---|
| Who led M-2022-0117? | refused | direct: the matter is behind B-03 |
| Who has led the most AFM investigations? | refused-aggregate | a count over a set she cannot see in full is wrong in a way she could not detect |
| What expertise is recorded for Mara? | one fact of two | the other names no matter — it was *derived* from one, and lineage decides |

The third is the case the design exists for. The withheld fact is about a person,
not a matter; only its lineage, over `prov:wasDerivedFrom+`, connects it to the
restricted matter — and that is enough.

**Decide, then retrieve.** The resolver asks the graph which matters and derived
graphs a question would reach, asks OPA which of those this person may see, and
only then runs the query — bound to the permitted set. The query that produces
evidence cannot name a denied matter. Nothing is filtered afterwards.
([ADR 0009](docs/decisions/0009-decide-then-retrieve.md))

**One rule file, checked against the firm's own records.** `config/barriers.yaml`
is the only place an access rule is written. It compiles to the data OPA evaluates,
and the compiler refuses to write a policy when a rule and the practice-management
system's restriction records disagree. Insiders are referenced from the matter team,
never copied. ([ADR 0007](docs/decisions/0007-the-rule-lives-in-barriers-yaml.md))

**Disclosure is a policy decision with an owner.** Whether a screened person is told
that something was withheld is `disclosure:` in `barriers.yaml` — both modes are
implemented, and the caller cannot choose. A refusal is itself a one-bit disclosure;
that is stated, not discovered.
([ADR 0010](docs/decisions/0010-disclosure-is-a-policy-setting.md))

**The record.** Every request writes one line to `audit/decisions.jsonl`, once, at
completion, answered or refused, chained by hash. The audit log of a barrier system
is itself confidential: a record saying *Sanne was denied M-2022-0117* would tell its
reader what the barrier hides. So denied identifiers are salted hashes in **every**
field — including the slot she typed — and free text is not logged at all.
`explain(trace)` reads the stored record: the live explanation and the later one are
the same object. ([ADR 0013](docs/decisions/0013-denied-identifiers-are-salted-hashes.md))

**The boundary.** One MCP server per person, started as that person, holding only
that person's key, on a network where the resolver is the only other service. No
tool takes a persona. There is no `document()` tool. `passages()` needs the permit
`ask()` issued, to the same person — the lock is fitted before the index it guards
exists.

## The numbers

From `reports/eval.md` — thirty questions, both paths:

| path | correct | refused | confidently wrong | **leaked** | not yet run |
|---|---|---|---|---|---|
| graph-grounded, through the resolver | 30 | 0 | 0 | **0** | — |
| vector-only, no access decision | *pending* | *pending* | *pending* | **6** | 24 |

The vector path's six leaks need no model to count: walled passages were placed in
its context. Its other verdicts wait for `make eval-live`. Six of the graph path's
thirty answers are right but incomplete — outcomes no document or partner has
recorded yet, which the answer does not invent.

From `reports/leak.md`, generated by `make leak`:

| | |
|---|---|
| questions asked — every rule × every persona × direct / second hop / lineage / aggregate / documents, the glossary path, passages | 160 |
| … where the persona is denied the matter | 64 |
| **leaked** | **0** |
| wrong refusals, including over-refusals of matters the persona may see | 0 |
| doors behaving — the permit, and the record only Risk may read | 16 / 16 |
| audit records checked for a denied identifier in clear, including Risk's own reads | 164 — **0 found** |
| person × document checks, OPA against the document store | 3,710 — **0 disagreements** |
| walled documents fetched with the walled person's own credentials | 15 — **all refused** |

Who *should* be denied is computed from `barriers.yaml` and the systems of record
directly, bypassing both the policy compiler and OPA. That independence was checked
by breaking it: with Sanne's screen removed from the compiled policy only, the suite
reported six leaks, two wrong refusals and fourteen clear-text identifiers in the
log — a check run by hand, not a committed test. An earlier version read the compiled policy for its expectations — and passed
the tampered one, because it agreed with itself.

**What the first Claude Code session found.** A persona's description, returned by
`whoami()`, named the matter she is screened from. The suite had never looked at
`whoami()`. It does now, and the description no longer does.

## From M0, still true

- **The systems of record are a database**, not CSV exports, so the spine is built by
  declarative R2RML over live tables, read through a role that cannot write back.
- **SHACL is the load contract.** A load that violates the shapes does not land —
  including the rule that no literal exceeds 500 characters, because the graph holds
  assertions and identifiers, never document content. From M1 the shapes also
  refuse a fact without a source, confidence and review state, and a derived graph
  without lineage.
- **The model does not write SPARQL.** Questions are templates bound to competency
  questions, and from M1 every template declares every graph it touches.
- **The mess is in the data, on purpose**: the same organisation spelled differently
  in the practice-management system and the CRM, and colleagues sharing a family name.

## Running it on a Docker host

The lab is deployed by hand to a Docker host, and nothing on it is exposed: every port
binds to the host's loopback. There is no CI; the gate is a command.

```sh
ssh host 'git clone https://github.com/fps4/trusted-knowledge-graph && cd trusted-knowledge-graph \
  && make build && make up-stores && make load && make policy'
ssh -L 8480:127.0.0.1:8480 host      # the resolver, if you want it from here
```

Claude Code stays on your machine. The MCP container — and the persona's key — stay
on the host, reached over ssh:

```sh
make mcp-configs HOST=host           # writes mcp/<persona>.json locally
claude --strict-mcp-config --mcp-config mcp/sanne.json
```

## Using it from Claude Code

`make init` writes one MCP config per person, for a stack on the same machine. One
session, one person:

```sh
claude --strict-mcp-config --mcp-config mcp/sanne.json
```

A single `.mcp.json` listing everyone would give one session every person's tools at
once, which is exactly the boundary the demo is about — so there isn't one.

## Layout

| | |
|---|---|
| `config/estate.yaml` | the whole synthetic firm, including the deliberate mess |
| `config/barriers.yaml` | **the only place an access rule is written** — owner, dates, disclosure |
| `config/people.yaml` | who can ask; what they *are* comes from HR, not from here |
| `config/asserted.yaml` | facts told by a named partner, each with its lineage |
| `config/audit.yaml` | what the record keeps, hashes, omits, and for how long |
| `config/glossary.yaml` | business terms, owners, readings, what an ambiguous term gets |
| `config/sali-mapping.yaml` | the firm's vocabularies against SALI LMSS, pinned |
| `config/relations.yaml` | who owns each relation, and whether it states the present or a date |
| `vocab/` | the imported SALI subset, with provenance — `docs/sources.md` is the register |
| `config/battery.yaml` | thirty questions, each with how its truth is computed |
| `data/fixtures/` | the documents and their manifest; extraction and vector-eval results once run |
| `sql/`, `mappings/` | the systems of record, and R2RML over them |
| `ontology/` | a small OWL profile, and the shapes that gate every load |
| `policy/access.rego` | the policy — hand-written, with `opa test` cases |
| `build/opa/data.json` | the policy's data, compiled from `barriers.yaml` — generated |
| `src/tkg/resolver/` | the seven steps, and the HTTP API they sit behind |
| `src/tkg/access/` | compiler, lineage, OPA client, permit |
| `src/tkg/audit/` | the chained writer, salted hashes, verification |
| `src/tkg/mcp/` | one MCP server per person |
| `src/tkg/semantic/` | templates, the glossary resolver, the router |
| `src/tkg/dms.py`, `src/tkg/index.py` | the document store and the index |
| `src/tkg/ingest/` | estate, documents, extraction, linking, the load pipeline |
| `src/tkg/eval/` | the barrier suite, the battery, truth, extraction scoring |
| `reports/` | `eval.md`, `leak.md`, `glossary.md`, `audit.md`, `baseline.json` — generated, never typed |
| `docs/decisions/` | twenty-six ADRs, written before the code they justify — one still open |

MIT.
