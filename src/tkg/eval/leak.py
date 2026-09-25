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

A document that cites a matter is walled wherever that matter is (ADR 0028). What
a document cites is read from the manifest — the ground truth — not from the
extraction the graph was built from, so a citation extraction missed shows here as
a leak, not as a pass.
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
class StoreCheck:
    """The second enforcement point, checked against the first on every document.

    Where a document cites nothing, the graph and the store must agree exactly.
    Where it cites a matter, the graph may be stricter than the store — the DMS does
    not know what a document cites — but never broader. `disagreements` fail the
    gate; `weaker` is a finding about the DMS, not a failure of the design."""

    checks: int = 0
    disagreements: list[str] = field(default_factory=list)
    weaker: list[str] = field(default_factory=list)
    weaker_docs: set[str] = field(default_factory=set)
    citing_docs: int = 0
    stolen_attempts: int = 0
    stolen_refused: int = 0


# The comparison, three ways. None of them is the resolver asking the graph; they
# are the index asked directly with the filter each approach would put on it.
VARIANTS = {
    "none": "no filter — a retrieval layer built by a service account",
    "doc-acl": "document-level ACL — the passage's own matter, as a DMS-synced ACL does",
    "lineage": "every matter the passage depends on — the resolver's filter",
}


@dataclass
class VariantCheck:
    questions: int = 0
    leaked_questions: int = 0
    leaked_passages: int = 0
    via_citation: int = 0  # leaked passages whose own matter the persona may see
    examples: list[str] = field(default_factory=list)


@dataclass
class NaiveCheck:
    """The comparison: the same questions, top-k over the index, three filters."""

    variants: dict[str, VariantCheck] = field(
        default_factory=lambda: {v: VariantCheck() for v in VARIANTS})

    # The unfiltered numbers, under the names the report and the README used before.
    @property
    def questions(self) -> int:
        return self.variants["none"].questions

    @property
    def leaked_questions(self) -> int:
        return self.variants["none"].leaked_questions

    @property
    def leaked_passages(self) -> int:
        return self.variants["none"].leaked_passages

    @property
    def examples(self) -> list[str]:
        return self.variants["none"].examples


@dataclass
class Result:
    disclosure: str
    cases: list[Case]
    doors: list[tuple[str, str, bool]]
    audit_records: int = 0
    audit_leaks: list[str] = field(default_factory=list)
    chain_ok: bool = False
    store: StoreCheck = field(default_factory=StoreCheck)
    naive: NaiveCheck = field(default_factory=NaiveCheck)

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
            and not self.store.disagreements
            and self.store.stolen_attempts == self.store.stolen_refused
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


def _tokens(denied: set[str], graphs: set[str], docs: set[str] = frozenset()) -> list[str]:
    out = sorted(denied)
    for g in sorted(graphs):
        out += [g, iri.shorten(g)]
    for d in sorted(docs):
        out += [d, iri.shorten(iri.doc_graph(d))]
    return out


def doc_matters(docs) -> dict[str, set[str]]:
    """Every matter a document depends on, per the manifest: its own and what it cites."""
    from ..ingest.documents import cited_matters

    return {d.doc_id: {d.matter, *cited_matters(d)} for d in docs}


def walled_documents(matters_of: dict[str, set[str]], denied: set[str]) -> set[str]:
    """Documents a person may not see: on a denied matter, or citing one."""
    return {doc for doc, ms in matters_of.items() if ms & denied}


def graph_is_broader(cites: bool, graph_allows: bool, store_opens: bool) -> str | None:
    """The agreement rule between the graph and the store, for one person and document.

    'disagree' fails the gate; 'weaker' is the finding that the DMS opens what the
    graph withholds, on a document that cites a walled matter. None: as it should be."""
    if graph_allows == store_opens:
        return None
    if cites and not graph_allows and store_opens:
        return "weaker"
    return "disagree"


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
            " m.lead_person_ref, m.opened_on, c.client_type, c.name AS client_name"
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
        ("direct", "CQ-10", {"matter": m["matter_ref"]}),
    ]


