"""Competency questions, bound to query templates.

The model does not write SPARQL. The resolver holds a small library of templates,
each answering a question the practice groups agreed the graph must answer, and a
question is served by picking a template and filling its slots. This is the same
position as a governed metric registry: every answer comes from a registered
definition, never from ad-hoc query generation.

From M1 every template also says what it touches, so that access can be decided
before anything is retrieved (docs/decisions/0009):

- `matter_var` — the variable that binds a matter. Spine facts are allowed or
  denied by their matter. `None` means the question reaches no matter at all.
- `graphs` — every `GRAPH ?var` in the query, and what kind of graph it may be:
  `spine` (the systems of record), `vocab` (ontology and vocabularies) or
  `derived` (decided by lineage). The binder constrains every one of them; a
  graph variable the template does not declare is a test failure, because an
  unconstrained `GRAPH ?x` can match a graph nobody decided on.

Two placeholders carry the decision into the query:

- `{{access:<var>}}` — `VALUES ?matter { …permitted… }` in the bound query,
  nothing in the candidate query.
- `{{graph:<var>}}` — a filter on that graph variable, placed inside the same
  group as its GRAPH pattern so an OPTIONAL stays optional.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import iri

IRI_RE = re.compile(r"^https://lab\.fps4\.dev/[A-Za-z0-9/_.\-]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GRAPH_VAR_RE = re.compile(r"GRAPH\s+\?(\w+)")

# Short forms a person — or an assistant — will actually type.
SHORT_FORMS = (
    (re.compile(r"^M-\d{4}-\d{4}$"), iri.matter),
    (re.compile(r"^C-\d{4}$"), iri.client),
    (re.compile(r"^P-\d{4}$"), iri.person),
)
CURIES = {"id:": iri.ID, "gl:": iri.GLOSSARY, "g:": iri.GRAPH}


class SlotError(ValueError):
    pass


def expand(value: str) -> str:
    value = value.strip()
    for pattern, make in SHORT_FORMS:
        if pattern.match(value):
            return make(value)
    for prefix, base in CURIES.items():
        if value.startswith(prefix):
            return base + value[len(prefix) :]
    return value


@dataclass(frozen=True)
class Slot:
    name: str
    kind: str  # "iri" | "date"
    default: str
    description: str


@dataclass(frozen=True)
class Template:
    id: str
    question: str
    slots: tuple[Slot, ...]
    select: str
    where: str
    columns: tuple[str, ...]
    graphs: dict[str, str]
    matter_var: str | None = "matter"
    kind: str = "rows"  # "rows" | "aggregate"
    tail: str = ""
    note: str = ""
    needs: str = "facts"  # facts | passages | both — what the router reads
    passage_query: str = ""  # what to ask the index, for templates that need passages
    listed: bool = True  # False for a reading's template, reached through its term
    derived: tuple[str, ...] = field(init=False, default=())

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "derived", tuple(v for v, k in self.graphs.items() if k == "derived")
        )

    # ── slots ───────────────────────────────────────────────────────────────
    def check_slots(self, params: dict[str, str] | None) -> dict[str, str]:
        params = dict(params or {})
        bound: dict[str, str] = {}
        for slot in self.slots:
            value = params.pop(slot.name, None)
            value = slot.default if value in (None, "") else str(value)
            if slot.kind == "iri":
                value = expand(value)
                if not IRI_RE.match(value):
                    raise SlotError(f"{slot.name}: not an identifier in this estate: {value!r}")
            elif slot.kind == "date":
                if not DATE_RE.match(value):
                    raise SlotError(f"{slot.name}: expected YYYY-MM-DD, got {value!r}")
            else:  # pragma: no cover - guarded by construction
                raise SlotError(f"unknown slot kind {slot.kind}")
            bound[slot.name] = value
        if params:
            raise SlotError(f"unknown slot(s) for {self.id}: {', '.join(sorted(params))}")
        return bound

    def _render_slots(self, where: str, slots: dict[str, str]) -> str:
        for slot in self.slots:
            value = slots[slot.name]
            rendered = f"<{value}>" if slot.kind == "iri" else f'"{value}"^^xsd:date'
            where = where.replace("{{" + slot.name + "}}", rendered)
        return where

    def _render_graphs(self, where: str, permitted_graphs: list[str] | None) -> str:
        for var, kind in self.graphs.items():
            if kind == "spine":
                allowed = iri.SPINE_GRAPHS
            elif kind == "vocab":
                allowed = iri.VOCAB_GRAPHS
            elif permitted_graphs is None:  # candidate query: reach, do not decide
                where = where.replace("{{graph:" + var + "}}", "")
                continue
            else:
                allowed = tuple(permitted_graphs)
            clause = (
                f"FILTER (?{var} IN ({', '.join(f'<{g}>' for g in allowed)}))"
                if allowed
                else "FILTER (false)"
            )
            where = where.replace("{{graph:" + var + "}}", clause)
        return where

    # ── the two queries ────────────────────────────────────────────────────
    def candidates(self, slots: dict[str, str]) -> str:
        """Which matters and derived graphs the question would reach. Identifiers only."""
        reach = ([self.matter_var] if self.matter_var else []) + list(self.derived)
        if not reach:
            return ""
        where = self._render_slots(self.where, slots)
        if self.matter_var:
            where = where.replace("{{access:" + self.matter_var + "}}", "")
        where = self._render_graphs(where, None)
        head = " ".join(f"?{v}" for v in reach)
        return iri.PREFIXES + f"SELECT DISTINCT {head} WHERE {{{where}}}\n"

    def bind(
        self,
        slots: dict[str, str],
        permitted_matters: list[str] | None = None,
        permitted_graphs: list[str] | None = None,
    ) -> str:
        """The query that produces evidence. It cannot name a denied matter."""
        where = self._render_slots(self.where, slots)
        if self.matter_var:
            values = " ".join(f"<{m}>" for m in (permitted_matters or []))
            where = where.replace(
                "{{access:" + self.matter_var + "}}", f"VALUES ?{self.matter_var} {{ {values} }}"
            )
        where = self._render_graphs(where, list(permitted_graphs or []))
        return iri.PREFIXES + f"SELECT {self.select} WHERE {{{where}}}\n{self.tail}\n"


SPINE = "spine"
VOCAB = "vocab"
DERIVED = "derived"

# The outcome, if one was told — optional, because most matters have none and an
# answer must not invent one.
OUTCOME_OPTIONAL = """
  OPTIONAL {
    GRAPH ?fg {
      ?fact a ssf:Fact ;
            ssf:factSubject ?matter ;
            ssf:factPredicate ssf:hadOutcome ;
            ssf:factObject ?outcome ;
            ssf:reviewState ?stated ;
            ssf:confidence ?confidence .
    }
    {{graph:fg}}
    GRAPH ?go { ?outcome skos:prefLabel ?outcomeLabel }
    {{graph:go}}
    OPTIONAL {
      GRAPH ?rg { ?rv ssf:reviews ?fact ; ssf:verdict ?verdict }
      {{graph:rg}}
    }
    BIND (COALESCE(?verdict, ?stated) AS ?review)
    # A fact a person has rejected is not asserted. It stays in the graph, with its
    # review, for the record.
    FILTER (?review != "rejected")
  }"""

CQ01 = Template(
    id="CQ-01",
    question="Which matters have we run for this client, who led them, and are they closed?",
    slots=(Slot("client", "iri", iri.client("C-0042"), "the client, e.g. C-0042"),),
    columns=("matterRef", "typeLabel", "leadLabel", "opened", "closed", "g"),
    graphs={"g": SPINE, "gt": VOCAB, "gh": SPINE},
    select="?matterRef ?typeLabel ?leadLabel ?opened ?closed ?g",
    where="""
  {{access:matter}}
  GRAPH ?g {
    ?matter a ssf:Matter ;
            ssf:matterRef ?matterRef ;
            ssf:forClient {{client}} ;
            ssf:matterType ?type ;
            ssf:ledBy ?lead ;
            ssf:openedOn ?opened .
    OPTIONAL { ?matter ssf:closedOn ?closed }
  }
  {{graph:g}}
  GRAPH ?gt { ?type skos:prefLabel ?typeLabel }
  {{graph:gt}}
  GRAPH ?gh { ?lead rdfs:label ?leadLabel }
  {{graph:gh}}
