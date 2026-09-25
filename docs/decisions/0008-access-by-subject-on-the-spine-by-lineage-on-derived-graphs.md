# 8. Access is decided by subject on the spine and by lineage on derived graphs

Status: accepted · 2026-09-25

## Context

The architecture says named graphs are the unit of access. That is true for a
graph extracted from one document, or told by one partner about one matter: the
graph derives from something, and it can inherit that thing's restrictions.

It is not true for `g:spine/pms`, which holds all four hundred matters. A named
graph that is every matter cannot be allowed or denied as a whole.

## Decision

- **Spine facts are decided by subject.** Every template declares the variable
  that binds its matter; the matter is what is allowed or denied, and everything
  reached through it — the lead, the team, the client-via-matter — goes with it.
- **Derived graphs are decided by lineage.** A graph inherits the restrictions of
  every matter it was derived from, transitively over `prov:wasDerivedFrom+` in
  `g:prov`. A graph derived from a graph derived from a restricted matter is
  restricted.
- **Traversal in SPARQL, rules in Rego.** The graph answers *what is connected*;
  OPA answers *what is allowed*. The resolver passes OPA the candidate matters and
  a lineage map, and OPA decides both — including that a derived graph is denied
  if any matter in its lineage is.
- **The Rego is written by hand; the data is compiled.** `policy/access.rego` is
  one small reviewed policy with `opa test` cases. `barriers.yaml` compiles to
  `build/opa/data.json`. Generating Rego from YAML would produce a policy harder
  to review than the file it came from.

## Consequences

- Every template must say which of its variables are matters and which are
  derived graphs, and the binder constrains every graph variable it declares.
- A derived graph with no lineage would escape every barrier. The loader refuses
  one.
- The architecture's sentence becomes the precise one: the named graph is the unit
  of *provenance*; access is by subject where the graph is shared and by lineage
  where it is not.