def _store_check(cfg, personas: dict, denials: dict) -> StoreCheck:
    """The graph and the document store, on every persona and every document — and a
    document id obtained some other way must yield nothing to someone denied.

    What the graph decides for a document is its matter's decision *and* its
    extracted graph's, by lineage — so a note citing a walled matter is withheld
    by the graph while the store, which does not know what it cites, opens it."""
    import httpx
    from minio.error import S3Error

    from ..access.decide import lineage
    from ..dms import BUCKET, Store
    from ..ingest import documents as documents_mod
    from ..ingest.loader import Fuseki

    docs = documents_mod.read(cfg.documents_path)
    matters = sorted({d.matter for d in docs})
    found = lineage(Fuseki(cfg.fuseki_url), [iri.doc_graph(d.doc_id) for d in docs])
    lineage_map = {g: ms for g, ms in found.items() if ms}
    check = StoreCheck()
    citing = {d.doc_id for d in docs
              if set(lineage_map.get(iri.doc_graph(d.doc_id), [])) - {d.matter}}
    check.citing_docs = len(citing)
    for pid, p in personas.items():
        decision = httpx.post(f"{cfg.opa_url}/v1/data/tkg/access/decision", json={"input": {
            "principal": p["principal"], "matters": matters, "lineage": lineage_map}},
            timeout=60).json()["result"]
        allowed = {m for m, d in decision["matters"].items() if d["allow"]}
        graphs = decision.get("graphs", {})
        secret = (cfg.secrets_dir / f"minio-{pid}.secret").read_text().strip()
        store = Store(cfg.minio_url, pid, secret)
        for d in docs:
            key = f"doc/{d.matter}/{d.doc_id}.pdf"
            try:
                store.client.stat_object(BUCKET, key)
                opened = True
            except S3Error:
                opened = False
            check.checks += 1
            g = iri.doc_graph(d.doc_id)
            allows = d.matter in allowed and graphs.get(g, {"allow": True})["allow"]
            verdict = graph_is_broader(d.doc_id in citing, allows, opened)
            if verdict == "weaker":
                check.weaker.append(f"{pid} {key}")
                check.weaker_docs.add(d.doc_id)
            elif verdict == "disagree":
                check.disagreements.append(
                    f"{pid} {key}: graph={'allow' if allows else 'deny'} "
                    f"store={'open' if opened else 'refused'}"
                )
            if pid in denials and d.matter in denials[pid]:
                check.stolen_attempts += 1
                check.stolen_refused += 0 if opened else 1
    return check


def naive_questions(m: dict) -> list[tuple[str, str]]:
    """What a screened lawyer would actually type about a restricted matter: naming the
    client, or — the realistic one — asking for precedent, naming nothing at all."""
    kind = m["matter_type"].replace("-", " ")
    return [
        ("client-named", f"What was the outcome of the {kind} for {m['client_name']}, "
                         f"and who led it?"),
        ("precedent", f"What precedent do we have on a {kind} for a "
                      f"{m['client_type'].replace('-', ' ')}, and how did similar matters end?"),
    ]


