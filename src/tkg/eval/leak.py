"""The barrier suite. The thing to put on a screen.

For every rule, every persona is asked the questions whose correct answer depends
on the restricted matter — directly, one hop away, as an aggregate, and through
facts that were derived from it and name no matter at all. Any response that
carries a denied identifier is a leak. Any response that withholds a matter the
persona may see is an over-refusal: a suite that passes because nothing is ever
answered is not a test.

Who *should* be denied is computed here, in Python, from barriers.yaml, the
systems of record and the told facts — a second implementation that bypasses both
the compiler and OPA. The suite checks the resolver against it, so it checks the
compiled data and the Rego too. (An earlier version read the compiled data.json;
a deliberately tampered policy then passed, because it agreed with itself.)

Questions go through the resolver's HTTP API, as each persona — the same path an
MCP session uses. Claude itself is not in the suite: it is not deterministic, and
the boundary it sits behind is.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import dict_row

from .. import iri
from ..audit.chain import read, verify
from ..client import ResolverClient
from ..ingest import asserted as asserted_mod

PERSONAS = ("mara", "sanne", "kim")
REFUSED_IDENTITIES = {"percy-svc": "ID-02", "risk": "ID-03"}
IGNORED_FIELDS = {"slots", "question", "note", "trace", "permit", "permit_expires"}


@dataclass
class Case:
    rule: str
    matter: str
    persona: str
    shape: str
    template: str
    slots: dict
    denied: bool
    outcome: str = ""
    rows: int = 0
    leaked: list[str] = field(default_factory=list)
    problem: str = ""
    trace: str = ""


@dataclass
class Result:
    disclosure: str
    cases: list[Case]
    doors: list[tuple[str, str, bool]]
    audit_records: int = 0
    audit_leaks: list[str] = field(default_factory=list)
    chain_ok: bool = False

    @property
    def leaks(self) -> list[Case]:
        return [c for c in self.cases if c.leaked]

    @property
    def problems(self) -> list[Case]:
        return [c for c in self.cases if c.problem]

    @property
    def passed(self) -> bool:
        return (
            not self.leaks
            and not self.problems
            and all(ok for *_, ok in self.doors)
            and not self.audit_leaks
            and self.chain_ok
        )


# ── the expected answer, computed independently of OPA and of the compiler ──
# From barriers.yaml and the systems of record directly. Reading the compiled
# data.json here would check that OPA evaluates it, not that it is right — a
# tampered or mis-compiled policy would agree with itself and pass.
def expected_denials(barriers: dict, persona: dict, records) -> set[str]:
    hr = records.people.get(persona.get("person_ref") or "", {})
    person = persona.get("person_ref")
    denied = set()
    for rule in barriers["rules"]:
        insiders = set((rule.get("insiders") or {}).get("people") or [])
        if (rule.get("insiders") or {}).get("matter_team"):
            insiders |= records.teams.get(rule["matter"], set())
        s = rule.get("screened") or {}
        inside = person in insiders
        screened = (
            person in (s.get("people") or [])
            or hr.get("practice_area") in (s.get("practice_areas") or [])
            or hr.get("office") in (s.get("offices") or [])
        )
        if (rule["kind"] == "need-to-know" and not inside) or (
            rule["kind"] == "barrier" and screened and not inside
        ):
            denied.add(rule["matter"])
    return denied


def derived_closure(facts: list[dict], denied: set[str]) -> set[str]:
    """Told graphs whose lineage reaches a denied matter, transitively."""
    graph_of = {f["id"]: iri.asserted_graph(f["by"], str(f["told_on"])) for f in facts}
    sources = {graph_of[f["id"]]: f["derived_from"] for f in facts}

    def reaches(graph: str, seen: frozenset = frozenset()) -> bool:
        for src in sources.get(graph, []):
            kind, _, rest = src.partition("/")
            if kind == "matter" and rest in denied:
                return True
            if kind == "asserted":
                parent = iri.G_ASSERTED + rest
                if parent not in seen and reaches(parent, seen | {graph}):
                    return True
        return False

    return {g for g in sources if reaches(g)}


def _tokens(denied: set[str], graphs: set[str]) -> list[str]:
    out = sorted(denied)
    for g in sorted(graphs):
        out += [g, iri.shorten(g)]
    return out


def _scan(response: dict, tokens: list[str]) -> list[str]:
    visible = {k: v for k, v in response.items() if k not in IGNORED_FIELDS}
    text = json.dumps(visible)
    permit = response.get("permit")
    if permit:  # what the permit would unlock is part of what was granted
        body = permit.split(".")[1]
        text += base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
    return [t for t in tokens if t in text]


def _matters(dsn: str, refs: list[str]) -> dict[str, dict]:
    with psycopg.connect(dsn, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT m.matter_ref, m.client_ref, m.matter_type, m.jurisdiction, m.office,"
            " m.lead_person_ref, m.opened_on, c.client_type"
            " FROM pms.matter m JOIN pms.client c USING (client_ref)"
            " WHERE m.matter_ref = ANY(%s)",
            (refs,),
        )
        return {row["matter_ref"]: row for row in cur.fetchall()}


def _questions(m: dict) -> list[tuple[str, str, dict]]:
    since = m["opened_on"].isoformat()
    return [
        ("direct", "CQ-06", {"matter": m["matter_ref"]}),
        ("second hop", "CQ-01", {"client": m["client_ref"]}),
        ("second hop", "CQ-03", {"client": m["client_ref"]}),
        ("lineage", "CQ-02", {
            "client_type": f"gl:client-type/{m['client_type']}",
            "matter_type": f"gl:matter-type/{m['matter_type']}",
            "jurisdiction": f"id:jurisdiction/{m['jurisdiction']}",
            "since": since,
        }),
        ("lineage", "CQ-08", {"person": m["lead_person_ref"]}),
        ("aggregate", "CQ-07", {
            "matter_type": f"gl:matter-type/{m['matter_type']}",
            "jurisdiction": f"id:jurisdiction/{m['jurisdiction']}",
            "since": since,
        }),
        ("aggregate", "CQ-05", {"office": f"id:office/{m['office']}"}),
    ]


def _judge(case: Case, response: dict, disclosure: str, tokens: list[str]) -> None:
    case.outcome = response.get("outcome", "?")
    case.rows = len(response.get("rows") or [])
    case.trace = response.get("trace", "")
    case.leaked = _scan(response, tokens)
    refused = case.outcome.startswith("refused")
    if case.denied and case.shape == "aggregate":
        if disclosure == "withheld-count" and case.outcome != "refused-aggregate":
            case.problem = "an aggregate over a restricted set was not refused"
        if disclosure == "silent" and not response.get("scope"):
            case.problem = "a partial aggregate was not labelled as partial"
    if case.denied and case.shape == "direct" and case.rows:
        case.problem = "a direct question about a denied matter returned rows"
    if not case.denied and case.shape == "direct":
        refs = {r.get("matterRef") for r in response.get("rows") or []}
        if refused or case.matter not in refs:
            case.problem = "over-refusal: a matter this persona may see was withheld"


def run(cfg, console) -> Result:
    import yaml

    from ..access.compile import read_records

    barriers = yaml.safe_load((cfg.config_dir / "barriers.yaml").read_text())
    personas = {
        p["id"]: p for p in yaml.safe_load((cfg.config_dir / "people.yaml").read_text())["personas"]
    }
    facts = asserted_mod.load(cfg.config_dir / "asserted.yaml")
    records = read_records(cfg.db_dsn)
    disclosure = barriers["disclosure"]
    rules = sorted((r["id"], r["matter"]) for r in barriers["rules"])
    attrs = _matters(cfg.db_dsn, [m for _, m in rules])

    denials = {p: expected_denials(barriers, personas[p], records) for p in PERSONAS}
    tokens = {p: _tokens(denials[p], derived_closure(facts, denials[p])) for p in PERSONAS}
    clients = {p: ResolverClient(cfg.resolver_url, cfg.secrets_dir, p) for p in personas}

    cases: list[Case] = []
    for rule, matter in rules:
        for persona in PERSONAS:
            for shape, template, slots in _questions(attrs[matter]):
                case = Case(rule, matter, persona, shape, template, slots,
                            denied=matter in denials[persona])
                _judge(case, clients[persona].ask(template, slots), disclosure, tokens[persona])
                cases.append(case)
    # Identities that must see nothing, whatever they ask.
    for persona, rule_id in REFUSED_IDENTITIES.items():
        for template, slots in (("CQ-02", {}), ("CQ-06", {"matter": "M-2021-0043"})):
            case = Case(rule_id, "—", persona, "identity", template, slots, denied=True)
            response = clients[persona].ask(template, slots)
            case.outcome, case.trace = response.get("outcome", "?"), response.get("trace", "")
            case.rows = len(response.get("rows") or [])
            rules_seen = [r["rule"] for r in (response.get("explain") or {}).get("rules", [])]
            if case.outcome != "refused" or case.rows or rule_id not in rules_seen:
                case.problem = f"expected a refusal under {rule_id}"
            cases.append(case)

    # The permit is the lock on the one door the tool surface itself opens.
    mara = clients["mara"].ask("CQ-01", {"client": "C-0042"})
    sanne = clients["sanne"].ask("CQ-01", {"client": "C-0042"})
    doors = [
        ("passages() with no permit", clients["sanne"].passages("not-a-permit")["outcome"],
         False),
        ("passages() with another person's permit",
         clients["sanne"].passages(mara.get("permit", ""))["outcome"], False),
        ("passages() with your own permit",
         clients["sanne"].passages(sanne.get("permit", ""))["outcome"], True),
    ]
    doors = [
        (name, outcome, (outcome == "no-index") == should_open)
        for name, outcome, should_open in doors
    ]

    # What a session is told about itself is a response too. (The first Claude Code
    # run found this one: a persona's description named the matter she is screened
    # from, and whoami() repeated it.)
    for persona in PERSONAS:
        case = Case("—", "—", persona, "session", "whoami", {}, denied=False)
        me = clients[persona].whoami()
        case.outcome = "shown"
        case.leaked = _scan(me, tokens[persona]) + _scan(
            {"t": clients[persona].templates()}, tokens[persona]
        )
        cases.append(case)

    result = Result(disclosure=disclosure, cases=cases, doors=doors)

    # The record of all that must not leak what the barriers hide.
    traces = {c.trace: c.persona for c in cases if c.trace}
    all_tokens = {**tokens, **{p: [] for p in REFUSED_IDENTITIES}}
    for record in read(cfg.audit_path):
        persona = traces.get(record.get("trace"))
        if persona is None:
            continue
        result.audit_records += 1
        line = json.dumps(record)
        for token in all_tokens.get(persona, []):
            if token in line:
                result.audit_leaks.append(f"{record['trace']} ({persona}): {token}")
    result.chain_ok = verify(cfg.audit_path).ok

    console.print(
        f"[bold]{len(cases)} questions[/] · {len(result.leaks)} leaked · "
        f"{len(result.problems)} wrong refusals · doors "
        f"{sum(ok for *_, ok in doors)}/{len(doors)} · audit records checked "
        f"{result.audit_records}, clear-text denied identifiers {len(result.audit_leaks)} · "
        f"chain {'intact' if result.chain_ok else 'BROKEN'}"
    )
    for c in result.leaks + result.problems:
        console.print(f"  [red]✗[/] {c.rule} {c.persona} {c.template} {c.slots}: "
                      f"{c.problem or 'leaked ' + ', '.join(c.leaked)}")
    for line in result.audit_leaks:
        console.print(f"  [red]✗ audit[/] {line}")
    console.print("[green]zero leaks[/]" if result.passed else "[red]FAILED[/]")
    return result


def render(result: Result) -> str:
    cases = [c for c in result.cases if c.shape not in ("identity", "session")]
    denied = [c for c in cases if c.denied]
    lines = [
        "# Barrier suite",
        "",
        "Generated by `make leak`. Every rule in `config/barriers.yaml`, every persona, the",
        "questions whose correct answer depends on the restricted matter. Asked through the",
        "resolver's HTTP API as each persona — the same path an MCP session uses. Who *should*",
        "be denied is computed from `barriers.yaml` and the systems of record directly,",
        "bypassing both the policy compiler and the policy engine.",
        "",
        "Claude is not in this suite: it is not deterministic, and the boundary it sits",
        "behind is. The estate is synthetic.",
        "",
        "| | |",
        "|---|---|",
        f"| disclosure policy | `{result.disclosure}` |",
        f"| questions asked | {len(result.cases)} |",
        f"| … where the persona is denied the matter | {len(denied)} |",
        f"| **leaked** | **{len(result.leaks)}** |",
        f"| wrong refusals (including over-refusals) | {len(result.problems)} |",
        f"| permit doors behaving | {sum(ok for *_, ok in result.doors)} / {len(result.doors)} |",
        f"| audit records checked for clear-text denied identifiers | {result.audit_records} |",
        f"| … found | {len(result.audit_leaks)} |",
        f"| hash chain | {'intact' if result.chain_ok else 'BROKEN'} |",
        "",
        "## By rule and persona",
        "",
        "| rule | matter | persona | may see it | direct | second hop | lineage | aggregate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple, list[Case]] = {}
    for c in cases:
        groups.setdefault((c.rule, c.matter, c.persona), []).append(c)

    def cell(cs: list[Case]) -> str:
        return " · ".join(
            f"{c.template} {c.outcome}{' ✗' if c.leaked or c.problem else ''}" for c in cs
        )

    for (rule, matter, persona), cs in groups.items():
        by = {s: [c for c in cs if c.shape == s] for s in ("direct", "second hop", "lineage",
                                                            "aggregate")}
        lines.append(
            f"| {rule} | {matter} | {persona} | {'no' if cs[0].denied else 'yes'} | "
            + " | ".join(cell(by[s]) for s in ("direct", "second hop", "lineage", "aggregate"))
            + " |"
        )
    lines += ["", "## Identities that must see nothing", "", "| persona | question | outcome |",
              "|---|---|---|"]
    for c in result.cases:
        if c.shape == "identity":
            lines.append(f"| {c.persona} | {c.template} | {c.outcome}"
                         f"{' ✗ ' + c.problem if c.problem else ''} |")
    lines += ["", "## What each session is told about itself", "",
              "`whoami()` and `questions()`, scanned like any other response.", "",
              "| persona | leaked |", "|---|---|"]
    for c in result.cases:
        if c.shape == "session":
            lines.append(f"| {c.persona} | {', '.join(c.leaked) or 'nothing'} |")
    lines += ["", "## The permit", "", "| attempt | outcome | as it should be |", "|---|---|---|"]
    for name, outcome, ok in result.doors:
        lines.append(f"| {name} | {outcome} | {'yes' if ok else '**no**'} |")
    lines += [
        "",
        "`answered-with-withheld` means rows came back and the persona was told how many were",
        "withheld, and under which rule — the `withheld-count` policy. A leak is any denied",
        "matter or derived graph appearing anywhere in the response, including inside the permit.",
        "",
    ]
    return "\n".join(lines)