""",
    tail="ORDER BY ?opened",
)

CQ02 = Template(
    id="CQ-02",
    question=(
        "Have we advised a client of this type on this kind of matter, in this "
        "jurisdiction, since this date — who led it, and what was the outcome?"
    ),
    slots=(
        Slot("client_type", "iri", iri.concept("client-type", "fund-manager"), "client type"),
        Slot(
            "matter_type",
            "iri",
            iri.concept("matter-type", "regulatory-investigation"),
            "matter type",
        ),
        Slot("jurisdiction", "iri", iri.jurisdiction("NL"), "jurisdiction"),
        Slot("since", "date", "2021-01-01", "earliest opening date"),
    ),
    columns=(
        "matterRef", "clientLabel", "leadLabel", "opened", "closed",
        "outcomeLabel", "review", "confidence", "g", "fg",
    ),
    graphs={"g": SPINE, "gh": SPINE, "fg": DERIVED, "go": VOCAB, "rg": DERIVED},
    note=(
        "The matters come from the systems of record. The outcome, where there is one, "
        "was told by a named partner and carries its review state; where there is none, "
        "the answer does not supply one."
    ),
    select=(
        "?matterRef ?clientLabel ?leadLabel ?opened ?closed "
        "?outcomeLabel ?review ?confidence ?g ?fg"
    ),
    where="""
  {{access:matter}}
  GRAPH ?g {
    ?matter a ssf:Matter ;
            ssf:matterRef ?matterRef ;
            ssf:matterType {{matter_type}} ;
            ssf:inJurisdiction {{jurisdiction}} ;
            ssf:forClient ?client ;
            ssf:ledBy ?lead ;
            ssf:openedOn ?opened .
    OPTIONAL { ?matter ssf:closedOn ?closed }
    ?client ssf:clientType {{client_type}} ;
            rdfs:label ?clientLabel .
  }
  {{graph:g}}
  GRAPH ?gh { ?lead rdfs:label ?leadLabel }
  {{graph:gh}}
  FILTER (?opened >= {{since}})