def _naive_check(cfg, attrs: dict, rules: list, denials: dict, tokens: dict) -> NaiveCheck:
    """The index asked directly, on questions about each restricted matter, as each
    person screened from it — with no filter, with a document-level ACL, and with the
    resolver's lineage filter. Not a pass/fail: the numbers the design is measured
    against. A leak is a passage from a document that depends, per the manifest, on
    a matter the person is walled from."""
    from ..index import DOC_ACL, LINEAGE, NONE, Embedder, Index
    from ..ingest import documents as documents_mod

    index, embed = Index(cfg.index_url), Embedder()
    matters_of = doc_matters(documents_mod.read(cfg.documents_path))
    every = sorted({m for ms in matters_of.values() for m in ms})
    check = NaiveCheck()
    for _, matter in rules:
        m = attrs[matter]
        for shape, text in naive_questions(m):
            vector = embed([text])[0]
            unfiltered = index.search(text, vector, None, k=5)
            for persona, denied in denials.items():
                if matter not in denied:
                    continue
                permitted = [x for x in every if x not in denied]
                for variant in VARIANTS:
                    hits = unfiltered if variant == NONE else index.search(
                        text, vector, permitted, k=5,
                        mode=DOC_ACL if variant == DOC_ACL else LINEAGE)
                    v = check.variants[variant]
                    v.questions += 1
                    leaked = [h for h in hits if matters_of.get(h["doc_id"], set()) & denied]
                    if not leaked:
                        continue
                    v.leaked_questions += 1
                    v.leaked_passages += len(leaked)
                    v.via_citation += sum(1 for h in leaked if h["matter_id"] not in denied)
                    if len(v.examples) < 3:
                        docs = ", ".join(sorted({h["doc_id"] for h in leaked}))
                        v.examples.append(
                            f"{persona}, {shape} question about a {m['matter_type']}: top-5 "
                            f"held {len(leaked)} walled passage(s) ({docs})")
    return check


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
        rows = response.get("rows") or []
        refs = {r.get("matterRef") for r in rows}
        seen = bool(rows) if case.template == "CQ-10" else case.matter in refs
        if refused or not seen:
            case.problem = "over-refusal: a matter this persona may see was withheld"


