"""The lab's one entry point.

Every command is idempotent and every command says what it did. `tkg load` is the
whole pipeline: seed the systems of record, map them to the spine, add the facts
told by partners, validate against the shapes, and only then load. Validation
before loading is the point — a load that violates the contract does not land.

From M1, questions are asked *as someone*: `tkg ask --as sanne …` goes through the
resolver over HTTP with that persona's assertion, exactly as her MCP session does.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
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
from .semantic.templates import TEMPLATES

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
    """Seed, map, add told facts, validate against the shapes, and load. In that order."""
    cfg = _settings()
    config = _estate_config(cfg.config_dir)

    if not skip_seed:
        est = estate_mod.build(config, cfg.seed)
        counts = seed_db(cfg.db_admin_dsn, est)
        console.print("[green]1/5 seeded[/] " + " · ".join(f"{v} {k}" for k, v in counts.items()))

    spine = cfg.data_dir / "generated" / "spine.nq"
    n = materialize(cfg.sqlalchemy_url, cfg.mappings_dir, spine)
    console.print(f"[green]2/5 mapped[/] {n} quads from R2RML over the live database")

    told = cfg.data_dir / "generated" / "asserted.nq"
    facts = asserted_mod.load(cfg.config_dir / "asserted.yaml")
    try:
        n = asserted_mod.write(asserted_mod.build(facts), told)
    except asserted_mod.LineageError as exc:
        console.print(f"[red]3/5 told facts refused — nothing was loaded[/] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]3/5 told facts[/] {len(facts)} facts, {n} quads, each with its lineage")

    taxonomy_ttl = taxonomies.build_turtle(config)
    data = union_graph([spine, told], [taxonomy_ttl, cfg.ontology_dir / "firm.ttl"])
    result = validate(data, cfg.ontology_dir / "shapes.ttl", cfg.ontology_dir / "firm.ttl")
    if not result.conforms:
        console.print("[red]4/5 shapes failed — nothing was loaded[/]")
        console.print(Panel(result.report[:4000], title="SHACL report", border_style="red"))
        raise typer.Exit(1)
    console.print(f"[green]4/5 shapes passed[/] {result.triples} triples validated")

    fuseki = Fuseki(cfg.fuseki_url)
    push(fuseki, [spine, told], cfg.ontology_dir / "firm.ttl", taxonomy_ttl)
    table = Table(show_header=True, header_style="dim")
    table.add_column("named graph")
    table.add_column("triples", justify="right")
    for graph, count in fuseki.graphs():
        table.add_row(iri.shorten(graph), f"{count:,}")
    console.print(f"[green]5/5 loaded[/] {fuseki.count():,} triples")
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
        table.add_row(
            template.id,
            template.question,
            template.kind,
            ", ".join(s.name for s in template.slots) or "—",
        )
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
    if response.get("reason"):
        console.print(f"[{style}]{response['reason']}[/]")

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
    if response.get("permit"):
        console.print(f"[dim]permit minted for passages(), expires {response['permit_expires']}[/]")
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
) -> None:
    """Ask one competency question as a persona, through the resolver."""
    render(_client(as_).ask(template_id, _slots(set_)))


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


# The M1 scenes, in the order of the demo script: (persona, template, slots, caption).
DEMO = [
    ("mara", "CQ-02", {}, "Mara, partner: AFM investigations for Dutch fund managers since 2021"),
    ("sanne", "CQ-02", {}, "Sanne, screened by B-03: the identical question"),
    ("sanne", "CQ-06", {"matter": "M-2022-0117"}, "Sanne: who led M-2022-0117?"),
    ("sanne", "CQ-07", {}, "Sanne: who has the most AFM investigation experience? (aggregate)"),
    ("sanne", "CQ-08", {"person": "P-0101"},
     "Sanne: what expertise is recorded for Mara? (facts that name no matter)"),
    ("kim", "CQ-06", {"matter": "M-2023-0018"}, "Kim: a need-to-know matter she is not on"),
    ("percy-svc", "CQ-02", {}, "The firm's assistant, calling as itself"),
]


@app.command()
def demo() -> None:
    """Run the M1 scenes through the resolver, as the personas, and print the transcripts."""
    traces: dict[str, str] = {}
    console.rule("[bold]Who is asking")
    for persona in ("mara", "sanne"):
        me = _client(persona).whoami()
        console.print(f"[bold]{me['persona']}[/]  {me['principal']}  [dim]{me['about']}[/]")
    console.print()
    for persona, template_id, slots, caption in DEMO:
        console.rule(f"[bold]{caption}")
        response = _client(persona).ask(template_id, slots)
        render(response)
        traces[f"{persona}:{template_id}"] = response.get("trace", "")

    console.rule("[bold]Sanne asks why — answered from the stored record, not from memory")
    _explain_panel(_client("sanne").explain(traces["sanne:CQ-06"]))
    console.rule(
        "[dim]M1: every request above wrote one record to a hash-chained log — make verify-audit"
    )


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
