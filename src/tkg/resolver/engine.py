"""The resolver, at M0 scale.

Given a competency question and its slots, bind the template, run it, and return
the evidence with the named graph each row came from. That last part is not
decoration: a fact that cannot say where it came from is not yet knowledge, and
the citation is what a lawyer checks.

M1 puts an access decision between binding and answering. M2 puts glossary
resolution and routing in front of binding. The shape of this function does not
change when they arrive — things are added to it, in a fixed order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import iri
from ..ingest.loader import Fuseki
from ..semantic.templates import TEMPLATES, Template


@dataclass
class Answer:
    template: Template
    bound_query: str
    slots: dict[str, str]
    rows: list[dict[str, str]] = field(default_factory=list)
    graphs: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.rows)


class Resolver:
    def __init__(self, fuseki: Fuseki) -> None:
        self.fuseki = fuseki

    def ask(self, template_id: str, params: dict[str, str] | None = None) -> Answer:
        try:
            template = TEMPLATES[template_id]
        except KeyError:
            known = ", ".join(sorted(TEMPLATES))
            raise KeyError(f"no such competency question: {template_id}. Known: {known}") from None

        query, slots = template.bind(params)
        result = self.fuseki.query(query)

        rows: list[dict[str, str]] = []
        graphs: list[str] = []
        for binding in result["results"]["bindings"]:
            row = {}
            for column in template.columns:
                cell = binding.get(column)
                if cell is None:
                    row[column] = ""
                    continue
                value = cell["value"]
                row[column] = iri.shorten(value) if cell["type"] == "uri" else value
            rows.append(row)
            if "g" in binding and binding["g"]["value"] not in graphs:
                graphs.append(binding["g"]["value"])
        return Answer(template=template, bound_query=query, slots=slots, rows=rows, graphs=graphs)
