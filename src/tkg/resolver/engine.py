"""The resolver: seven steps, one decision, one record.

A question arrives as a competency question and its slots, from a persona whose
identity was verified before this code runs. The steps, in the architecture's
order:

1. Plan          — which competency question, and whether it turns on a glossary term.
2. Resolve terms — against g:glossary: owners, readings, what an ambiguous term gets.
3. Route         — graph · index · hybrid · refuse, with the reason. docs/decisions/0017.
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

import re
import secrets
from datetime import UTC, datetime, timedelta

from .. import __version__, iri
from ..access import permit as permit_mod
from ..access.decide import Decision, Opa, PolicyUnavailable, lineage
from ..audit.chain import Hasher, Writer, read
from ..audit.queries import AuditReader
from ..ingest.loader import Fuseki
from ..semantic import glossary
from ..semantic.router import route
from ..semantic.templates import TEMPLATES, TERM_QUESTIONS, SlotError, Template

URL_TTL = timedelta(minutes=5)

PIPELINE_VERSION = f"tkg {__version__}"

MATTER_REF = re.compile(r"^M-\d{4}-\d{4}$")


def _listed() -> list[Template]:
    return [t for t in TEMPLATES.values() if t.listed]


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
        stores=None,
        index=None,
        embed=None,
    ) -> None:
        # stores(persona) -> a document-store client holding *that persona's*
        # credentials; index/embed are None until the index exists (M3).
        self.stores = stores
        self.index = index
        self.embed = embed
        self.fuseki = fuseki
        self.opa = opa
        self.writer = writer
        self.hasher = hasher
        self.permit_key = permit_key
        self.personas = personas
        self.reader = AuditReader(writer.path, hasher, fuseki)

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
    def ask(
        self,
        persona: str,
        template_id: str,
        params: dict[str, str] | None,
        terms: list[str] | None = None,
    ) -> dict:
        record = self._record(persona, "ask")
        record["template"] = template_id
        try:
            response = self._ask(persona, template_id, dict(params or {}), terms or [], record)
        except PolicyUnavailable as exc:
            record.update(outcome="refused-policy-unavailable", reason=str(exc)[:200])
            response = {
                "outcome": "refused-policy-unavailable",
                "reason": "The policy engine did not answer, so nothing was decided and "
                "nothing is returned. The resolver never decides on its own.",
            }
        self._write(record)
        return {"trace": record["trace"], "persona": persona, **response}

    def _ask(self, persona: str, template_id: str, params: dict, terms: list[str],
             record: dict) -> dict:
        # ── step 1 · plan: which question, and does it turn on a term ──────
        question = TERM_QUESTIONS.get(template_id)
        template: Template | None = None if question else TEMPLATES.get(template_id)
        if question is None and template is None:
            known = ", ".join(sorted(list(TERM_QUESTIONS) + [t.id for t in _listed()]))
            record.update(outcome="refused-invalid", reason="no such competency question")
            return {"outcome": "refused-invalid", "reason": f"no such question. Known: {known}"}

        # ── step 2 · resolve terms against the glossary graph ──────────────
        used = []
        for term_id in terms:
            term = glossary.by_id(self.fuseki, term_id)
            if term is None:
                record.update(outcome="refused-invalid", reason="unknown glossary term")
                return {"outcome": "refused-invalid",
                        "reason": f"{term_id!r} is not a term in the glossary"}
            used.append({"term": term.id, "owner": term.owner})
        ambiguous, term = None, None
        if question:
            term = glossary.by_id(self.fuseki, question.term)
            key = params.pop("reading", None)
            reading = next((r for r in term.readings if r.key == key), None)
            if reading is None and key:
                keys = ", ".join(r.key for r in term.readings)
                record.update(outcome="refused-invalid", reason="no such reading")
                return {"outcome": "refused-invalid",
                        "reason": f"{term.label!r} has no reading {key!r}. Readings: {keys}"}
            if reading is None and (term.on_ambiguous or "").startswith("default:"):
                wanted = term.on_ambiguous.split(":", 1)[1]
                reading = next(r for r in term.readings if r.key == wanted)
            if reading is None:
                ambiguous = (
                    f"'{term.label}' has {len(term.readings)} readings with different owners, "
                    f"and the question did not choose one (on_ambiguous: {term.on_ambiguous})"
                )
            else:
                template = TEMPLATES[reading.template]
                record["question_id"] = question.id
            used.append({"term": term.id, "reading": reading.key if reading else None,
                         "owner": reading.owner if reading else term.owner})
        record["terms"] = used

        # ── step 3 · route ─────────────────────────────────────────────────
        chosen = route(template.needs if template else "facts", template_id, ambiguous,
                       index_available=self._index_ready())
        record["route"] = chosen.public()
        if chosen.route == "refuse":
            outcome = "refused-ambiguous" if ambiguous else "refused-no-index"
            record["outcome"] = outcome
            response = {"template": template_id, "outcome": outcome, "route": chosen.public(),
                        "reason": chosen.reason, "terms": used}
            if ambiguous and term.on_ambiguous == "ask":
                response["readings"] = [r.__dict__ for r in term.readings]
                response["reason"] += ". Choose one: ask again with slots {'reading': <key>}."
            return response

        # ── step 4 · bind ─────────────────────────────────────────────────
        try:
            slots = template.check_slots(params)
        except SlotError as exc:
            # The rejected value is not recorded: it may be free text.
            record.update(outcome="refused-invalid", reason="slot refused")
            return {"outcome": "refused-invalid", "reason": str(exc)}

        response = self._answer(persona, record["trace"], template, slots, record)
        response.update(route=chosen.public(), terms=used)
        if question:
            response["question_id"] = question.id
        return response

    def _answer(self, persona: str, trace: str, template: Template, slots: dict,
                part: dict) -> dict:
        """Steps 5 to 7 for one template. Writes what it decided into `part`."""
        part["template"] = template.id
        # ── step 5 · decide ────────────────────────────────────────────────
        cand_matters, cand_graphs = self._candidates(template, slots)
        lineage_map = lineage(self.fuseki, cand_graphs)
        principal = self.personas[persona]["principal"]
        decision = self.opa.decide(principal, cand_matters, lineage_map)
        denied_m, denied_g = decision.denied_matters(), decision.denied_graphs()
        permitted_m = [m for m in cand_matters if m not in denied_m]
        permitted_g = [g for g in cand_graphs if g not in denied_g]

        part.update(
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
            part.update(outcome="refused", returned={"rows": 0})
            return {
                **base,
                "outcome": "refused",
                "explain": {"rules": [_public(g) for g in decision.principal]},
            }

        denied_any = bool(denied_m or denied_g)
        if template.kind == "aggregate" and denied_any and withholding:
            part.update(outcome="refused-aggregate", returned={"rows": 0})
            return {
                **base,
                "outcome": "refused-aggregate",
                "reason": "This is a count over a set that includes matters you cannot see. "
                "Computed over the rest it would be wrong in a way you could not detect.",
                "explain": explain,
            }

        # ── step 6 · passages: M3. The permit below will guard them. ───────
        # ── step 7 · compose, from the permitted set only ──────────────────
        query = template.bind(slots, [iri.matter(m) for m in permitted_m], permitted_g)
        rows, cited = self._run(template, query)

        if denied_any and withholding:
            outcome = "refused" if not rows else "answered-with-withheld"
        else:
            outcome = "answered"
        scope = None
        if template.kind == "aggregate" and denied_any:
            scope = "Computed over the matters you can see."

        permit_token, permit_exp = None, None
        if rows and template.kind == "rows":
            permit_token, permit_exp = permit_mod.mint(
                persona, trace, permitted_m, permitted_g, self.permit_key
            )
        sources = self._sources(persona, cited, rows)
        passages = []
        if template.needs in ("passages", "both") and self._index_ready() and permitted_m:
            passages = self._search(persona, template.passage_query or template.question,
                                    permitted_m)
        returned = {
            "rows": len(rows),
            "matters": sorted({r["matterRef"] for r in rows if r.get("matterRef")}),
            "graphs": cited,
            "permit": {"exp": permit_exp} if permit_token else None,
            # What was minted, never the signature: the object key and its expiry.
            "links": [{"key": x["key"], "exp": x["expires"]} for x in sources],
        }
        if passages:
            returned["passages"] = [p["chunk_id"] for p in passages]
            returned["passage_matters"] = sorted({p["matter_id"] for p in passages})
        if template.kind == "aggregate":
            # What the count was computed over — "shown" in the only sense an
            # aggregate shows anything. The subject-centred audit needs it.
            returned["counted"] = sorted(permitted_m)
        part.update(outcome=outcome, returned=returned)
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
        if sources:
            response["sources"] = sources
        if passages:
            response["passages"] = passages
        if denied_any and withholding:
            response["explain"] = explain
        if permit_token:
            response["permit"] = permit_token
            response["permit_expires"] = datetime.fromtimestamp(permit_exp, UTC).isoformat(
                timespec="seconds"
            )
        return response

    # ── resolve_term: what a word means here, and who says so ───────────────
    def resolve_term(self, persona: str, text: str) -> dict:
        record = self._record(persona, "resolve_term")
        try:
            terms = glossary.lookup(self.fuseki, text)
            concepts = [] if terms else glossary.concepts(self.fuseki, text)
        except glossary.TermError as exc:
            # The text is not recorded: it is free text. docs/decisions/0013.
            record.update(outcome="refused-invalid", reason="not a term")
            self._write(record)
            return {"trace": record["trace"], "outcome": "refused-invalid", "reason": str(exc)}
        if not terms:
            record.update(outcome="concept" if concepts else "unknown",
                          matched=[c["concept"] for c in concepts])
            self._write(record)
            return {
                "trace": record["trace"],
                "outcome": "concept" if concepts else "unknown",
                "concepts": concepts,
                "note": "Not a business term. " + (
                    "It is a concept in a vocabulary; use it as a slot value."
                    if concepts else
                    "Nothing in the glossary or the vocabularies has that name, and a "
                    "question is not answered from a guess at what it means."
                ),
            }
        term = terms[0]
        record.update(term=term.id, readings=[])
        readings = []
        try:
            for r in term.readings:
                template = TEMPLATES[r.template]
                part = {"reading": r.key, "owner": r.owner}
                answer = self._answer(persona, record["trace"], template,
                                      template.check_slots({}), part)
                record["readings"].append(part)
                readings.append({
                    **r.__dict__,
                    "count": answer["rows"][0]["n"] if answer.get("rows") else None,
                    "outcome": answer["outcome"],
                    **({"scope": answer["scope"]} if answer.get("scope") else {}),
                    **({"explain": answer["explain"]} if answer.get("explain") else {}),
                })
        except PolicyUnavailable as exc:
            record.update(outcome="refused-policy-unavailable", reason=str(exc)[:200])
            self._write(record)
            return {"trace": record["trace"], "outcome": "refused-policy-unavailable"}
        record["outcome"] = "resolved"
        self._write(record)
        body = term.public()
        body["readings"] = readings
        return {
            "trace": record["trace"],
            "persona": persona,
            "outcome": "resolved",
            **body,
            "note": (
                "Each count is decided for you, like any other answer."
                if readings else "Use `means` as slot values; pass the term id in `terms`."
            ),
        }

    # ── the document store and the index ───────────────────────────────────
    def _index_ready(self) -> bool:
        return self.index is not None and self.index.exists()

    def _object_keys(self, doc_ids: list[str]) -> dict[str, str]:
        if not doc_ids:
            return {}
        values = " ".join(f"<{iri.document(d)}>" for d in doc_ids)
        query = iri.PREFIXES + (
            f"SELECT ?doc ?key WHERE {{ GRAPH <{iri.G_SPINE_DMS}> {{ VALUES ?doc {{ {values} }} "
            "?doc ssf:objectKey ?key } }"
        )
        rows = self.fuseki.query(query)["results"]["bindings"]
        return {r["doc"]["value"].rsplit("/", 1)[-1]: r["key"]["value"] for r in rows}

    def _sources(self, persona: str, cited: list[str], rows: list[dict]) -> list[dict]:
        """A link that opens the source — for documents the decision already permitted.

        Minted with the asking persona's own document-store credentials, so the store
        checks them again, on its own policy. There is no tool that turns an id into
        bytes; the link rides on the citation. docs/decisions/0021.
        """
        if self.stores is None:
            return []
        docs = {g.rsplit("/", 1)[-1] for g in cited if g.startswith("g:doc/")}
        docs |= {r["docId"] for r in rows if r.get("docId")}
        keys = self._object_keys(sorted(docs))
        if not keys:
            return []
        store = self.stores(persona)
        expires = (datetime.now(UTC) + URL_TTL).isoformat(timespec="seconds")
        return [
            {"document": d, "key": k, "url": store.presign(k), "expires": expires}
            for d, k in sorted(keys.items())
        ]

    def _search(self, persona: str, text: str, matters: list[str], k: int = 5) -> list[dict]:
        """Passages, pre-filtered to the permitted matters — never filtered afterwards."""
        hits = self.index.search(text, self.embed([text])[0], matters, k=k)
        store = self.stores(persona) if self.stores else None
        for h in hits:
            if store is not None:
                h["source_url"] = store.presign(f"doc/{h['matter_id']}/{h['doc_id']}.pdf")
        return hits

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
        if not self._index_ready():
            record.update(outcome="no-index", permit_trace=claims["trace"],
                          returned={"passages": 0})
            self._write(record)
            return {"trace": record["trace"], "outcome": "no-index",
                    "permit_for": claims["trace"], "passages": [],
                    "note": "The permit is valid; the index is not loaded."}
        hits = self._search(persona, text or "", claims["matters"]) if claims["matters"] else []
        record.update(
            outcome="answered",
            permit_trace=claims["trace"],
            returned={"passages": [h["chunk_id"] for h in hits],
                      "passage_matters": sorted({h["matter_id"] for h in hits}),
                      "links": len(hits)},
        )
        self._write(record)
        return {
            "trace": record["trace"],
            "outcome": "answered",
            "permit_for": claims["trace"],
            "filter": f"{len(claims['matters'])} permitted matters, applied inside the query",
            "passages": hits,
        }

    # ── the record, read by Risk — and only by Risk ─────────────────────────
    def _audit(self, persona: str, request: str, subject: dict, answer) -> dict:
        record = self._record(persona, request)
        record.update(subject)
        try:
            allowed, grounds = self.opa.may_read_record(self.personas[persona]["principal"])
        except PolicyUnavailable as exc:
            record.update(outcome="refused-policy-unavailable", reason=str(exc)[:200])
            self._write(record)
            return {"trace": record["trace"], "outcome": "refused-policy-unavailable"}
        if not allowed:
            record.update(outcome="refused", rules=[g["rule"] for g in grounds])
            self._write(record)
            return {"trace": record["trace"], "outcome": "refused",
                    "explain": {"rules": [_public(g) for g in grounds]}}
        result = answer()
        if result is None:
            record["outcome"] = "not-found"
            self._write(record)
            return {"trace": record["trace"], "outcome": "not-found"}
        # Risk's reads go into the same chain, by the same writer. What Risk asked
        # about is hashed like any other matter identifier: the reader is
        # authorised, the record of the reading is not a directory of the walls.
        record["outcome"] = "shown"
        self._write(record)
        return {"trace": record["trace"], "outcome": "shown", **result}

    def audit_subject(self, persona: str, matter_ref: str) -> dict:
        if not MATTER_REF.match(matter_ref or ""):
            return {"outcome": "refused-invalid", "reason": "expected a matter like M-2022-0117"}
        return self._audit(
            persona, "audit.subject", {"subject": self.hasher("matter", matter_ref)},
            lambda: self.reader.subject(matter_ref),
        )

    def audit_person(self, persona: str, person: str, since: str | None,
                     until: str | None) -> dict:
        if person not in self.personas:
            return {"outcome": "refused-invalid", "reason": f"no persona {person!r}"}
        try:
            for value in (since, until):
                if value:
                    datetime.fromisoformat(value)
        except ValueError:
            return {"outcome": "refused-invalid", "reason": "since/until: ISO 8601 timestamps"}
        return self._audit(
            persona, "audit.person", {"about": person, "since": since, "until": until},
            lambda: self.reader.person(person, since, until),
        )

    def audit_trace(self, persona: str, trace: str) -> dict:
        if not re.match(r"^t-[0-9a-f]{8}$", trace or ""):
            return {"outcome": "refused-invalid", "reason": "expected a trace like t-1a2b3c4d"}
        return self._audit(
            persona, "audit.trace", {"of_trace": trace},
            lambda: (lambda r: None if r is None else {"record": r})(self.reader.trace(trace)),
        )