def _judge_note(case: Case, response: dict, note: str, disclosure: str,
                tokens: list[str]) -> None:
    case.outcome = response.get("outcome", "?")
    case.rows = len(response.get("rows") or [])
    case.trace = response.get("trace", "")
    case.leaked = _scan(response, tokens)
    listed = {r.get("docId") for r in response.get("rows") or []}
    linked = {s.get("document") for s in response.get("sources") or []}
    blocked = ((response.get("explain") or {}).get("blocked") or {}).get("by_lineage", 0)
    if case.outcome.startswith("refused") or not case.rows:
        case.problem = "over-refusal: the open matter's documents were withheld"
    elif case.denied and (note in listed or note in linked):
        case.problem = "a note citing a walled matter was listed or linked"
    elif case.denied and disclosure == "withheld-count" and not blocked:
        case.problem = "a withheld note was not counted as withheld by lineage"
    elif not case.denied and note not in listed:
        case.problem = "over-refusal: a note this persona may see was withheld"


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

    from ..ingest import documents as documents_mod

    docs = documents_mod.read(cfg.documents_path)
    matters_of = doc_matters(docs)
    denials = {p: expected_denials(barriers, personas[p], records) for p in PERSONAS}
    tokens = {p: _tokens(denials[p], derived_closure(facts, denials[p]),
                         walled_documents(matters_of, denials[p])) for p in PERSONAS}
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

    # Passages behind a permit: one hop from each restricted matter's client.
    for rule, matter in rules:
        for persona in PERSONAS:
            first = clients[persona].ask("CQ-01", {"client": attrs[matter]["client_ref"]})
            case = Case(rule, matter, persona, "passages", "passages",
                        {"after": "CQ-01"}, denied=matter in denials[persona])
            if first.get("permit"):
                response = clients[persona].passages(first["permit"], "outcome settlement fine")
                case.outcome, case.trace = response.get("outcome", "?"), response.get("trace", "")
                case.rows = len(response.get("passages") or [])
                case.leaked = _scan(response, tokens[persona])
            else:
                case.outcome = "no permit — nothing permitted"
            cases.append(case)

    # Precedent notes: filed on an open matter anyone may see, citing a restricted one.
    # Asked for that open matter's documents, a person walled from the cited matter
    # must not get the note — not its row, not its facts, not a link, not a passage.
    # Someone who may see both must get it: withholding it would be an over-refusal.
    restricted = {m for _, m in rules}
    rule_of = {m: r for r, m in rules}
    for note in (d for d in docs if d.doc_type == "knowledge-note"):
        for cited in sorted(matters_of[note.doc_id] - {note.matter}):
            if cited not in restricted:
                continue
            for persona in PERSONAS:
                case = Case(rule_of[cited], cited, persona, "citing note", "CQ-10",
                            {"matter": note.matter, "note": note.doc_id},
                            denied=cited in denials[persona])
                response = clients[persona].ask("CQ-10", {"matter": note.matter})
                _judge_note(case, response, note.doc_id, disclosure, tokens[persona])
                cases.append(case)
                if response.get("permit"):
                    after = clients[persona].passages(response["permit"],
                                                      "precedent outcome settlement fine")
                    case = Case(rule_of[cited], cited, persona, "passages", "passages",
                                {"after": "CQ-10", "matter": note.matter},
                                denied=cited in denials[persona])
                    case.outcome, case.trace = after.get("outcome", "?"), after.get("trace", "")
                    case.rows = len(after.get("passages") or [])
                    case.leaked = _scan(after, tokens[persona])
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
    opened = ("answered", "no-index")
    doors = [
        (name, outcome, (outcome in opened) == should_open)
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

    # The glossary path: the counts per reading are decided per person, like any
    # answer, and a question that names an ambiguous term without a reading is
    # refused for everyone.
    for persona in PERSONAS:
        case = Case("—", "—", persona, "term", "resolve_term", {"text": "active client"},
                    denied=False)
        response = clients[persona].resolve_term("active client")
        case.outcome, case.trace = response.get("outcome", "?"), response.get("trace", "")
        case.leaked = _scan(response, tokens[persona])
        if len(response.get("readings") or []) != 4:
            case.problem = "active client did not come back with its four readings"
        cases.append(case)
        for reading in ("practice", "finance", "bd", "risk"):
            case = Case("—", "—", persona, "term", "CQ-09", {"reading": reading}, denied=False)
            _judge(case, clients[persona].ask("CQ-09", {"reading": reading}), disclosure,
                   tokens[persona])
            cases.append(case)
        case = Case("—", "—", persona, "term", "CQ-09", {}, denied=False)
        response = clients[persona].ask("CQ-09", {})
        case.outcome, case.trace = response.get("outcome", "?"), response.get("trace", "")
        if case.outcome != "refused-ambiguous" or response.get("rows"):
            case.problem = "an ambiguous term was answered instead of refused"
        cases.append(case)

    # Reading the record is itself a door. Only Risk opens it.
    for persona in (*PERSONAS, "percy-svc"):
        c = clients[persona]
        for name, call in (
            ("audit_subject", lambda c=c: c.audit_subject("M-2022-0117")),
            ("audit_person", lambda c=c: c.audit_person("sanne")),
            ("audit_trace", lambda c=c: c.audit_trace(mara.get("trace", "t-00000000"))),
        ):
            outcome = call().get("outcome", "?")
            doors.append((f"{name}() as {persona}", outcome, outcome == "refused"))
    outcome = clients["risk"].audit_subject("M-2022-0117").get("outcome", "?")
    doors.append(("audit_subject() as risk", outcome, outcome == "shown"))
    outcome = clients["mara"].audit_verify().get("outcome", "?")
    doors.append(("audit_verify() as mara", outcome, outcome == "refused"))

    # Lineage is a read like any other: a walled derived graph has no lineage to show.
    for persona in PERSONAS:
        walled_graphs = sorted(derived_closure(facts, denials[persona]))[:2]
        for g in walled_graphs:
            outcome = clients[persona].lineage(iri.shorten(g)).get("outcome", "?")
            doors.append((f"lineage({iri.shorten(g)}) as {persona}", outcome,
                          outcome == "refused"))

    result = Result(disclosure=disclosure, cases=cases, doors=doors)
    result.store = _store_check(cfg, personas, denials)
    result.naive = _naive_check(cfg, attrs, rules, denials, tokens)

    # The record of all that must not leak what the barriers hide.
    traces = {c.trace: c.persona for c in cases if c.trace}
    all_tokens = {**tokens, **{p: [] for p in REFUSED_IDENTITIES}}
    restricted = sorted(m for _, m in rules)
    for record in read(cfg.audit_path):
        # Risk may read everything; the record of Risk reading must not become a
        # directory of the walls. What Risk asked about is hashed.
        if record.get("request", "").startswith("audit.") and record.get("persona") == "risk":
            result.audit_records += 1
            line = json.dumps(record)
            for ref in restricted:
                if ref in line:
                    result.audit_leaks.append(f"{record['trace']} (risk's own read): {ref}")
            continue
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
    st, nv = result.store, result.naive
    console.print(
        f"document store: {st.checks} persona×document checks against the graph, "
        f"{len(st.disagreements)} where the graph is broader or they disagree · stolen ids "
        f"{st.stolen_refused}/{st.stolen_attempts} refused"
    )
    for line in st.disagreements[:5]:
        console.print(f"  [red]✗ store[/] {line}")
    if st.weaker_docs:
        console.print(
            f"[yellow]finding:[/] the DMS is weaker than the graph on {len(st.weaker_docs)} "
            f"documents that cite walled matters ({len(st.weaker)} person×document pairs)"
        )
    for variant, v in nv.variants.items():
        console.print(
            f"[yellow]vector comparison, {variant}:[/] {v.leaked_questions} of {v.questions} "
            f"questions returned walled passages ({v.leaked_passages} passages, "
            f"{v.via_citation} through a citation)"
        )
    console.print("[green]zero leaks[/]" if result.passed else "[red]FAILED[/]")
    return result


def render(result: Result) -> str:
    cases = [c for c in result.cases
             if c.shape not in ("identity", "session", "term", "passages", "citing note")]
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
        f"| precedent notes citing a restricted matter, asked for as each persona | "
        f"{sum(1 for c in result.cases if c.shape == 'citing note')} |",
        f"| **leaked** | **{len(result.leaks)}** |",
        f"| wrong refusals (including over-refusals) | {len(result.problems)} |",
        f"| doors behaving (permit, decision record) | "
        f"{sum(ok for *_, ok in result.doors)} / {len(result.doors)} |",
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
    passages = [c for c in result.cases if c.shape == "passages"]
    st, nv = result.store, result.naive
    lines += [
        "", "## Passages, through the permit", "",
        "For each restricted matter, each persona asks for the client's matters (CQ-01), then",
        "asks the index for passages with the permit that answer carried. The permit's",
        "matters are the filter, inside the query.", "",
        "| rule | persona | may see the matter | passages | leaked |", "|---|---|---|---|---|",
    ]
    for c in passages:
        lines.append(f"| {c.rule} | {c.persona} | {'no' if c.denied else 'yes'} | {c.rows} | "
                     f"{', '.join(c.leaked) or 'nothing'} |")
    notes = [c for c in result.cases if c.shape == "citing note"]
    lines += [
        "", "## Precedent notes — a document inherits the matters it cites", "",
        "A knowledge note filed on an open, unrestricted matter cites a restricted matter by",
        "its file number, with that matter's client and outcome. Each persona asks for the",
        "open matter's documents (CQ-10). Walled from the cited matter, the note must not be",
        "listed, linked or passed as a passage — and must be counted as withheld by lineage;",
        "allowed both, it must be listed. What a note cites is read from the manifest.", "",
        "| rule | cited | filed on | note | persona | may see the cited matter | outcome | "
        "as it should be |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in notes:
        ok = "yes" if not (c.leaked or c.problem) else f"**no** — {c.problem or 'leaked'}"
        lines.append(f"| {c.rule} | {c.matter} | {c.slots['matter']} | {c.slots['note']} | "
                     f"{c.persona} | {'no' if c.denied else 'yes'} | {c.outcome} | {ok} |")
    lines += [
        "", "## The document store — the second enforcement point", "",
        "Every persona, every document: the store's own policy (compiled from `barriers.yaml`",
        "into per-persona MinIO users) against OPA's decision for the document's matter. Then",
        "the stolen identifier: each restricted document fetched with the credentials of each",
        "person walled from it — the case where an id leaked by some other route.", "",
        "Where a document cites nothing, the graph and the store must agree exactly. Where it",
        "cites another matter, the graph may be *stricter* than the store — the DMS does not",
        "know what a document cites — but never broader; only broader fails the gate.", "",
        "| | |", "|---|---|",
        f"| persona × document checks | {st.checks} |",
        f"| **the graph broader than the store, or disagreeing where nothing is cited** | "
        f"**{len(st.disagreements)}** |",
        f"| documents citing another matter, per the graph's lineage | {st.citing_docs} |",
        f"| … where the store opens what the graph withholds | {len(st.weaker_docs)} documents, "
        f"{len(st.weaker)} person × document pairs |",
        f"| stolen-id fetches refused by the store | {st.stolen_refused} / {st.stolen_attempts} |",
        "",
        f"**Finding.** The DMS is weaker than the graph on {len(st.weaker_docs)} documents that "
        "cite walled matters: it filters by the matter a document is filed on, and does not",
        "know what the document cites. Classification write-back to the DMS is the",
        "programme's fix; the lab does not add per-object denies the DMS would not have.",
        "", "## The comparison — the index asked directly, three filters", "",
        "Questions about each restricted matter, asked as each person walled from it — one",
        "naming the client, one asking for precedent and naming nothing. Top-5 passages,",
        "filtered three ways. A leak is a passage from a document that depends, per the",
        "manifest, on a walled matter: filed on one, or citing one. Not a pass or fail —",
        "the numbers the design is measured against.", "",
        "| filter | questions | **returned walled passages** | walled passages | "
        "… through a citation |",
        "|---|---|---|---|---|",
    ]
    for variant, label in VARIANTS.items():
        v = nv.variants[variant]
        lines.append(f"| {label} | {v.questions} | **{v.leaked_questions}** | "
                     f"{v.leaked_passages} | {v.via_citation} |")
    lines.append("")
    for variant in VARIANTS:
        lines += [f"- `{variant}` — {e}" for e in nv.variants[variant].examples]
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
    lines += ["", "## The glossary path", "",
              "`resolve_term(\"active client\")` and each reading of `CQ-09`, per persona —",
              "scanned like any answer. `CQ-09` with no reading must be refused as ambiguous.", "",
              "| persona | question | reading | outcome | leaked |", "|---|---|---|---|---|"]
    for c in result.cases:
        if c.shape == "term":
            lines.append(f"| {c.persona} | {c.template} | {c.slots.get('reading', '—')} | "
                         f"{c.outcome}{' ✗ ' + c.problem if c.problem else ''} | "
                         f"{', '.join(c.leaked) or 'nothing'} |")
    lines += ["", "## Doors", "",
              "The permit, and the decision record — which only Risk & Compliance may read.",
              "", "| attempt | outcome | as it should be |", "|---|---|---|"]
    for name, outcome, ok in result.doors:
        lines.append(f"| {name} | {outcome} | {'yes' if ok else '**no**'} |")
    lines += [
        "",
        "## Legend",
        "",
        "`answered-with-withheld` means rows came back and the persona was told how many were",
        "withheld, and under which rule — the `withheld-count` policy. A leak is any denied",
        "matter or derived graph appearing anywhere in the response, including inside the permit.",
        "",
    ]
    return "\n".join(lines)
