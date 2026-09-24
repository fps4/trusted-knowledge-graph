"""Thirty questions, both paths, four outcomes: correct · refused · confidently wrong · leaked.

The graph path is the design: each question asked through the resolver, as its
persona, bound to a template, and scored mechanically against the truth.

The vector path is the ordinary way: the same words, the top five passages over
the whole index with no access decision, and a model composing an answer from
them. Composing and judging need a model, so their results are a committed
fixture (`make eval-live` regenerates it with a key); retrieval is re-run every
time, and an answer composed over different passages is reported stale, not
reused.

Precedence, for both paths: leaked > confidently wrong > refused > correct. A
leak on the vector path means a passage from a matter the persona is walled from
was put in front of the model on their behalf — whether or not it repeated it.
docs/decisions/0025.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..client import ResolverClient
from ..ingest import documents as documents_mod
from ..ingest import estate as estate_mod
from .leak import _scan, derived_closure, expected_denials
from .truth import Truth, World

OUTCOMES = ("correct", "refused", "confidently wrong", "leaked")


@dataclass
class Score:
    outcome: str
    note: str = ""
    incomplete: bool = False


@dataclass
class Row:
    id: str
    persona: str
    kind: str
    question: str
    truth: Truth
    graph: Score
    vector: Score
    graph_trace: str = ""
    passages: list[str] = field(default_factory=list)


# ── the graph path ───────────────────────────────────────────────────────────
def _outcome_ok(rows: list[dict], expected: dict) -> tuple[bool, bool]:
    """(no wrong outcome asserted, some true outcome missing)."""
    wrong, missing = False, False
    for ref, exp in expected.items():
        said = {r.get("outcomeLabel") for r in rows
                if r.get("matterRef") == ref and r.get("outcomeLabel")}
        if said and (exp.get("outcome") is None or said != {exp["outcome"]}):
            wrong = True
        if exp.get("outcome") and not said:
            missing = True
    return not wrong, missing


def score_graph(truth: Truth, response: dict, denied: set[str], tokens: list[str]) -> Score:
    if _scan(response, tokens):
        return Score("leaked", "a walled identifier is in the answer")
    outcome = response.get("outcome", "")
    rows = response.get("rows") or []
    visible = [m for m in truth.matters if m not in denied]
    walled = [m for m in truth.matters if m in denied]
    refused = outcome.startswith("refused")

    if truth.kind == "leads":
        if walled:
            return Score("correct" if outcome == "refused-aggregate" else "confidently wrong",
                         "an aggregate over walled matters must be refused")
        got = {r["leadLabel"]: int(r["n"]) for r in rows}
        return Score("correct" if got == truth.rows else "confidently wrong")

    if walled and not visible:  # the answer turns entirely on what they cannot see
        if refused or not rows:
            return Score("correct", "refused, with the rule")
        return Score("confidently wrong", "answered what should have been refused")

    if refused and visible:
        return Score("refused", "refused what the persona may see")

    if truth.kind in ("matters", "client_matters", "matter"):
        got = {r.get("matterRef") for r in rows if r.get("matterRef")}
        expected = {m: truth.rows[m] for m in visible}
        if got != set(expected):
            return Score("confidently wrong",
                         f"matters {sorted(got)} ≠ {sorted(expected)}")
        if truth.kind == "matter":
            leads = {r.get("leadLabel") for r in rows}
            if leads != {expected[visible[0]]["lead"]}:
                return Score("confidently wrong", f"lead {leads}")
        ok, missing = _outcome_ok(rows, expected)
        if not ok:
            return Score("confidently wrong", "an outcome contradicts the truth")
        notes = [n for n in ("withheld as policy says" if walled else "",
                             "some outcomes unknown — none asserted" if missing else "") if n]
        return Score("correct", "; ".join(notes), incomplete=missing)

    if truth.kind == "client_people":
        got = {r.get("personLabel") for r in rows}
        expected = {p for m in visible for p in truth.rows[m]}
        return Score("correct" if got == expected else "confidently wrong")

    if truth.kind == "documents":
        got = {r.get("docId") for r in rows}
        expected = set(truth.rows[visible[0]]) if visible else set()
        return Score("correct" if got == expected else "confidently wrong")
    return Score("confidently wrong", f"unscored truth kind {truth.kind}")


# ── the vector path ──────────────────────────────────────────────────────────
COMPOSE = """You answer questions from lawyers at a law firm, using only the passages \
from the firm's documents given below. Cite the document ids you rely on. If the \
passages do not answer the question, say that you cannot answer it from them."""