"""
    + OUTCOME_OPTIONAL,
    tail="ORDER BY ?opened",
)

CQ03 = Template(
    id="CQ-03",
    question="Who has worked on matters for this client, in what role, and between which dates?",
    slots=(Slot("client", "iri", iri.client("C-0042"), "the client, e.g. C-0042"),),
    columns=("personLabel", "role", "matterRef", "validFrom", "validTo", "g"),
    graphs={"g": SPINE, "gh": SPINE},
    note="Valid-time lives on the assignment, which is why this question is answerable at all.",
    select="?personLabel ?role ?matterRef ?validFrom ?validTo ?g",
    where="""
  {{access:matter}}
  GRAPH ?g {
    ?matter ssf:forClient {{client}} ; ssf:matterRef ?matterRef .
    ?assignment a ssf:Assignment ;
                ssf:assignmentMatter ?matter ;
                ssf:assignmentPerson ?person ;
                ssf:assignmentRole ?role ;
                ssf:validFrom ?validFrom .
    OPTIONAL { ?assignment ssf:validTo ?validTo }
  }
  {{graph:g}}
  GRAPH ?gh { ?person rdfs:label ?personLabel }
  {{graph:gh}}
""",
    tail="ORDER BY ?validFrom ?personLabel",
)

CQ04 = Template(
    id="CQ-04",
    question="Which client relationships does this partner hold in the CRM?",
    slots=(Slot("person", "iri", iri.person("P-0101"), "the partner, e.g. P-0101"),),
    columns=("accountLabel", "typeLabel", "since", "g"),
    graphs={"g": SPINE, "gt": VOCAB},
    matter_var=None,
    note=(
        "Answered from the CRM graph, and it reaches no matter — so no matter barrier "
        "applies to it. Whether a barrier should also cover the client relationship is "
        "a question for the firm, not one the lab answers for it. Note the spelling: "
        "these are accounts, and nothing has yet decided they are the same "
        "organisations as the practice-management clients."
    ),
    select="?accountLabel ?typeLabel ?since ?g",
    where="""
  GRAPH ?g {
    ?account a ssf:Account ;
             ssf:relationshipPartner {{person}} ;
             rdfs:label ?accountLabel ;
             ssf:accountType ?type ;
             ssf:accountSince ?since .
  }
  {{graph:g}}
  GRAPH ?gt { ?type skos:prefLabel ?typeLabel }
  {{graph:gt}}
