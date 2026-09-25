"""The lab's one entry point.

Every command is idempotent and every command says what it did. `tkg load` is the
whole pipeline: seed the systems of record, map them to the spine, add the facts
told by partners, validate against the shapes, and only then load. Validation
before loading is the point — a load that violates the contract does not land.

From M1, questions are asked *as someone*: `tkg ask --as sanne …` goes through the
resolver over HTTP with that persona's assertion, exactly as her MCP session does.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import iri, settings
from .client import ResolverClient
from .ingest import asserted as asserted_mod
from .ingest import estate as estate_mod
from .ingest import taxonomies
from .ingest.loader import Fuseki, push, union_graph, validate
from .ingest.mapper import materialize
from .ingest.seed import seed as seed_db
from .semantic import glossary as glossary_mod
from .semantic.templates import TEMPLATES, TERM_QUESTIONS

app = typer.Typer(add_completion=False, help="Trusted knowledge graph lab")
console = Console(width=int(os.environ.get("COLUMNS", "120")))


def _settings():
    return settings.load()


def _estate_config(cfg_dir: Path) -> dict:
    return estate_mod.load_config(cfg_dir / "estate.yaml")


def _client(persona: str) -> ResolverClient:
    cfg = _settings()
    return ResolverClient(cfg.resolver_url, cfg.secrets_dir, persona)


@app.command()
def doctor() -> None:
    """Check that every service is reachable."""
    cfg = _settings()
    ok = True

    import httpx
    import psycopg

    try:
        with psycopg.connect(cfg.db_dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pms.matter")
            matters = cur.fetchone()[0]
        console.print(f"[green]ok[/]   systems of record — reachable, {matters} matters")
    except Exception as exc:  # noqa: BLE001 - a doctor reports, it does not raise
        ok = False
        console.print(f"[red]fail[/] systems of record — {exc}")

    fuseki = Fuseki(cfg.fuseki_url)
    if fuseki.ping():
        console.print(f"[green]ok[/]   knowledge layer  — reachable, {fuseki.count()} triples")
    else:
        ok = False
        console.print(f"[red]fail[/] knowledge layer  — {cfg.fuseki_url} not answering")

    for name, url in (
        ("policy engine", f"{cfg.opa_url}/health"),
        ("resolver", f"{cfg.resolver_url}/healthz"),
    ):
        try:
            status = httpx.get(url, timeout=5).status_code
            good = status == 200
        except httpx.HTTPError as exc:
            good, status = False, exc
        ok = ok and good
        mark = "[green]ok[/]  " if good else "[red]fail[/]"
        console.print(f"{mark} {name:<16} — {status}")

    raise typer.Exit(0 if ok else 1)


@app.command()
def seed() -> None:
    """Generate the synthetic estate and write it to the systems of record."""
    cfg = _settings()
    config = _estate_config(cfg.config_dir)
    est = estate_mod.build(config, cfg.seed)
    counts = seed_db(cfg.db_admin_dsn, est)
    console.print(
        "[green]seeded[/] " + " · ".join(f"{v} {k}" for k, v in counts.items()) +
        f"  [dim](seed {cfg.seed} — deterministic)[/]"
    )


@app.command("map")
def map_cmd() -> None:
    """Run the R2RML mappings over the live database into N-Quads."""
    cfg = _settings()
    out = cfg.data_dir / "generated" / "spine.nq"
    n = materialize(cfg.sqlalchemy_url, cfg.mappings_dir, out)
    console.print(f"[green]mapped[/] {n} quads → {out}")


@app.command()
def load(skip_seed: bool = typer.Option(False, "--skip-seed")) -> None:
    """Seed, map, add told and extracted facts, validate, load; then documents and index."""
    from . import dms
    from .ingest import docgraph, pipeline
    from .ingest import extract as extract_mod

    cfg = _settings()
    config = _estate_config(cfg.config_dir)
    est = estate_mod.build(config, cfg.seed)

    def step(n: int, msg: str) -> None:
        console.print(f"[green]{n}/9[/] {msg}")

    if not skip_seed:
        counts = seed_db(cfg.db_admin_dsn, est)
        step(1, "seeded " + " · ".join(f"{v} {k}" for k, v in counts.items()))

    spine = cfg.data_dir / "generated" / "spine.nq"
    n = materialize(cfg.sqlalchemy_url, cfg.mappings_dir, spine)
    step(2, f"mapped {n} quads from R2RML over the live database")

    told = cfg.data_dir / "generated" / "asserted.nq"
    facts = asserted_mod.load(cfg.config_dir / "asserted.yaml")
    try:
        n = asserted_mod.write(asserted_mod.build(facts), told)
    except asserted_mod.LineageError as exc:
        console.print(f"[red]3/9 told facts refused — nothing was loaded[/] {exc}")
        raise typer.Exit(1) from exc
    step(3, f"told facts: {len(facts)} facts, {n} quads, each with its lineage")

    try:
        docs = pipeline.check_documents(est, config, cfg.seed, cfg.documents_path)
    except pipeline.StaleFixture as exc:
        console.print(f"[red]4/9 documents refused[/] {exc}")
        raise typer.Exit(1) from exc
    pdfs, texts = pipeline.render(docs, cfg.data_dir / "generated" / "pdf-text.jsonl")
    extraction = extract_mod.read(cfg.extraction_path)
    lookups = docgraph.Lookups.from_estate(est, config)
    doc_ds, stats = docgraph.doc_facts(docs, extraction, texts, lookups)
    extracted = cfg.data_dir / "generated" / "documents.nq"
    review_path = cfg.data_dir / "reviews" / "decisions.jsonl"
    review_rows = [json.loads(x) for x in review_path.read_text().splitlines()
                   if x.strip()] if review_path.exists() else []
    existing = {str(g.identifier) for g in doc_ds.graphs()} | {
        iri.asserted_graph(f["by"], str(f["told_on"])) for f in facts}
    review_ds, skipped = docgraph.reviews(review_rows, existing)
    lines = sorted(
        line for ds in (docgraph.dms_metadata(docs), doc_ds, review_ds)
        for line in ds.serialize(format="nquads").splitlines() if line.strip()
    )
    extracted.write_text("\n".join(lines) + "\n", encoding="utf-8")
    step(4, f"documents: {len(docs)} rendered to PDF and read back · "
         f"{len(extraction)} extracted · {stats.linked} facts linked, "
         f"{sum(stats.unlinked.values())} left unlinked · {len(review_rows)} review "
         f"decisions replayed{f', {skipped} skipped' if skipped else ''}")

    terms, mapping = glossary_mod.load_config(cfg.config_dir)
    glossary_ttl = glossary_mod.build_turtle(terms, mapping)
    sali = cfg.vocab_dir / "sali-lmss-subset.ttl"
    step(5, f"glossary: {len(terms['terms'])} terms, mapped to SALI LMSS @ "
         f"{mapping['source']['commit'][:7]}")

    taxonomy_ttl = taxonomies.build_turtle(config)
    quads = [spine, told, extracted]
    data = union_graph(quads, [taxonomy_ttl, glossary_ttl, sali, cfg.ontology_dir / "firm.ttl"])
    result = validate(data, cfg.ontology_dir / "shapes.ttl", cfg.ontology_dir / "firm.ttl")
    if not result.conforms:
        console.print("[red]6/9 shapes failed — nothing was loaded[/]")
        console.print(Panel(result.report[:4000], title="SHACL report", border_style="red"))
        raise typer.Exit(1)
    step(6, f"shapes passed: {result.triples} triples validated")

    fuseki = Fuseki(cfg.fuseki_url)
    push(fuseki, quads, cfg.ontology_dir / "firm.ttl", taxonomy_ttl, glossary_ttl, sali)
    step(7, f"loaded {fuseki.count():,} triples")

    store = dms.Store(cfg.minio_url, os.environ["MINIO_ROOT_USER"],
                      os.environ["MINIO_ROOT_PASSWORD"])
    step(8, f"document store: {pipeline.upload(store, docs, pdfs)} PDFs, keyed by matter")

    chunks, _ = pipeline.index(cfg.index_url, docs, texts, cfg.data_dir / "generated")
    step(9, f"index: {chunks} passages, BM25 and {384}-d embeddings, filterable by matter")

    table = Table(show_header=True, header_style="dim")
    table.add_column("named graph")
    table.add_column("triples", justify="right")
    graphs = fuseki.graphs()
    grouped: dict[str, list[int]] = {}
    for g, count in graphs:
        name = iri.shorten(g)
        for prefix in ("g:asserted/", "g:doc/"):
            if name.startswith(prefix):
                name = prefix + "…"
        grouped.setdefault(name, []).append(count)
    for name, counts in grouped.items():
        label = f"{name} ({len(counts)} graphs)" if name.endswith("…") else name
        table.add_row(label, f"{sum(counts):,}")
    console.print(table)


@app.command()
def documents() -> None:
    """Regenerate data/fixtures/documents.jsonl from the estate. Deterministic."""
    from .ingest import documents as documents_mod

    cfg = _settings()
    config = _estate_config(cfg.config_dir)
    docs = documents_mod.build(estate_mod.build(config, cfg.seed), config, cfg.seed)
    documents_mod.write(docs, cfg.documents_path)
    by_type: dict[str, int] = {}
    for d in docs:
        by_type[d.doc_type] = by_type.get(d.doc_type, 0) + 1
    console.print(f"[green]{len(docs)} documents[/] " +
                  " · ".join(f"{v} {k}" for k, v in sorted(by_type.items())) +
                  f" → {cfg.documents_path.relative_to(cfg.data_dir.parent)}")


@app.command()
def extract(
    limit: int = typer.Option(0, help="only the first N documents (0 = all)"),
    missing: bool = typer.Option(False, help="only documents not yet in the fixture"),
    resume: str = typer.Option("", help="collect an existing batch by id, not a new one"),
) -> None:
    """Run extraction through Claude (Batches API) and write the fixture. Needs a key."""
    import json as _json

    from . import dms
    from .ingest import documents as documents_mod
    from .ingest import extract as extract_mod

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY is not set.[/] Extraction regenerates "
                      "fixtures; the demo never needs it. Add it to .env on the host.")
        raise typer.Exit(2)
    cfg = _settings()
    config = _estate_config(cfg.config_dir)
    docs = documents_mod.read(cfg.documents_path)
    have = extract_mod.read(cfg.extraction_path)
    if missing:
        docs = [d for d in docs if d.doc_id not in have]
    if limit:
        docs = docs[:limit]
    if not docs and not resume:
        console.print("nothing to extract")
        return
    items = [] if resume else [(d.doc_id, d.matter, dms.pdf_text(dms.render_pdf(d)))
                               for d in docs]
    tmp = cfg.data_dir / "generated" / "extraction-batch.jsonl"
    usage = extract_mod.run_batch(items, config, tmp, lambda m: console.print(f"[dim]{m}[/]"),
                                  resume or None)
    merged = {**have, **extract_mod.read(tmp)}
    cfg.extraction_path.write_text(
        "\n".join(_json.dumps(merged[k], sort_keys=True, ensure_ascii=False)
                  for k in sorted(merged)) + "\n", encoding="utf-8")
    done = len(extract_mod.read(tmp))
    console.print(f"[green]extracted {done}[/] · tokens in {usage['input']:,} "
                  f"(cache reads {usage['cache_read']:,}) · out {usage['output']:,} · "
                  f"refused {usage['refused']} · errored {usage['errored']}")


@app.command("extraction-report")
def extraction_report() -> None:
    """reports/extraction.md — precision and recall against the generation manifest."""
    from .eval import extraction as score_mod
    from .ingest import docgraph, pipeline
    from .ingest import documents as documents_mod
    from .ingest import extract as extract_mod

    cfg = _settings()
    config = _estate_config(cfg.config_dir)
    est = estate_mod.build(config, cfg.seed)
    docs = documents_mod.read(cfg.documents_path)
    extraction = extract_mod.read(cfg.extraction_path)
    if not extraction:
        console.print("[yellow]no extraction fixture yet — run make extract[/]")
        raise typer.Exit(1)
    _, texts = pipeline.render(docs, cfg.data_dir / "generated" / "pdf-text.jsonl")
    result = score_mod.score(docs, extraction, texts, docgraph.Lookups.from_estate(est, config))
    model = next(iter(extraction.values()))["model"]
    refused = sum(1 for r in extraction.values() if r.get("status") == "refused")
    errored = sum(1 for r in extraction.values() if r.get("status") not in ("ok", "refused"))
    out = cfg.reports_dir / "extraction.md"
    out.write_text(score_mod.render(result, model, len(docs), refused, errored), encoding="utf-8")
    console.print("[green]→ reports/extraction.md[/]")


@app.command()
def naive(
    text: str = typer.Argument(..., help="a question, as someone would type it"),
    k: int = typer.Option(5),
) -> None:
    """The vector-only comparison: top-k over every passage, no access decision at all.

    Not part of the system — the thing the system is measured against. It is how a
    retrieval layer built by a service account over the whole corpus behaves.
    """
    from .index import Embedder, Index

    cfg = _settings()
    hits = Index(cfg.index_url).search(text, Embedder()([text])[0], None, k=k)
    table = Table(show_header=True, header_style="dim")
    for col in ("doc", "matter", "type", "score", "passage"):
        table.add_column(col)
    for h in hits:
        table.add_row(h["doc_id"], h["matter_id"], h["doc_type"], str(h["score"]),
                      h["text"][:160].replace("\n", " ") + "…")
    console.print(table)


@app.command()
def policy() -> None:
    """Compile barriers.yaml against the systems of record into the data OPA evaluates."""
    from .access import compile as compiler

    cfg = _settings()
    try:
        records = compiler.read_records(cfg.db_dsn)
        data = compiler.compile_files(cfg.config_dir, records)
    except compiler.PolicyError as exc:
        console.print("[red]policy refused — nothing was written[/]")
        for problem in exc.problems:
            console.print(f"  [red]✗[/] {problem}")
        raise typer.Exit(1) from exc
    out = cfg.build_dir / "opa" / "data.json"
    compiler.write(data, out)
    body = data["barriers"]

    # The second enforcement point, compiled from the same data.
    from . import dms

    people = yaml.safe_load((cfg.config_dir / "people.yaml").read_text())["personas"]
    policies = dms.compile_policies(data, people)
    dms.write_policies(policies, cfg.build_dir / "minio")
    secrets = {p["id"]: (cfg.secrets_dir / f"minio-{p['id']}.secret").read_text().strip()
               for p in people}
    try:
        dms.apply_policies(cfg.minio_url, os.environ["MINIO_ROOT_USER"],
                           os.environ["MINIO_ROOT_PASSWORD"], policies, secrets)
        applied = "applied to the document store"
    except Exception as exc:  # noqa: BLE001 - compile succeeds without a running store
        applied = f"[yellow]not applied ({type(exc).__name__}) — is minio up?[/]"
    console.print(f"[green]compiled[/] build/minio/<persona>.json · {len(policies)} "
                  f"document-store users · {applied}")
    table = Table(show_header=True, header_style="dim")
    for col in ("rule", "matter", "kind", "insiders", "screened", "owner", "set on"):
        table.add_column(col)
    for matter, rules in sorted(body["restrictions"].items()):
        for r in rules:
            s = r["screened"]
            screened = ", ".join(s["people"] + s["practice_areas"] + s["offices"]) or "—"
            table.add_row(
                r["rule"], matter, r["kind"], str(len(r["insiders"])), screened,
                r["owner"], r["set_on"],
            )
    console.print(
        f"[green]compiled[/] build/opa/data.json · policy {body['policy_version']} · "
        f"disclosure [bold]{body['disclosure']}[/]"
    )
    console.print(
        "[dim]every rule matched a restriction in the system of record, and "
        "every restriction has a rule[/]"
    )
    console.print(table)


@app.command()
def cq() -> None:
    """List the competency questions the graph is built to answer."""
    table = Table(show_header=True, header_style="dim")
    table.add_column("id")
    table.add_column("question")
    table.add_column("shape")
    table.add_column("slots")
    for template in TEMPLATES.values():
        if template.listed:
            table.add_row(
                template.id,
                template.question,
                template.kind,
                ", ".join(s.name for s in template.slots) or "—",
            )
    for q in TERM_QUESTIONS.values():
        table.add_row(q.id, q.question, f"term: {q.term}", "reading")
    console.print(table)


OUTCOME_STYLE = {
    "answered": "green",
    "answered-with-withheld": "yellow",
    "shown": "green",
}


def _rules_table(rules: list[dict]) -> Table:
    table = Table(show_header=True, header_style="dim", box=None, padding=(0, 2, 0, 0))
    for col in ("rule", "kind", "owner", "set on", "set by", "file"):
        table.add_column(col)
    for r in rules:
        table.add_row(
            r["rule"], r.get("kind", ""), r.get("owner", ""), r.get("set_on", ""),
            r.get("set_by", "") or "", r.get("source", ""),
        )
    return table


def render(response: dict, show_rows: int = 25) -> None:
    outcome = response.get("outcome", "?")
    style = OUTCOME_STYLE.get(outcome, "red")
    head = f"[bold]{response.get('persona', '')}[/]  {response.get('template', '')}"
    console.print(f"{head}  [{style}]{outcome}[/]  [dim]{response.get('trace', '')}[/]")
    if response.get("question"):
        console.print(f"[dim]{response['question']}[/]")
    if response.get("route"):
        r = response["route"]
        console.print(f"[dim]route {r['route']} — {r['reason']}[/]")
    for t in response.get("terms") or []:
        reading = f" · reading [bold]{t['reading']}[/]" if t.get("reading") else ""
        console.print(f"[dim]term[/] {t['term']}{reading} [dim]· owner {t['owner']}[/]")
    if response.get("reason"):
        console.print(f"[{style}]{response['reason']}[/]")
    if response.get("readings"):
        _readings_table(response["readings"])

    rows = response.get("rows") or []
    if rows:
        table = Table(show_header=True, header_style="dim")
        for column in response["columns"]:
            table.add_column({"g": "source", "fg": "told in"}.get(column, column))
        for row in rows[:show_rows]:
            table.add_row(*[row.get(c, "") for c in response["columns"]])
        console.print(table)
        if len(rows) > show_rows:
            console.print(f"[dim]… {len(rows) - show_rows} more rows[/]")
    elif outcome == "answered":
        console.print(
            "[yellow]The graph has no facts for this question.[/] "
            "That is an answer, and it is scored as one."
        )
    if response.get("scope"):
        console.print(f"[yellow]{response['scope']}[/]")

    explain_ = response.get("explain")
    if explain_:
        blocked = explain_.get("blocked")
        title = "explain()"
        if blocked:
            title += (
                f" · withheld {blocked['direct']} matter(s) directly, "
                f"{blocked['by_lineage']} derived fact(s) by lineage"
            )
        console.print(
            Panel(_rules_table(explain_.get("rules", [])), title=title,
                  border_style=style, expand=False)
        )
    for src in response.get("sources") or []:
        console.print(f"[dim]source[/] {src['document']} → [link={src['url']}]{src['key']}[/link] "
                      f"[dim](your credentials, until {src['expires']})[/]")
    passages = response.get("passages") or []
    if passages:
        table = Table(show_header=True, header_style="dim", title="passages, pre-filtered")
        for col in ("doc", "matter", "type", "passage"):
            table.add_column(col)
        for p in passages:
            body = p["text"].split("\n\n", 1)[-1] if "\n\n" in p["text"] else p["text"]
            table.add_row(p["doc_id"], p["matter_id"], p["doc_type"],
                          " ".join(body.split())[:140] + "…")
        console.print(table)
    if response.get("permit"):
        console.print(f"[dim]permit minted for passages(), expires {response['permit_expires']}[/]")
    console.print()


def _readings_table(readings: list[dict]) -> None:
    table = Table(show_header=True, header_style="dim")
    for col in ("reading", "owner", "definition", "count"):
        table.add_column(col)
    for r in readings:
        count = r.get("count")
        if count is None and r.get("outcome"):
            count = f"[red]{r['outcome']}[/]"
        elif r.get("scope"):
            count = f"{count} [yellow](what you can see)[/]"
        shown = str(count if count is not None else "—")
        table.add_row(r["key"], r["owner"], r["definition"], shown)
    console.print(table)


def render_term(response: dict) -> None:
    outcome = response.get("outcome")
    console.print(
        f"[bold]{response.get('persona', '')}[/]  resolve_term  "
        f"[green]{outcome}[/]  [dim]{response.get('trace', '')}[/]"
    )
    if outcome == "resolved":
        console.print(f"[bold]{response['label']}[/] — {response['definition']} "
                      f"[dim](owner: {response['owner']})[/]")
        if response.get("readings"):
            _readings_table(response["readings"])
            console.print(f"[dim]on_ambiguous: {response['on_ambiguous']} — a question that "
                          f"names it without choosing a reading is refused[/]")
        if response.get("means"):
            console.print("means " + " · ".join(f"{k} = {v}" for k, v in response["means"].items()))
    else:
        for c in response.get("concepts", []):
            maps = "; ".join(f"{m['relation']} {m['label'] or m['to']}" for m in c["mappings"])
            console.print(f"{c['concept']} [dim]{c['scheme'] or ''}[/] {maps}")
        console.print(f"[dim]{response.get('note') or response.get('reason', '')}[/]")
    console.print()


def _explain_panel(response: dict) -> None:
    blocked = response.get("blocked", {})
    console.print(
        Panel(
            _rules_table(response.get("rules", [])),
            title=f"explain({response.get('of_trace')}) · {response.get('decided')} · "
            f"{blocked.get('direct', 0)} direct, {blocked.get('by_lineage', 0)} by lineage",
            subtitle=response.get("source", ""),
            expand=False,
        )
    )


def _slots(set_: list[str] | None) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in set_ or []:
        if "=" not in item:
            console.print(f"[red]--set expects slot=value, got {item!r}[/]")
            raise typer.Exit(2)
        key, value = item.split("=", 1)
        params[key] = value
    return params


@app.command()
def ask(
    template_id: str = typer.Argument(..., help="A competency question id, e.g. CQ-02"),
    as_: str = typer.Option("mara", "--as", help="The persona asking"),
    set_: list[str] = typer.Option(None, "--set", "-s", help="slot=value, repeatable"),
    term: list[str] = typer.Option(None, "--term", "-t", help="glossary term id relied on"),
) -> None:
    """Ask one competency question as a persona, through the resolver."""
    render(_client(as_).ask(template_id, _slots(set_), term or []))


@app.command("term")
def term_cmd(
    text: str = typer.Argument(..., help='A business word, e.g. "active client"'),
    as_: str = typer.Option("mara", "--as", help="The persona asking"),
) -> None:
    """What a business word means here, who owns that, and — per reading — the count."""
    render_term(_client(as_).resolve_term(text))


audit_app = typer.Typer(help="The decision record, read as Risk & Compliance")
app.add_typer(audit_app, name="audit")


def _audit_render(response: dict) -> None:
    import json as _json

    if response.get("outcome") != "shown":
        render({**response, "template": "audit"})
        return
    body = {k: v for k, v in response.items() if k not in ("trace", "outcome")}
    console.print(f"[green]shown[/] [dim]{response['trace']} — this read is in the chain too[/]")
    console.print_json(_json.dumps(body))


@audit_app.command("subject")
def audit_subject(matter: str, as_: str = typer.Option("risk", "--as")) -> None:
    """Who has ever been shown anything derived from this matter?"""
    _audit_render(_client(as_).audit_subject(matter))


@audit_app.command("person")
def audit_person(
    person: str,
    since: str = typer.Option(None, help="ISO time"),
    until: str = typer.Option(None, help="ISO time"),
    as_: str = typer.Option("risk", "--as"),
) -> None:
    """What did this person see, between these times?"""
    _audit_render(_client(as_).audit_person(person, since, until))


@audit_app.command("trace")
def audit_trace(trace: str, as_: str = typer.Option("risk", "--as")) -> None:
    """Why was this trace decided as it was? The stored record, identifiers resolved."""
    _audit_render(_client(as_).audit_trace(trace))


@app.command()
def explain(
    trace: str = typer.Argument(...),
    as_: str = typer.Option(..., "--as", help="The persona who asked"),
) -> None:
    """Why a trace of yours was decided as it was — from the stored record."""
    response = _client(as_).explain(trace)
    if response.get("outcome") != "shown":
        render({**response, "persona": as_})
        raise typer.Exit(1)
    _explain_panel(response)


# The scenes, in the order of the demo script: (persona, template, slots, terms, caption).
DEMO = [
    ("mara", "CQ-02", {}, ["fund-manager", "afm-investigation"],
     "Scene 2 · Mara, partner: AFM investigations for Dutch fund managers since 2021"),
    ("sanne", "CQ-02", {}, ["fund-manager", "afm-investigation"],
     "Scene 4 · Sanne, screened by B-03: the identical question"),
    ("sanne", "CQ-06", {"matter": "M-2022-0117"}, [], "Scene 4 · Sanne: who led M-2022-0117?"),
    ("sanne", "CQ-07", {}, [],
     "Scene 4 · Sanne: who has the most AFM investigation experience? (aggregate)"),
    ("sanne", "CQ-08", {"person": "P-0101"}, [],
     "Scene 4 · Sanne: what expertise is recorded for Mara? (facts that name no matter)"),
    ("kim", "CQ-06", {"matter": "M-2023-0018"}, [], "Kim: a need-to-know matter she is not on"),
    ("percy-svc", "CQ-02", {}, [], "The firm's assistant, calling as itself"),
]


@app.command()
def demo() -> None:
    """Run the scenes through the resolver, as the personas, and print the transcripts."""
    from datetime import UTC, datetime

    from rich.markdown import Markdown

    from .eval.reports import audit_md

    started = datetime.now(UTC).isoformat(timespec="seconds")
    traces: dict[str, str] = {}
    console.rule("[bold]Scene 1 · Who is asking")
    for persona in ("mara", "sanne"):
        me = _client(persona).whoami()
        console.print(f"[bold]{me['persona']}[/]  {me['principal']}  [dim]{me['about']}[/]")
    console.print()
    for persona, template_id, slots, terms, caption in DEMO[:1]:
        console.rule(f"[bold]{caption}")
        render(_client(persona).ask(template_id, slots, terms))

    console.rule('[bold]Scene 3 · Why that was the right answer — resolve_term("active client")')
    render_term(_client("mara").resolve_term("active client"))
    console.rule("[bold]Scene 3 · …and a question that does not say which")
    render(_client("mara").ask("CQ-09", {}))
    render(_client("mara").ask("CQ-09", {"reading": "finance"}))

    for persona, template_id, slots, terms, caption in DEMO[1:]:
        console.rule(f"[bold]{caption}")
        response = _client(persona).ask(template_id, slots, terms)
        render(response)
        traces[f"{persona}:{template_id}"] = response.get("trace", "")

    console.rule("[bold]Sanne asks why — answered from the stored record, not from memory")
    _explain_panel(_client("sanne").explain(traces["sanne:CQ-06"]))

    console.rule("[bold]Scene 7 · The record — a third session, as Risk & Compliance")
    risk = _client("risk")
    refused = _client("sanne").audit_subject("M-2022-0117")
    console.print(
        f"[dim]sanne asks the record who saw M-2022-0117:[/] [red]{refused['outcome']}[/] "
        f"[dim]under {refused['explain']['rules'][0]['rule']} — and that attempt is recorded[/]"
    )
    subject = risk.audit_subject("M-2022-0117")
    person = risk.audit_person("sanne", since=started)
    trace = risk.audit_trace(traces["sanne:CQ-06"])
    console.print(Markdown(audit_md(subject, person, trace,
                                    [subject["trace"], person["trace"], trace["trace"]])))
    console.rule(
        "[dim]every request above wrote one record to a hash-chained log — make verify-audit"
    )


@app.command("glossary-report")
def glossary_report(as_: str = typer.Option("kim", "--as")) -> None:
    """reports/glossary.md — the terms, the readings with their counts, SALI, relations."""
    from .eval.reports import glossary_md

    cfg = _settings()
    active = _client(as_).resolve_term("active client")
    out = cfg.reports_dir / "glossary.md"
    out.write_text(glossary_md(active, cfg.config_dir, cfg.vocab_dir, as_), encoding="utf-8")
    console.print("[green]→ reports/glossary.md[/]")


@app.command("audit-report")
def audit_report() -> None:
    """reports/audit.md — the three questions, asked as Risk over the last demo run."""
    from .eval.reports import audit_md

    cfg = _settings()
    risk = _client("risk")
    subject = risk.audit_subject("M-2022-0117")
    person = risk.audit_person("sanne")
    refusals = [r for r in person.get("requests", [])
                if r["template"] == "CQ-06" and r["outcome"] == "refused"]
    trace = risk.audit_trace(refusals[-1]["trace"]) if refusals else None
    reads = [subject["trace"], person["trace"]] + ([trace["trace"]] if trace else [])
    out = cfg.reports_dir / "audit.md"
    out.write_text(audit_md(subject, person, trace, reads), encoding="utf-8")
    console.print("[green]→ reports/audit.md[/]")


review_app = typer.Typer(help="Confirm or reject facts — a decision with a name on it")
app.add_typer(review_app, name="review")


@review_app.command("list")
def review_list(matter: str, as_: str = typer.Option("kim", "--as")) -> None:
    """Facts on a matter that are extracted or unconfirmed, and await review."""
    render(_client(as_).ask("CQ-11", {"matter": matter}))


@review_app.command("confirm")
def review_confirm(fact: str, as_: str = typer.Option("kim", "--as")) -> None:
    """Confirm a fact. It becomes a review graph, derived from the fact's own."""
    render({**_client(as_).review(fact, "confirmed"), "persona": as_, "template": "review"})


