# 19. Aggregates over walled matters — an open decision for the firm

Status: **proposed** · 2026-09-25 — the lab's current behaviour is recorded; the choice is not the lab's

## Context

The resolver refuses an aggregate whose candidate set includes any matter the person cannot
see: a count computed over the rest would be wrong in a way they could not detect.
For a question about AFM investigations, that is right.

The glossary shows what it costs. A firm-wide count — how many active clients, by Finance's
reading — touches some matter nearly everyone is walled from. With one
need-to-know matter (B-11) and one office screen (B-12) in a synthetic estate of
400 matters, **Mara, Kim and Sanne are all refused two of the four readings of
"active client"**. In a real firm, with hundreds of need-to-know matters, every
firm-wide metric would be refused for everyone outside every wall — which is
everyone.

## Options

1. **Refuse** (current). Safe, and unusable for firm-wide numbers.
2. **Compute over what you can see, and label it** — the `silent` disclosure mode,
   applied to aggregates only, as a separate setting from row-level disclosure.
   Usable; the number is knowingly partial, and says so.
3. **Value-sensitive** — compute with and without the walled matters; answer if
   they agree, refuse if not. Most answers survive. It means evaluating the
   aggregate over denied matters inside the resolver, which bends ADR 0009.
4. **Coarse only** — answer aggregates above a minimum group size, refuse
   fine-grained ones (statistical disclosure control). Needs a threshold with an
   owner.

## What every option shares

A refusal, and an answer that differs from a refusal, are both signals. Varying a
date slot and watching where the refusal starts reveals when a walled matter
opened — under option 1 as much as under 3. Only option 2 closes that side
channel, at the cost of a partial number. This is the same trade as the
disclosure setting (ADR 0010), for aggregates.

## Recommendation

A separate `aggregates:` setting in `barriers.yaml`, owned by Risk, with option 2
as the lab's proposed default for coarse firm-wide counts and option 1 kept for
fine-grained ones — and the question put to the firm rather than answered for it.
Not implemented until it is decided.