""",
    tail="ORDER BY ?since",
)

CQ05 = Template(
    id="CQ-05",
    question="How many matters of each type did this office open, by year?",
    slots=(Slot("office", "iri", iri.office("Amsterdam"), "the office"),),
    columns=("year", "typeLabel", "n"),
    graphs={"g": SPINE, "gt": VOCAB},
    kind="aggregate",
    select="?year ?typeLabel (COUNT(?matter) AS ?n)",
    where="""
  {{access:matter}}
  GRAPH ?g {
    ?matter a ssf:Matter ;
            ssf:office {{office}} ;
            ssf:matterType ?type ;
            ssf:openedOn ?opened .
  }
  {{graph:g}}
  GRAPH ?gt { ?type skos:prefLabel ?typeLabel }
  {{graph:gt}}
  BIND (YEAR(?opened) AS ?year)
""",
    tail="GROUP BY ?year ?typeLabel\nORDER BY ?year ?typeLabel",
)

CQ06 = Template(
    id="CQ-06",
    question="Who led this matter, for which client, and what was the outcome?",
    slots=(Slot("matter", "iri", iri.matter("M-2021-0043"), "the matter, e.g. M-2021-0043"),),
    columns=(
        "matterRef", "clientLabel", "typeLabel", "leadLabel", "opened", "closed",
        "outcomeLabel", "review", "g", "fg",
    ),
    graphs={"g": SPINE, "gt": VOCAB, "gh": SPINE, "fg": DERIVED, "go": VOCAB, "rg": DERIVED},
    select=(
        "?matterRef ?clientLabel ?typeLabel ?leadLabel ?opened ?closed "
        "?outcomeLabel ?review ?g ?fg"
    ),
    where="""
  {{access:matter}}
  GRAPH ?g {
    ?matter a ssf:Matter ;
            ssf:matterRef ?matterRef ;
            ssf:forClient ?client ;
            ssf:matterType ?type ;
            ssf:ledBy ?lead ;
            ssf:openedOn ?opened .
    OPTIONAL { ?matter ssf:closedOn ?closed }
    ?client rdfs:label ?clientLabel .
  }
  {{graph:g}}
  FILTER (?matter = {{matter}})
  GRAPH ?gt { ?type skos:prefLabel ?typeLabel }
  {{graph:gt}}
  GRAPH ?gh { ?lead rdfs:label ?leadLabel }
  {{graph:gh}}
"""
    + OUTCOME_OPTIONAL,
)

CQ07 = Template(
    id="CQ-07",
    question="Who has led the most matters of this type, in this jurisdiction, since this date?",
    slots=(
        Slot(
            "matter_type",
            "iri",
            iri.concept("matter-type", "regulatory-investigation"),
            "matter type",
        ),
        Slot("jurisdiction", "iri", iri.jurisdiction("NL"), "jurisdiction"),
        Slot("since", "date", "2018-01-01", "earliest opening date"),
    ),
    columns=("leadLabel", "n"),
    graphs={"g": SPINE, "gh": SPINE},
    kind="aggregate",
    note=(
        "An aggregate. If any matter it would count is one you cannot see, the count "
        "is wrong in a way you cannot detect — so it is refused, or, where the policy "
        "says so, computed over what you can see and labelled as such."
    ),
    select="?leadLabel (COUNT(DISTINCT ?matter) AS ?n)",
    where="""
  {{access:matter}}
  GRAPH ?g {
    ?matter a ssf:Matter ;
            ssf:matterType {{matter_type}} ;
            ssf:inJurisdiction {{jurisdiction}} ;
            ssf:ledBy ?lead ;
            ssf:openedOn ?opened .
  }
  {{graph:g}}
  GRAPH ?gh { ?lead rdfs:label ?leadLabel }
  {{graph:gh}}
  FILTER (?opened >= {{since}})
