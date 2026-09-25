# 27. The demo UI — one screen per person, the evidence beside the answer

Status: accepted · 2026-09-25

## Context

The demo ran in terminals: Claude Code for the question, the CLI for the record.
A room watching that sees text scroll by, not *why* an answer is the answer. The
screen has to show the route, the readings and their owners, the rule that
withheld something, the documents, each fact's lineage, and — for Risk — the
record and whether its chain holds. It must not weaken anything ADR 0011, 0013,
0021 or 0022 claims.

## Decision

- **One process per person.** `web-mara`, `web-sanne`, `web-kim`, `web-risk`: one
  image, four containers, each started with `TKG_PERSONA` and **only its own key**
  mounted at `/run/secrets/persona.key`. There is no persona switcher. A dropdown
  that changes who you are is a role the browser can pass, and ADR 0011 says a role
  the caller can pass is not a boundary.
- **No login.** The person is the container, exactly as the person is the MCP
  container. That is no weaker than ADR 0011: identity was already asserted by
  whoever holds the key, and it still is. The page says so in a permanent banner.
  Reaching a screen means an ssh tunnel to a loopback port, as for every other
  service (ADR 0003).
- **A backend-for-frontend.** Next.js route handlers mint the same short-lived
  HS256 assertion as `src/tkg/identity.py` (kid = persona; persona, aud, iat,
  exp = iat + 60) and call the resolver. The browser never sees a key and never
  reaches the resolver. The containers join `tkg_edge` only, where the resolver is
  the one other service. Each route forwards a fixed set of fields to one endpoint;
  none takes a persona.
- **No document proxy.** PDF links are the resolver's presigned URLs for
  `127.0.0.1:9100`, signed with the person's own store credentials (ADR 0021). The
  viewer tunnels 9100 too. A route that turned an identifier into bytes would be
  the second door ADR 0021 refuses.
- **Chat is Claude, through the Anthropic API directly** (`TKG_MODEL`, default
  `claude-opus-5-5`, low effort), not through a gateway. The model gets the MCP
  server's tools and instructions, verbatim; each tool call is a resolver call as
  the screen's person. The conversation is sent back unchanged each turn.
- **Guided mode needs no model.** Pick a competency question, fill its slots, look
  words up with `resolve_term`, ask. It is the fallback when the room's network or
  the key is not there, and it renders the same answer and the same inspector.
- **The inspector** reads only what the resolver returned or will return to this
  person: Trace, Explain, Sources (with `passages()` under the answer's permit),
  Lineage (`/lineage` per cited graph — itself decided and recorded), and Record
  (`explain(trace)` from the stored chain). Risk's screen adds the three audit
  questions and `/audit/verify`; the others' screens do not show them, and the
  resolver refuses them if called.
- **Copied, not linked.** The shell — Next.js 15, React 19, Tailwind, shadcn/ui
  components, the markdown and table renderers, the NDJSON reader, the Dockerfile
  shape — was copied from an existing internal Next.js shell by the same author and
  is MIT here. Stripped: its authentication, its non-English dictionary, a vendored
  SDK and its instrumentation, and all of its domain code. The chat view was
  written new.

## Consequences

- The boundary scene stays visibly true: two windows, two people, the same question,
  two answers — and no control on either that makes one the other.
- Anyone who can open a screen's port *is* that person. That is the ADR 0011
  weakness in a new place, not a new weakness; the tunnel is the only way in.
- What the screen shows of the model's text is observed, not measured — as for
  Claude Code (README, honesty statement). Every table and panel beside it is the
  resolver's own response.
- The screens write to the record like any caller: opening Lineage or Record is a
  request, decided and chained.
- Chat costs money per turn and needs a key on the host; guided mode costs nothing.
