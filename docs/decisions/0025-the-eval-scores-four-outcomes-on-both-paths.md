# 25. The eval scores four outcomes on both paths, against a truth the graph did not compute

Status: accepted · 2026-09-25 · M4

## Context

"The graph path is better" is a claim. It becomes a finding only when both paths
answer the same questions, the right answers are known independently of either,
and a leak is scored next to a wrong answer rather than as a different kind of
problem.

## Decision

- **Thirty questions** in `config/battery.yaml`: seventeen ordinary, eight behind a
  wall (the persona is screened from what the answer turns on), five whose true
  answer is that the firm has not done this.
- **Truth is computed from the estate in Python** — the generator's own objects —
  never from the graph being scored. For a persona, walled matters are removed; if
  nothing is left, the right answer is a refusal.
- **Graph path**: through the resolver, as the persona, bound to a template; scored
  mechanically. An answer that is right but cannot give an outcome no document
  recorded is *correct and incomplete*, not wrong — it did not assert one.
- **Vector path**: the same words, top-5 passages over the whole index, no access
  decision; Claude composes an answer from them, and Claude grades it against the
  truth. Both are a committed fixture; retrieval is re-run every time and an answer
  composed over different passages is reported *stale*, never reused.
- **Four outcomes, in precedence**: leaked > confidently wrong > refused > correct.
  On the vector path, *leaked* means a passage from a walled matter was put in front
  of the model on that person's behalf — whether or not it repeated it.

## Consequences

- The graph path can lose: an extracted outcome that contradicts the truth is
  *confidently wrong*, however it arrived.
- The judge is a model. Its verdicts are committed, with its reasons, so they can be
  read and disputed; the leak verdict is mechanical and needs no judge.
- Thirty questions measure the method, not a firm. The numbers are the lab's.