""",
    tail="GROUP BY ?leadLabel\nORDER BY DESC(?n) ?leadLabel",
)

CQ08 = Template(
    id="CQ-08",
    question="What expertise has been recorded for this person, by whom, and how sure are we?",
    slots=(Slot("person", "iri", iri.person("P-0101"), "the person, e.g. P-0101"),),
    columns=("topicLabel", "review", "confidence", "toldBy", "fg"),
    graphs={"fg": DERIVED, "gt": VOCAB, "gb": SPINE},
    matter_var=None,
    note=(
        "None of these facts names a matter. Each was derived from one, and it is the "
        "lineage — not the subject — that decides who may see it."
    ),
    select="?topicLabel ?review ?confidence ?toldBy ?fg",
    where="""
  GRAPH ?fg {
    ?fact a ssf:Fact ;
          ssf:factSubject {{person}} ;
          ssf:factPredicate ssf:hasExpertise ;
          ssf:factObject ?topic ;
          ssf:reviewState ?review ;
          ssf:confidence ?confidence ;
          ssf:assertedBy ?teller .
  }
  {{graph:fg}}
  GRAPH ?gt { ?topic skos:prefLabel ?topicLabel }
  {{graph:gt}}
  GRAPH ?gb { ?teller rdfs:label ?toldBy }
  {{graph:gb}}
""",
    tail="ORDER BY ?topicLabel",
)

CQ10 = Template(
    id="CQ-10",
    question="What documents do we hold on this matter, what do they establish, and where can "
    "I read them?",
    slots=(Slot("matter", "iri", iri.matter("M-2021-0043"), "the matter, e.g. M-2021-0043"),),
    columns=("docId", "docType", "date", "fact", "value", "confidence", "review", "fg"),
    graphs={"g": SPINE, "fg": DERIVED},
    needs="both",
    passage_query="outcome of the matter, the advice given, and who acted",
    note=(
        "Facts extracted from each document, with confidence and review state — and the "
        "passages behind them, from the index, filtered to what you may see. Every document "
        "carries a link that opens it, minted with your own document-store credentials."
    ),
    select="?docId ?docType ?date ?fact ?value ?confidence ?review ?fg",
    where="""
  {{access:matter}}
  GRAPH ?g {
    ?doc a ssf:Document ; ssf:documentMatter ?matter ; ssf:docType ?docType ;
         ssf:documentDate ?date .
  }
  {{graph:g}}
  FILTER (?matter = {{matter}})
  BIND (STRAFTER(STR(?doc), "/id/doc/") AS ?docId)
  OPTIONAL {
    GRAPH ?fg {
      ?f ssf:fromDocument ?doc ; ssf:factPredicate ?p ; ssf:factObject ?o ;
         ssf:confidence ?confidence ; ssf:reviewState ?review .
    }
    {{graph:fg}}
    BIND (STRAFTER(STR(?p), "/firm/") AS ?fact)
    BIND (STRAFTER(STR(?o), "fps4.dev/") AS ?value)
  }
""",
    tail="ORDER BY ?date ?docId ?fact",
)

CQ11 = Template(
    id="CQ-11",
    question="Which facts about this matter are unconfirmed or extracted, and await review?",
    slots=(Slot("matter", "iri", iri.matter("M-2022-0022"), "the matter, e.g. M-2022-0022"),),
    columns=("factId", "fact", "value", "confidence", "review", "source", "fg"),
    graphs={"fg": DERIVED, "rg": DERIVED},
    matter_var=None,
    note=(
        "Review with `tkg review confirm|reject <factId>`. A review is its own graph, "
        "derived from the fact's, so it is walled wherever the fact is."
    ),
    select="?factId ?fact ?value ?confidence ?review ?source ?fg",
    where="""
  GRAPH ?fg {
    ?f a ssf:Fact ; ssf:factSubject {{matter}} ; ssf:factPredicate ?p ; ssf:factObject ?o ;
       ssf:confidence ?confidence ; ssf:reviewState ?stated .
    OPTIONAL { ?f ssf:fromDocument ?d }
    OPTIONAL { ?f ssf:assertedBy ?by }
  }
  {{graph:fg}}
  OPTIONAL {
    GRAPH ?rg { ?rv ssf:reviews ?f ; ssf:verdict ?verdict }
    {{graph:rg}}
  }
  BIND (COALESCE(?verdict, ?stated) AS ?review)
  FILTER (?review IN ("extracted", "unconfirmed"))
  BIND (STRAFTER(STR(?f), "/id/fact/") AS ?factId)
  BIND (STRAFTER(STR(?p), "/firm/") AS ?fact)
  BIND (STRAFTER(STR(?o), "fps4.dev/") AS ?value)
  BIND (COALESCE(STRAFTER(STR(?d), "/id/"), STRAFTER(STR(?by), "/id/")) AS ?source)
