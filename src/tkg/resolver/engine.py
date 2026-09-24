"""The resolver: seven steps, one decision, one record.

A question arrives as a competency question and its slots, from a persona whose
identity was verified before this code runs. The steps, in the architecture's
order:

1. Plan          — M1: the question arrives already as a template id; noted, not done.
2. Resolve terms — M2: the glossary. Recorded as empty rather than faked.
3. Route         — M1: every question is a template over the graph.
4. Bind          — slots validated against the estate.
5. Decide        — candidates → lineage → OPA → permitted set. The only place a
                   decision is made. docs/decisions/0009.
6. Passages      — M3: the index. The permit that will guard it exists now.
7. Compose       — the bound query, which cannot name a denied matter; or a
                   refusal carrying the rule.

Everything above appends to one trace, and the trace is written once, at the
end, whatever happened — docs/decisions/0012. Denied identifiers go into it as
salted hashes, in every field — docs/decisions/0013.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from .. import __version__, iri
from ..access import permit as permit_mod
from ..access.decide import Decision, Opa, PolicyUnavailable, lineage
from ..audit.chain import Hasher, Writer, read
from ..ingest.loader import Fuseki
from ..semantic.templates import TEMPLATES, SlotError, Template

PIPELINE_VERSION = f"tkg {__version__}"

ROUTE = {
    "route": "graph",
    "reason": "M1: every question is a competency-question template over the graph. "
    "Routing between graph, index, hybrid and refuse arrives in M2.",
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _cell(cell: dict | None) -> str:
    if cell is None:
        return ""
    return iri.shorten(cell["value"]) if cell["type"] == "uri" else cell["value"]


def _public(grounds: dict) -> dict:
    """What a person may be told about a rule: never which matter it was reached through."""
    return {k: v for k, v in grounds.items() if k != "via"}


class Resolver:
    def __init__(
        self,
        fuseki: Fuseki,
        opa: Opa,
        writer: Writer,
        hasher: Hasher,
        permit_key: bytes,
        personas: dict[str, dict],
    ) -> None:
        self.fuseki = fuseki
        self.opa = opa
        self.writer = writer
        self.hasher = hasher
        self.permit_key = permit_key
        self.personas = personas

    # ── records ─────────────────────────────────────────────────────────────
    def _record(self, persona: str, request: str) -> dict:
        return {
            "trace": "t-" + secrets.token_hex(4),
            "ts": _now(),
            "persona": persona,
            "sub": self.personas.get(persona, {}).get("principal"),
            "request": request,
            "pipeline_version": PIPELINE_VERSION,
            "salt_id": self.hasher.salt_id,
        }

    def _write(self, record: dict) -> dict:
        return self.writer.append(record)

    def refuse_identity(self, request: str, reason: str) -> dict:
        record = self._record("(unverified)", request)
        record.update(outcome="refused-identity", reason=reason)
        self._write(record)
        return {"trace": record["trace"], "outcome": "refused-identity", "reason": reason}

    # ── ask ─────────────────────────────────────────────────────────────────
    def ask(self, persona: str, template_id: str, params: dict[str, str] | None) -> dict:
        record = self._record(persona, "ask")
        record.update(template=template_id, route=ROUTE, terms=[])
        try:
            response = self._ask(persona, template_id, params, record)
        except PolicyUnavailable as exc:
            record.update(outcome="refused-policy-unavailable", reason=str(exc)[:200])
            response = {
                "outcome": "refused-policy-unavailable",
                "reason": "The policy engine did not answer, so nothing was decided and "
                "nothing is returned. The resolver never decides on its own.",
            }
        self._write(record)
        return {"trace": record["trace"], "persona": persona, **response}

    def _ask(self, persona: str, template_id: str, params, record: dict) -> dict:
        template: Template | None = TEMPLATES.get(template_id)
        if template is None:
            known = ", ".join(sorted(TEMPLATES))
            record.update(outcome="refused-invalid", reason="no such competency question")
            return {"outcome": "refused-invalid", "reason": f"no such question. Known: {known}"}
        try:
            slots = template.check_slots(params)
        except SlotError as exc:
            # The rejected value is not recorded: it may be free text.
            record.update(outcome="refused-invalid", reason="slot refused")
            return {"outcome": "refused-invalid", "reason": str(exc)}

        # ── step 5 · decide ────────────────────────────────────────────────
        cand_matters, cand_graphs = self._candidates(template, slots)
        lineage_map = lineage(self.fuseki, cand_graphs)
        principal = self.personas[persona]["principal"]
        decision = self.opa.decide(principal, cand_matters, lineage_map)
        denied_m, denied_g = decision.denied_matters(), decision.denied_graphs()
        permitted_m = [m for m in cand_matters if m not in denied_m]
        permitted_g = [g for g in cand_graphs if g not in denied_g]

        record.update(
            slots=self._redact_slots(slots, denied_m, denied_g),
            considered={
                "matters": [self._id("matter", m, denied_m) for m in cand_matters],
                "graphs": [self._id("graph", g, denied_g) for g in cand_graphs],
            },
            decisions=self._decisions(decision, lineage_map),
            grounds=self._grounds(decision),
            disclosure=decision.disclosure,
            policy_version=decision.policy_version,
        )

        base = {
            "template": template.id,
            "question": template.question,
            "slots": slots,
            "policy_version": decision.policy_version,
        }
        explain = self._explain_live(decision)
        withholding = decision.disclosure == "withheld-count"

        # Who is asking decides before any matter does.
        if decision.principal:
            record.update(outcome="refused", returned={"rows": 0})
            return {
                **base,
                "outcome": "refused",
                "explain": {"rules": [_public(g) for g in decision.principal]},
            }

        denied_any = bool(denied_m or denied_g)
        if template.kind == "aggregate" and denied_any and withholding:
            record.update(outcome="refused-aggregate", returned={"rows": 0})
            return {
                **base,
                "outcome": "refused-aggregate",
                "reason": "This is a count over a set that includes matters you cannot see. "
                "Computed over the rest it would be wrong in a way you could not detect.",
                "explain": explain,
            }

        # ── step 7 · compose, from the permitted set only ──────────────────
        query = template.bind(
            slots, [iri.matter(m) for m in permitted_m], permitted_g
        )
        rows, cited = self._run(template, query)

        if denied_any and withholding:
            outcome = "refused" if not rows else "answered-with-withheld"
        else:
            outcome = "answered"
        scope = None
        if template.kind == "aggregate" and denied_any:
            scope = "Computed over the matters you can see."

        permit_token, permit_exp = None, None
        if rows:
            permit_token, permit_exp = permit_mod.mint(
                persona, record["trace"], permitted_m, permitted_g, self.permit_key
            )
        shown_matters = sorted({r["matterRef"] for r in rows if r.get("matterRef")})
        record.update(
            outcome=outcome,
            returned={
                "rows": len(rows),
                "matters": shown_matters,
                "graphs": cited,
                "permit": {"exp": permit_exp} if permit_token else None,
            },
        )
        response = {
            **base,
            "outcome": outcome,
            "columns": list(template.columns),
            "rows": rows,
            "citations": cited,
            "note": template.note,
        }
        if scope:
            response["scope"] = scope
        if denied_any and withholding:
            response["explain"] = explain
        if permit_token:
            response["permit"] = permit_token
            response["permit_expires"] = datetime.fromtimestamp(permit_exp, UTC).isoformat(
                timespec="seconds"
            )
        return response

    def _candidates(self, template: Template, slots: dict) -> tuple[list[str], list[str]]:
        query = template.candidates(slots)
        if not query:
            return [], []
        matters, graphs = set(), set()
        for row in self.fuseki.query(query)["results"]["bindings"]:
            if template.matter_var and template.matter_var in row:
                ref = iri.matter_ref(row[template.matter_var]["value"])
                if ref:
                    matters.add(ref)
            for var in template.derived:
                if var in row:
                    graphs.add(row[var]["value"])
        return sorted(matters), sorted(graphs)

    def _run(self, template: Template, query: str) -> tuple[list[dict], list[str]]:
        rows: list[dict] = []
        cited: list[str] = []
        for binding in self.fuseki.query(query)["results"]["bindings"]:
            rows.append({c: _cell(binding.get(c)) for c in template.columns})
            for var in ("g", *template.derived):
                if var in binding and binding[var]["value"] not in cited:
                    cited.append(binding[var]["value"])
        return rows, [iri.shorten(g) for g in cited]

    # ── what goes into the record ───────────────────────────────────────────
    def _id(self, kind: str, ident: str, denied: list[str]) -> str:
        return self.hasher(kind, ident) if ident in denied else ident

    def _redact_slots(self, slots: dict, denied_m: list[str], denied_g: list[str]) -> dict:
        out = {}
        for name, value in slots.items():
            ref = iri.matter_ref(value)
            if ref and ref in denied_m:
                out[name] = self.hasher("matter", ref)
            elif value in denied_g:
                out[name] = self.hasher("graph", value)
            else:
                out[name] = value
        return out

    def _decisions(self, decision: Decision, lineage_map: dict[str, list[str]]) -> list[dict]:
        denied_m = decision.denied_matters()
        rows = [
            {
                "item": "matter:" + self._id("matter", m, denied_m),
                "allow": d["allow"],
                "rules": [g["rule"] for g in d["grounds"]],
                "reached": "direct",
            }
            for m, d in sorted(decision.matters.items())
        ]
        for g, d in sorted(decision.graphs.items()):
            rows.append(
                {
                    "item": "graph:" + (self.hasher("graph", g) if not d["allow"] else g),
                    "allow": d["allow"],
                    "rules": [x["rule"] for x in d["grounds"]],
                    "reached": "lineage",
                    "via": [
                        self.hasher("matter", m) if not d["allow"] else m
                        for m in lineage_map.get(g, [])
                    ],
                }
            )
        return rows

    @staticmethod
    def _grounds(decision: Decision) -> dict[str, dict]:
        out: dict[str, dict] = {}
        every = list(decision.principal)
        for d in (*decision.matters.values(), *decision.graphs.values()):
            every.extend(d["grounds"])
        for g in every:
            out[g["rule"]] = _public(g)
        return out

    @staticmethod
    def _explain_live(decision: Decision) -> dict:
        rules = Resolver._grounds(decision)
        return {
            "rules": list(rules.values()),
            "blocked": {
                "direct": len(decision.denied_matters()),
                "by_lineage": len(decision.denied_graphs()),
            },
            "policy_version": decision.policy_version,
        }

    # ── explain, from the stored record ─────────────────────────────────────
    def explain(self, persona: str, trace: str) -> dict:
        record = self._record(persona, "explain")
        record["of_trace"] = trace
        asks = (r for r in read(self.writer.path) if r["request"] == "ask")
        found = next((r for r in asks if r.get("trace") == trace), None)
        # The same answer for "not yours" and "does not exist": either would otherwise
        # tell you something about someone else's question.
        if found is None or found.get("persona") != persona:
            record["outcome"] = "refused"
            self._write(record)
            return {"trace": record["trace"], "outcome": "refused",
                    "reason": "No trace of yours with that id."}
        record["outcome"] = "shown"
        self._write(record)
        response = {
            "trace": record["trace"],
            "outcome": "shown",
            "of_trace": trace,
            "asked_at": found["ts"],
            "template": found.get("template"),
            "decided": found.get("outcome"),
            "policy_version": found.get("policy_version"),
        }
        if found.get("disclosure") == "silent":
            response["note"] = "The policy in force does not disclose what was withheld."
            return response
        decisions = found.get("decisions", [])
        response.update(
            rules=list(found.get("grounds", {}).values()),
            blocked={
                "direct": sum(1 for d in decisions if not d["allow"] and d["reached"] == "direct"),
                "by_lineage": sum(
                    1 for d in decisions if not d["allow"] and d["reached"] == "lineage"
                ),
            },
            source="the stored decision record — the same grounds as at the time",
        )
        return response

    # ── passages: the door the permit locks ─────────────────────────────────
    def passages(self, persona: str, permit: str, text: str) -> dict:
        record = self._record(persona, "passages")
        try:
            claims = permit_mod.verify(permit, self.permit_key, persona)
        except permit_mod.PermitError as exc:
            record.update(outcome="refused-permit", reason=str(exc))
            self._write(record)
            return {"trace": record["trace"], "outcome": "refused-permit", "reason": str(exc)}
        # The text is not recorded: it is free text. docs/decisions/0013.
        record.update(
            outcome="no-index",
            permit_trace=claims["trace"],
            returned={"passages": 0},
        )
        self._write(record)
        return {
            "trace": record["trace"],
            "outcome": "no-index",
            "permit_for": claims["trace"],
            "passages": [],
            "note": "The permit is valid. The index it guards arrives in M3; the lock "
            "is fitted before the room exists.",
        }
