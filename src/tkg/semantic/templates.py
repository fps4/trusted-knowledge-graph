"""Competency questions, bound to query templates.

The model does not write SPARQL. The resolver holds a small library of templates,
each answering a question the practice groups agreed the graph must answer, and a
question is served by picking a template and filling its slots. This is the same
position as a governed metric registry: every answer comes from a registered
definition, never from ad-hoc query generation.

M0 ships five, all answerable from the spine alone — no documents, no extraction.
M2 puts glossary resolution and routing in front of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import iri

IRI_RE = re.compile(r"^https://lab\.fps4\.dev/[A-Za-z0-9/_.\-]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SlotError(ValueError):
    pass


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
    sparql: str
    columns: tuple[str, ...]
    note: str = ""

    def bind(self, params: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
        params = dict(params or {})
        bound: dict[str, str] = {}
        query = self.sparql
        for slot in self.slots:
            value = params.pop(slot.name, slot.default)
            if slot.kind == "iri":
                if not IRI_RE.match(value):
                    raise SlotError(f"{slot.name}: not an identifier in this estate: {value!r}")
                rendered = f"<{value}>"
            elif slot.kind == "date":
                if not DATE_RE.match(value):
                    raise SlotError(f"{slot.name}: expected YYYY-MM-DD, got {value!r}")
                rendered = f'"{value}"^^xsd:date'
            else:  # pragma: no cover - guarded by construction
                raise SlotError(f"unknown slot kind {slot.kind}")
            bound[slot.name] = value
            query = query.replace("{{" + slot.name + "}}", rendered)
        if params:
            raise SlotError(f"unknown slot(s) for {self.id}: {', '.join(sorted(params))}")
        return iri.PREFIXES + query, bound


CQ01 = Template(
    id="CQ-01",
    question="Which matters have we run for this client, who led them, and are they closed?",
    slots=(
        Slot("client", "iri", iri.client("C-0042"), "the client, by its practice-management id"),
    ),
    columns=("matterRef", "typeLabel", "leadLabel", "opened", "closed", "g"),
    sparql="""
SELECT ?matterRef ?typeLabel ?leadLabel ?opened ?closed ?g WHERE {
  GRAPH ?g {
    ?matter a ssf:Matter ;
            ssf:matterRef ?matterRef ;
            ssf:forClient {{client}} ;
            ssf:matterType ?type ;
            ssf:ledBy ?lead ;
            ssf:openedOn ?opened .
    OPTIONAL { ?matter ssf:closedOn ?closed }
  }
  GRAPH ?gt { ?type skos:prefLabel ?typeLabel }
  GRAPH ?gh { ?lead rdfs:label ?leadLabel }
}
ORDER BY ?opened
""",
)

CQ02 = Template(
    id="CQ-02",
    question=(
        "Have we advised a client of this type on this kind of matter, in this "
        "jurisdiction, since this date — and who led it?"
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
    columns=("matterRef", "clientLabel", "leadLabel", "opened", "closed", "g"),
    note=(
        "The spine half of the demo's first scenario. The outcome of each matter is "
        "not here: outcomes are extracted from documents, and until they are, this "
        "answer says what it knows and no more."
    ),
    sparql="""
SELECT ?matterRef ?clientLabel ?leadLabel ?opened ?closed ?g WHERE {
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
  GRAPH ?gh { ?lead rdfs:label ?leadLabel }
  FILTER (?opened >= {{since}})
}
ORDER BY ?opened
""",
)

CQ03 = Template(
    id="CQ-03",
    question="Who has worked on matters for this client, in what role, and between which dates?",
    slots=(Slot("client", "iri", iri.client("C-0042"), "the client"),),
    columns=("personLabel", "role", "matterRef", "validFrom", "validTo", "g"),
    note="Valid-time lives on the assignment, which is why this question is answerable at all.",
    sparql="""
SELECT ?personLabel ?role ?matterRef ?validFrom ?validTo ?g WHERE {
  GRAPH ?g {
    ?matter ssf:forClient {{client}} ; ssf:matterRef ?matterRef .
    ?assignment a ssf:Assignment ;
                ssf:assignmentMatter ?matter ;
                ssf:assignmentPerson ?person ;
                ssf:assignmentRole ?role ;
                ssf:validFrom ?validFrom .
    OPTIONAL { ?assignment ssf:validTo ?validTo }
  }
  GRAPH ?gh { ?person rdfs:label ?personLabel }
}
ORDER BY ?validFrom ?personLabel
""",
)

CQ04 = Template(
    id="CQ-04",
    question="Which client relationships does this partner hold in the CRM?",
    slots=(Slot("person", "iri", iri.person("P-0101"), "the partner"),),
    columns=("accountLabel", "typeLabel", "since", "g"),
    note=(
        "Answered from the CRM graph. Note the spelling: these are accounts, not "
        "practice-management clients, and nothing has yet decided they are the same "
        "organisations. That decision has a name on it and belongs to identity resolution."
    ),
    sparql="""
SELECT ?accountLabel ?typeLabel ?since ?g WHERE {
  GRAPH ?g {
    ?account a ssf:Account ;
             ssf:relationshipPartner {{person}} ;
             rdfs:label ?accountLabel ;
             ssf:accountType ?type ;
             ssf:accountSince ?since .
  }
  GRAPH ?gt { ?type skos:prefLabel ?typeLabel }
}
ORDER BY ?since
""",
)

CQ05 = Template(
    id="CQ-05",
    question="How many matters of each type did this office open, by year?",
    slots=(Slot("office", "iri", iri.office("Amsterdam"), "the office"),),
    columns=("year", "typeLabel", "n"),
    sparql="""
SELECT ?year ?typeLabel (COUNT(?matter) AS ?n) WHERE {
  GRAPH ?g {
    ?matter a ssf:Matter ;
            ssf:office {{office}} ;
            ssf:matterType ?type ;
            ssf:openedOn ?opened .
  }
  GRAPH ?gt { ?type skos:prefLabel ?typeLabel }
  BIND (YEAR(?opened) AS ?year)
}
GROUP BY ?year ?typeLabel
ORDER BY ?year ?typeLabel
""",
)

TEMPLATES: dict[str, Template] = {t.id: t for t in (CQ01, CQ02, CQ03, CQ04, CQ05)}