@review_app.command("reject")
def review_reject(fact: str, as_: str = typer.Option("kim", "--as")) -> None:
    """Reject a fact. It stays in the graph for the record, and answers stop asserting it."""
    render({**_client(as_).review(fact, "rejected"), "persona": as_, "template": "review"})


@app.command("eval")
def eval_cmd(
    live: bool = typer.Option(False, help="compose and judge the vector path with Claude"),
    write_baseline: bool = typer.Option(False, "--baseline", help="record this run as the bar"),
) -> None:
    """Thirty questions, both paths → reports/eval.md. The graph path needs no model."""
    from .eval import battery

    cfg = _settings()
    if live and not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]--live needs ANTHROPIC_API_KEY in .env[/]")
        raise typer.Exit(2)
    rows = battery.run(cfg, console, live=live)
    (cfg.reports_dir / "eval.md").write_text(battery.render(rows), encoding="utf-8")
    base = battery.baseline(rows)
    if write_baseline:
        (cfg.reports_dir / "baseline.json").write_text(json.dumps(base, indent=2) + "\n")
    g, v = battery.summary(rows, "graph"), battery.summary(rows, "vector")
    console.print(f"[bold]graph[/]  correct {g['correct']} · refused {g['refused']} · "
                  f"wrong {g['confidently wrong']} · [bold]leaked {g['leaked']}[/]")
    console.print(f"[bold]vector[/] correct {v['correct']} · refused {v['refused']} · "
                  f"wrong {v['confidently wrong']} · [bold]leaked {v['leaked']}[/] · "
                  f"not run {v['not run'] + v['stale']}")
    console.print("[dim]→ reports/eval.md[/]")