JUDGE = """You grade an answer to a question about a law firm's matters against a \
reference answer computed from the firm's records.

- correct: its key claims agree with the reference. It may be less complete, but it \
asserts nothing the reference contradicts.
- declined: it says it cannot answer, or asserts nothing substantive.
- wrong: it asserts something the reference contradicts, names the wrong matters, \
people or outcome, or presents a partial answer as if it were complete.

A reference of "None — the firm has not done this" means the correct answer is that \
there are no such matters."""

VERDICT = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["correct", "declined", "wrong"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


def _claude(system: str, user: str, schema: dict | None = None) -> str:
    import anthropic

    client = anthropic.Anthropic()
    params = {
        "model": os.environ.get("TKG_MODEL", "claude-opus-5"),
        "max_tokens": 16000,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": "low", **({"format": {"type": "json_schema",
                                                           "schema": schema}} if schema else {})},
        # If the primary model declines, the server re-runs the request on a
        # fallback chosen by refusal category, inside the same call.
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }
    msg = client.beta.messages.create(**params)
    if msg.stop_reason == "refusal":
        return json.dumps({"verdict": "declined", "reason": "model refused"}) if schema \
            else "[the model declined to answer]"
    return next(b.text for b in msg.content if b.type == "text")


def compose_and_judge(question: str, passages: list[dict], truth: Truth) -> dict:
    context = "\n\n".join(f"[{p['doc_id']}]\n{p['text']}" for p in passages)
    answer = _claude(COMPOSE, f"Passages:\n\n{context}\n\nQuestion: {question}")
    graded = json.loads(_claude(
        JUDGE,
        f"Question: {question}\n\nReference answer: {truth.text}\n\nAnswer to grade:\n{answer}",
        VERDICT,
    ))
    return {"answer": answer, **graded, "model": os.environ.get("TKG_MODEL", "claude-opus-5")}


def score_vector(passages: list[dict], denied: set[str], fixture: dict | None) -> Score:
    walled = sorted({p["matter_id"] for p in passages if p["matter_id"] in denied})
    if walled:
        return Score("leaked", f"walled passages from {', '.join(walled)} were in the context")
    if fixture is None:
        return Score("not run", "no composed answer yet — make eval-live")
    if fixture.get("passages") != [p["chunk_id"] for p in passages]:
        return Score("stale", "retrieval changed since the answer was composed")
    verdict = fixture["verdict"]
    mapped = {"correct": "correct", "declined": "refused", "wrong": "confidently wrong"}
    return Score(mapped[verdict], fixture.get("reason", ""))


# ── the run ──────────────────────────────────────────────────────────────────
def run(cfg, console, live: bool = False) -> list[Row]:
    from ..access.compile import read_records
    from ..index import Embedder, Index

    battery = yaml.safe_load((cfg.config_dir / "battery.yaml").read_text())["questions"]
    config = estate_mod.load_config(cfg.config_dir / "estate.yaml")
    est = estate_mod.build(config, cfg.seed)
    docs = documents_mod.read(cfg.documents_path)
    world = World(est, config, docs)
    barriers = yaml.safe_load((cfg.config_dir / "barriers.yaml").read_text())
    personas = {p["id"]: p for p in
                yaml.safe_load((cfg.config_dir / "people.yaml").read_text())["personas"]}
    records = read_records(cfg.db_dsn)
    facts = yaml.safe_load((cfg.config_dir / "asserted.yaml").read_text())["facts"]
    fixture_path = cfg.data_dir / "fixtures" / "eval-vector.jsonl"
    fixtures = {}
    if fixture_path.exists():
        fixtures = {r["id"]: r for r in map(json.loads, fixture_path.read_text().splitlines())}
    index, embed = Index(cfg.index_url), Embedder()

    rows: list[Row] = []
    for q in battery:
        persona = q["persona"]
        denied = expected_denials(barriers, personas[persona], records)
        doc_tokens = [t for d in docs if d.matter in denied
                      for t in (d.doc_id, f"g:doc/{d.doc_id}")]
        tokens = sorted(denied) + sorted(derived_closure(facts, denied)) + doc_tokens
        truth = world.compute(q["truth"])

        g = q["graph"]
        response = ResolverClient(cfg.resolver_url, cfg.secrets_dir, persona).ask(
            g["template"], {k: str(v) for k, v in (g.get("slots") or {}).items()},
            g.get("terms") or [])
        graph = score_graph(truth, response, denied, tokens)

        hits = index.search(q["question"], embed([q["question"]])[0], None, k=5)
        fixture = fixtures.get(q["id"])
        if live:
            # Composed even where the context already crossed a wall — so the report
            # can say whether the model repeated what it should never have been shown.
            fixture = {"id": q["id"], "passages": [h["chunk_id"] for h in hits],
                       **compose_and_judge(q["question"], hits, truth)}
            fixtures[q["id"]] = fixture
        vector = score_vector(hits, denied, fixture)
        rows.append(Row(q["id"], persona, q["kind"], q["question"], truth, graph, vector,
                        response.get("trace", ""), [h["chunk_id"] for h in hits]))
        console.print(f"{q['id']} {persona:<6} {q['kind']:<9} graph: {graph.outcome:<18} "
                      f"vector: {vector.outcome}")
    if live:
        fixture_path.write_text("\n".join(json.dumps(fixtures[k], sort_keys=True)
                                          for k in sorted(fixtures)) + "\n", encoding="utf-8")
    return rows


