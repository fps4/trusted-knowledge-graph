"""The lab's one entry point.

Every command is idempotent and every command says what it did. `tkg load` is the
whole pipeline: seed the systems of record, map them to the spine, validate
against the shapes, and only then load. Validation before loading is the point —
a load that violates the contract does not land.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from . import iri, settings
from .ingest import estate as estate_mod
from .ingest import taxonomies
from .ingest.loader import Fuseki, push, union_graph, validate
from .ingest.mapper import materialize
from .ingest.seed import seed as seed_db
from .resolver.engine import Resolver
from .semantic.templates import TEMPLATES

app = typer.Typer(add_completion=False, help="Trusted knowledge graph lab")
console = Console()


def _settings():
    return settings.load()


def _estate_config(cfg_dir: Path) -> dict:
    return estate_mod.load_config(cfg_dir / "estate.yaml")


@app.command()
def doctor() -> None:
    """Check that the systems of record and the knowledge layer are reachable."""
    cfg = _settings()
    ok = True

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
    """Seed, map, validate against the shapes, and load. In that order."""
    cfg = _settings()
    config = _estate_config(cfg.config_dir)

    if not skip_seed:
        est = estate_mod.build(config, cfg.seed)
        counts = seed_db(cfg.db_admin_dsn, est)
        console.print("[green]1/4 seeded[/] " + " · ".join(f"{v} {k}" for k, v in counts.items()))

    quads = cfg.data_dir / "generated" / "spine.nq"
    n = materialize(cfg.sqlalchemy_url, cfg.mappings_dir, quads)
    console.print(f"[green]2/4 mapped[/] {n} quads from R2RML over the live database")

    taxonomy_ttl = taxonomies.build_turtle(config)
    data = union_graph(quads, [taxonomy_ttl, cfg.ontology_dir / "firm.ttl"])
    result = validate(data, cfg.ontology_dir / "shapes.ttl", cfg.ontology_dir / "firm.ttl")
    if not result.conforms:
        console.print("[red]3/4 shapes failed — nothing was loaded[/]")
        console.print(Panel(result.report[:4000], title="SHACL report", border_style="red"))
        raise typer.Exit(1)
    console.print(f"[green]3/4 shapes passed[/] {result.triples} triples validated")

    fuseki = Fuseki(cfg.fuseki_url)
    push(fuseki, quads, cfg.ontology_dir / "firm.ttl", taxonomy_ttl)
    table = Table(show_header=True, header_style="dim")
    table.add_column("named graph")
    table.add_column("triples", justify="right")
    for graph, n in fuseki.graphs():
        table.add_row(iri.shorten(graph), f"{n:,}")
    console.print(f"[green]4/4 loaded[/] {fuseki.count():,} triples")
    console.print(table)


@app.command()
def cq() -> None:
    """List the competency questions the graph is built to answer."""
    table = Table(show_header=True, header_style="dim")
    table.add_column("id")
    table.add_column("question")
    table.add_column("slots")
    for template in TEMPLATES.values():
        table.add_row(
            template.id,
            template.question,
            ", ".join(s.name for s in template.slots) or "—",
        )
    console.print(table)


def _render(answer, show_query: bool) -> None:
    console.print(f"[bold]{answer.template.id}[/]  {answer.template.question}")
    if answer.slots:
        shown = " · ".join(f"{k}={iri.shorten(v)}" for k, v in answer.slots.items())
        console.print(f"[dim]slots  {shown}[/]")
    if show_query:
        console.print(Syntax(answer.bound_query.strip(), "sparql", theme="ansi_dark"))
    if not answer.rows:
        console.print(
            "[yellow]The graph has no facts for this question.[/] "
            "That is an answer, and it is scored as one.\n"
        )
        return
    table = Table(show_header=True, header_style="dim")
    for column in answer.template.columns:
        table.add_column("source graph" if column == "g" else column)
    for row in answer.rows[:25]:
        table.add_row(*[row.get(c, "") for c in answer.template.columns])
    console.print(table)
    if len(answer.rows) > 25:
        console.print(f"[dim]… {len(answer.rows) - 25} more rows[/]")
    if answer.template.note:
        console.print(f"[dim]{answer.template.note}[/]")
    console.print()


@app.command()
def ask(
    template_id: str = typer.Argument(..., help="A competency question id, e.g. CQ-02"),
    set_: list[str] = typer.Option(None, "--set", "-s", help="slot=value, repeatable"),
    show_query: bool = typer.Option(True, "--query/--no-query"),
) -> None:
    """Answer one competency question, with the query that produced it."""
    cfg = _settings()
    params: dict[str, str] = {}
    for item in set_ or []:
        if "=" not in item:
            console.print(f"[red]--set expects slot=value, got {item!r}[/]")
            raise typer.Exit(2)
        key, value = item.split("=", 1)
        params[key] = value
    resolver = Resolver(Fuseki(cfg.fuseki_url))
    try:
        answer = resolver.ask(template_id, params)
    except (KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    _render(answer, show_query)


@app.command()
def demo() -> None:
    """Run every competency question. This is what `make demo` shows."""
    cfg = _settings()
    resolver = Resolver(Fuseki(cfg.fuseki_url))
    console.rule("[bold]Answered from the spine alone — no documents, no extraction")
    for template_id in TEMPLATES:
        answer = resolver.ask(template_id)
        _render(answer, show_query=(template_id == "CQ-02"))
    console.rule(
        "[dim]M0: every fact above came from a system of record, and says which one"
    )


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
