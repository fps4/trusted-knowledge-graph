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

> **Status: M1.** Two lawyers ask the same question in two Claude Code sessions;
> one is answered and one is refused, with the rule, its owner and the date it was
> set — and every request is on a tamper-evident chain. There are no documents,
> no extraction and no glossary yet: those are M2 to M4. What is here runs.

```sh
make build && make up-stores && make load && make policy   # first run
make demo        # the scenes, asked as the personas, through the resolver
make leak        # the barrier suite → reports/leak.md
make verify-audit
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
- **Authored AI-assisted**, with the design record in `docs/decisions/` leading the
  code, as in the sibling labs.

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

From `reports/leak.md`, generated by `make leak`:

| | |
|---|---|
| questions asked, every rule × every persona × direct / second hop / lineage / aggregate | 112 |
| … where the persona is denied the matter | 56 |
| **leaked** | **0** |
| wrong refusals, including over-refusals of matters the persona may see | 0 |
| audit records checked for a denied identifier in clear | 109 — **0 found** |

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
| `sql/`, `mappings/` | the systems of record, and R2RML over them |
| `ontology/` | a small OWL profile, and the shapes that gate every load |
| `policy/access.rego` | the policy — hand-written, with `opa test` cases |
| `build/opa/data.json` | the policy's data, compiled from `barriers.yaml` — generated |
| `src/tkg/resolver/` | the seven steps, and the HTTP API they sit behind |
| `src/tkg/access/` | compiler, lineage, OPA client, permit |
| `src/tkg/audit/` | the chained writer, salted hashes, verification |
| `src/tkg/mcp/` | one MCP server per person |
| `reports/leak.md` | the barrier suite's last run |
| `docs/decisions/` | fourteen ADRs, written before the code they justify |

MIT.
