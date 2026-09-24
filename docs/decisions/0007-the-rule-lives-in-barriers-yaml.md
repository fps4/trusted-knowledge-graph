# 7. The rule lives in `barriers.yaml`; the system of record evidences it

Status: accepted · 2026-09-25 · M1

## Context

Two places know about a barrier. The practice-management system records *that*
M-2022-0117 is restricted — a rule id, a kind, a date, who set it — because in a
firm that row is written by the conflicts and risk process. What it does not
record is the rule itself: who is inside, who is screened, who owns it, when it is
reviewed, and what a screened person is told.

If both places were allowed to encode the rule, the lab would have two policies
and no way to say which one decided. If only the YAML existed, the lab would be
enforcing barriers the firm's own records have never heard of.

## Decision

- **`config/barriers.yaml` holds the rule**, and it is the only file in the repo
  that may. Two kinds, because firms have both:
  - `barrier` — default allow; the screened (named people, practice areas,
    offices) are denied.
  - `need-to-know` — default deny; only insiders see the matter.
- **Insiders are referenced, not copied.** `insiders: {matter_team: true}`
  resolves against `pms.matter_team` at compile time. A copied team list would
  be a third source.
- **Insiders win over a group screen.** B-03 screens the financial-institutions
  group, and one FI associate is on the M-2022-0117 team. That person was put on
  the matter by the process that set the barrier; the screen is for everyone else.
  A *named* person who is both inside and screened is a contradiction, and the
  compiler refuses it.
- **The compiler checks the rules against the system of record and refuses to
  write a policy when they disagree**: every restriction row has exactly one rule
  with the same id, matter and kind, and every rule points at a restriction row.

## Consequences

- A barrier that exists in the rules but not in the firm's records — or the
  reverse — stops the build. That is a governance incident, and the compiler is
  where it is caught rather than an audit a year later.
- The rule has an owner, a date and a review cycle, and those travel into every
  decision it makes and every refusal that names it.
- The estate generator and the rules file are coupled through rule ids. Changing
  the seed changes the generated restrictions, and the compiler says so.