""",
    tail="ORDER BY ?confidence ?factId",
)

# ── "active client": one question, four readings, four owners ─────────────
# Each reading is its own template, reached through the term. A question that
# names the term without choosing a reading is refused at the router with the
# readings listed back — see TERM_QUESTIONS below and docs/decisions/0015.
AS_OF = Slot("as_of", "date", "2025-12-31", "the date the estate is as of")

CQ09_PRACTICE = Template(
    id="CQ-09-practice",
    question="How many active clients — a client with a matter open on the as-of date?",
    slots=(AS_OF,),
    columns=("n",),
    graphs={"g": SPINE},
    kind="aggregate",
    listed=False,
    select="(COUNT(DISTINCT ?client) AS ?n)",
    where="""
  {{access:matter}}
  GRAPH ?g {
    ?matter a ssf:Matter ; ssf:forClient ?client ; ssf:openedOn ?opened .
    OPTIONAL { ?matter ssf:closedOn ?closed }
  }
  {{graph:g}}
  FILTER (?opened <= {{as_of}} && (!BOUND(?closed) || ?closed > {{as_of}}))
""",
)

CQ09_FINANCE = Template(
    id="CQ-09-finance",
    question="How many active clients — a client invoiced in the twelve months to the as-of date?",
    slots=(Slot("from", "date", "2025-01-01", "start of the twelve months"), AS_OF),
    columns=("n",),
    graphs={"g": SPINE},
    kind="aggregate",
    listed=False,
    select="(COUNT(DISTINCT ?client) AS ?n)",
    where="""
  {{access:matter}}
  GRAPH ?g {
    ?matter a ssf:Matter ; ssf:forClient ?client .
    ?invoice ssf:invoiceMatter ?matter ; ssf:invoicedOn ?on .
  }
  {{graph:g}}
  FILTER (?on >= {{from}} && ?on <= {{as_of}})
""",
)

CQ09_BD = Template(
    id="CQ-09-bd",
    question="How many active clients — CRM accounts with a named relationship partner?",
    slots=(),
    columns=("n",),
    graphs={"g": SPINE},
    kind="aggregate",
    matter_var=None,
    listed=False,
    note="Counts CRM accounts. Nothing has yet reconciled them with practice-management clients.",
    select="(COUNT(DISTINCT ?account) AS ?n)",
    where="""
  GRAPH ?g { ?account a ssf:Account ; ssf:relationshipPartner ?partner . }
  {{graph:g}}
""",
)

CQ09_RISK = Template(
    id="CQ-09-risk",
    question="How many active clients — any organisation the firm has ever acted for?",
    slots=(AS_OF,),
    columns=("n",),
    graphs={"g": SPINE},
    kind="aggregate",
    listed=False,
    note="Related entities belong in this reading and are not modelled in the lab.",
    select="(COUNT(DISTINCT ?client) AS ?n)",
    where="""
  {{access:matter}}
  GRAPH ?g { ?matter a ssf:Matter ; ssf:forClient ?client ; ssf:openedOn ?opened . }
  {{graph:g}}
  FILTER (?opened <= {{as_of}})
""",
)

TEMPLATES: dict[str, Template] = {
    t.id: t
    for t in (
        CQ01, CQ02, CQ03, CQ04, CQ05, CQ06, CQ07, CQ08, CQ10, CQ11,
        CQ09_PRACTICE, CQ09_FINANCE, CQ09_BD, CQ09_RISK,
    )
}


@dataclass(frozen=True)
class TermQuestion:
    """A question whose meaning depends on a glossary term. The reading chooses
    the template; the glossary, not this file, says which readings exist."""

    id: str
    question: str
    term: str


TERM_QUESTIONS: dict[str, TermQuestion] = {
    "CQ-09": TermQuestion(
        "CQ-09",
        "How many active clients do we have? Say which reading — resolve_term('active client').",
        "active-client",
    ),
}