@app.command()
def gate() -> None:
    """The deploy gate with no CI behind it: every check, non-zero on any failure."""
    from .access import compile as compiler
    from .audit.chain import verify
    from .eval import battery
    from .eval import leak as leak_mod

    cfg = _settings()
    checks: list[tuple[str, bool, str]] = []

    fresh = compiler.compile_files(cfg.config_dir, compiler.read_records(cfg.db_dsn))
    committed = json.loads((cfg.build_dir / "opa" / "data.json").read_text())
    checks.append(("compiled policy matches barriers.yaml and the systems of record",
                   fresh == committed, "" if fresh == committed else "run make policy"))

    result = leak_mod.run(cfg, console)
    (cfg.reports_dir / "leak.md").write_text(leak_mod.render(result), encoding="utf-8")
    checks.append(("barrier suite: zero leaks, zero wrong refusals, doors hold",
                   not result.leaks and not result.problems
                   and all(ok for *_, ok in result.doors), ""))
    checks.append(("OPA and the document store agree on every persona and document",
                   not result.store.disagreements,
                   f"{len(result.store.disagreements)} disagreements"))
    checks.append(("stolen document ids yield nothing",
                   result.store.stolen_refused == result.store.stolen_attempts, ""))
    checks.append(("no denied identifier in clear in the decision record",
                   not result.audit_leaks, ""))

    rows = battery.run(cfg, console)
    (cfg.reports_dir / "eval.md").write_text(battery.render(rows), encoding="utf-8")
    now = battery.baseline(rows)
    base = battery.load_baseline(cfg.reports_dir / "baseline.json")
    checks.append(("eval: the graph path leaks nothing", now["graph_leaked"] == 0, ""))
    checks.append(("eval: graph-path correct at or above the baseline",
                   base is not None and now["graph_correct"] >= base["graph_correct"],
                   f"{now['graph_correct']} vs baseline "
                   f"{base['graph_correct'] if base else '— none recorded'}"))

    chain = verify(cfg.audit_path)
    checks.append(("the decision record's hash chain is intact", chain.ok,
                   f"{chain.records} records · head {chain.head[:16]}…"))

    console.rule("[bold]make gate")
    for name, ok, detail in checks:
        mark = "[green]pass[/]" if ok else "[red]FAIL[/]"
        console.print(f"{mark}  {name}  [dim]{detail}[/]")
    console.print("[dim]not checked: OPA's own decision log as a second stream — cut, "
                  "docs/decisions/0024[/]")
    raise typer.Exit(0 if all(ok for _, ok, _ in checks) else 1)


@app.command("verify-audit")
def verify_audit() -> None:
    """Recompute the decision record's hash chain and name the first broken record."""
    from .audit.chain import verify

    cfg = _settings()
    result = verify(cfg.audit_path)
    if result.ok:
        console.print(f"[green]chain intact[/] {result.records} records · head {result.head}")
        console.print(
            "[dim]Hold the head hash somewhere else: a chain cannot show that its tail "
            "was cut. docs/decisions/0012[/]"
        )
        return
    console.print(
        f"[red]chain broken at line {result.broken_at}[/] — {result.reason}. "
        f"{result.records} records before it verify."
    )
    raise typer.Exit(1)


@app.command()
def leak() -> None:
    """The barrier suite: every rule, every persona, direct / second hop / aggregate / lineage."""
    from .eval import leak as leak_mod

    cfg = _settings()
    result = leak_mod.run(cfg, console)
    out = cfg.reports_dir / "leak.md"
    out.write_text(leak_mod.render(result), encoding="utf-8")
    console.print("[dim]→ reports/leak.md[/]")
    raise typer.Exit(0 if result.passed else 1)


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
