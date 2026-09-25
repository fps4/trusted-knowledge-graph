# 3. Every port binds to loopback, and the services have no authentication

Status: accepted · 2026-09-24

## Context

Fuseki, Postgres and the resolver all ship with either no authentication or
defaults nobody should rely on. The honest options are to configure real
authentication on each, or to make them unreachable and say so.

## Decision

Every published port binds to `127.0.0.1`. No service on the internal network
authenticates its callers. The README says this in plain words, next to the
instruction not to expose the stack.

## Consequences

- The access control that is real — policy decisions compiled from
  `config/barriers.yaml` — is not confused with transport security that is not.
- A reviewer can tell the difference between "this lab demonstrates an access
  model" and "this lab is hardened", because the repo draws the line itself
  rather than leaving it to be found.
- If any of this were ever exposed, that would be a finding. Saying so first costs
  nothing and is the only version of the claim that survives scrutiny.