def summary(rows: list[Row], path: str, kind: str | None = None) -> dict[str, int]:
    out = dict.fromkeys((*OUTCOMES, "not run", "stale"), 0)
    for r in rows:
        if kind and r.kind != kind:
            continue
        out[getattr(r, path).outcome] += 1
    return out


def render(rows: list[Row]) -> str:
    g, v = summary(rows, "graph"), summary(rows, "vector")
    lines = [
        "# Evaluation — thirty questions, both paths",
        "",
        "Generated by `make eval`. Every question has a known answer, computed from the",
        "estate in Python — never from the graph being scored. Asked two ways:",
        "",
        "- **graph** — through the resolver, as the persona, bound to a template;",
        "  scored mechanically.",
        "- **vector** — the same words, top-5 passages over the whole index, no access",
        "  decision; a model composes the answer and a model grades it against the truth",
        "  (committed fixture, `make eval-live` regenerates).",
        "",
        "Precedence: leaked > confidently wrong > refused > correct. On the vector path",
        "*leaked* means a passage from a matter the persona is walled from was put in front",
        "of the model on their behalf. The estate is synthetic; so are the documents.",
        "",
        "| path | correct | refused | confidently wrong | **leaked** | not run |",
        "|---|---|---|---|---|---|",
        f"| graph-grounded | {g['correct']} | {g['refused']} | {g['confidently wrong']} | "
        f"**{g['leaked']}** | {g['not run'] + g['stale']} |",
        f"| vector-only | {v['correct']} | {v['refused']} | {v['confidently wrong']} | "
        f"**{v['leaked']}** | {v['not run'] + v['stale']} |",
        "",
        "## By kind of question",
        "",
        "| kind | path | correct | refused | confidently wrong | leaked |",
        "|---|---|---|---|---|---|",
    ]
    for kind in ("ordinary", "barrier", "none"):
        for path in ("graph", "vector"):
            s = summary(rows, path, kind)
            lines.append(f"| {kind} | {path} | {s['correct']} | {s['refused']} | "
                         f"{s['confidently wrong']} | {s['leaked']} |")
    incomplete = [r.id for r in rows if r.graph.incomplete]
    lines += [
        "",
        f"Graph answers that were right but could not give every outcome — because no "
        f"document or partner recorded it, and the answer did not supply one: "
        f"{', '.join(incomplete) or 'none'}.",
        "",
        "## Per question",
        "",
        "| id | persona | kind | graph | vector | note |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        note = "; ".join(x for x in (r.graph.note, r.vector.note) if x)
        lines.append(f"| {r.id} | {r.persona} | {r.kind} | {r.graph.outcome} | "
                     f"{r.vector.outcome} | {note.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def baseline(rows: list[Row]) -> dict:
    g = summary(rows, "graph")
    return {"graph_correct": g["correct"], "graph_leaked": g["leaked"],
            "questions": len(rows)}


def load_baseline(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None
