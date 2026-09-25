"""Extraction: PDF text → Claude → facts with confidence and evidence.

The model sees one document's text — never the ground truth — and returns facts
in a fixed schema whose predicates are exactly the ones the ontology allows a
fact to carry, so an unknown predicate cannot be expressed, let alone stored. The
objects are strings as the document writes them; linking them to identifiers is a
separate, deterministic step (link.py), because that is where a firm's messy
names actually bite.

Runs through the Message Batches API: half the price, and this is fixture
generation, not a request path. Results are committed to
data/fixtures/extraction.jsonl, so `make load` needs no key and no network.
docs/decisions/0023.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

PREDICATES = {
    "forClient": "the matter is for this client (object: the client organisation's name)",
    "ledBy": "the matter is led by this person — the responsible partner (object: full name)",
    "matterType": "the kind of matter (object: one of the matter types listed)",
    "inJurisdiction": "the law the matter concerns (object: one of the jurisdictions listed)",
    "workedOn": "this person worked on the matter (object: full name)",
    "hadOutcome": "how the matter ended (object: one of the outcomes listed)",
    "citesMatter": "the document's matter cites another of the firm's matters, e.g. as "
                   "precedent (object: that matter's reference, like M-2020-0001)",
}

SYSTEM = """You extract facts from one document of a law firm's document management \
system, for a knowledge graph. A fact is about the matter the document belongs to; \
its reference is given, and is the subject unless you say otherwise. When the \
document states something about another matter it cites by reference, give that \
reference as the fact's subject.

Extract only what the document states. Do not infer from what is typical. If the \
document does not state something, do not extract it — a missing fact is correct, \
an invented one is not.

For each fact give:
- predicate: one of the allowed predicates
- subject: only for a fact about a cited matter — its reference, as written
- object: for people and organisations, the name exactly as the document writes it; \
for matter types, jurisdictions and outcomes, the identifier from the lists below
- confidence: 0 to 1 — how clearly the document states it
- evidence: the shortest verbatim quote from the document that supports it, at most \
200 characters

Allowed predicates:
{predicates}

Matter types: {matter_types}
Jurisdictions: {jurisdictions}
Outcomes: {outcomes}"""


def schema(cfg: dict) -> dict:
    return {
        "type": "object",
        "properties": {
            "facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "predicate": {"type": "string", "enum": sorted(PREDICATES)},
                        # Optional: a cited matter's reference. Absent means the
                        # document's own matter; linking checks it is a cited one.
                        "subject": {"type": "string"},
                        "object": {"type": "string"},
                        "confidence": {"type": "number"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["predicate", "object", "confidence", "evidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["facts"],
        "additionalProperties": False,
    }


def system_prompt(cfg: dict) -> str:
    def listing(key: str) -> str:
        return "; ".join(f"{x['id']} ({x['label']})" for x in cfg[key])

    return SYSTEM.format(
        predicates="\n".join(f"- {k}: {v}" for k, v in sorted(PREDICATES.items())),
        matter_types=listing("matter_types"),
        jurisdictions="; ".join(f"{j['id']} ({j['label']})" for j in cfg["jurisdictions"]),
        outcomes=listing("outcomes"),
    )


def request_params(cfg: dict, model: str, matter: str, text: str) -> dict:
    return {
        "model": model,
        "max_tokens": 16000,
        # Stable system prompt first and cached; the document varies after it.
        "system": [{"type": "text", "text": system_prompt(cfg),
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content":
                      f"Matter reference: {matter}\n\nDocument text:\n\n{text}"}],
        "output_config": {"effort": "low",
                          "format": {"type": "json_schema", "schema": schema(cfg)}},
    }


def run_batch(items: list[tuple[str, str, str]], cfg: dict, out: Path, log,
              resume: str | None = None) -> dict:
    """items: (doc_id, matter, pdf_text). Writes one JSON line per document.

    `resume` collects an existing batch instead of submitting a new one — a batch
    keeps running on the server if this process is interrupted, and paying twice for
    the same documents is not a recovery strategy.
    """
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    model = os.environ.get("TKG_MODEL", "claude-opus-5-5")
    client = anthropic.Anthropic()
    if resume:
        batch = client.messages.batches.retrieve(resume)
        log(f"resuming batch {batch.id}")
    else:
        batch = client.messages.batches.create(requests=[
            Request(custom_id=doc_id, params=MessageCreateParamsNonStreaming(
                **request_params(cfg, model, matter, text)))
            for doc_id, matter, text in items
        ])
        log(f"batch {batch.id} — {len(items)} documents, model {model}")
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        c = batch.request_counts
        log(f"  {batch.processing_status}: {c.succeeded} done, {c.processing} processing")
        time.sleep(30)

    usage = {"input": 0, "output": 0, "cache_read": 0, "refused": 0, "errored": 0}
    lines = {}
    for result in client.messages.batches.results(batch.id):
        row = {"doc_id": result.custom_id, "model": model, "batch": batch.id}
        if result.result.type != "succeeded":
            usage["errored"] += 1
            row.update(status=result.result.type, facts=[])
        else:
            msg = result.result.message
            usage["input"] += msg.usage.input_tokens
            usage["output"] += msg.usage.output_tokens
            usage["cache_read"] += msg.usage.cache_read_input_tokens or 0
            if msg.stop_reason == "refusal":
                usage["refused"] += 1
                row.update(status="refused", facts=[])
            elif msg.stop_reason == "max_tokens":
                row.update(status="truncated", facts=[])
            else:
                text = next(b.text for b in msg.content if b.type == "text")
                row.update(status="ok", facts=json.loads(text)["facts"])
        lines[result.custom_id] = row
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(lines[k], sort_keys=True, ensure_ascii=False)
                             for k in sorted(lines)) + "\n", encoding="utf-8")
    return usage


def read(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {r["doc_id"]: r for r in rows}
