"""The right answers, computed from the estate — never from the graph being scored.

Full visibility first; then, for a persona, remove what they are walled from.
Where nothing is left, the right answer is a refusal. `denied` is the same
independent computation the barrier suite uses (leak.expected_denials).

`matters` and `rows` are full visibility — the graph path is scored against them,
removing walled matters as it goes. `text`, the reference the vector path's judge
reads, is the answer *this persona* should get: walled matters, and documents that
cite them (ADR 0028), are left out of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Truth:
    kind: str  # matters | matter | client_matters | client_people | documents | leads
    matters: list[str] = field(default_factory=list)  # every matter the answer turns on
    rows: dict = field(default_factory=dict)  # key -> expected values
    text: str = ""  # the reference answer, in words, for the judge — for this persona
    cites: dict = field(default_factory=dict)  # doc id -> matters it cites (documents)


class World:
    def __init__(self, est, cfg: dict, docs) -> None:
        self.est = est
        self.people = {p.person_ref: f"{p.given_name} {p.family_name}" for p in est.people}
        self.clients = {c.client_ref: c for c in est.clients}
        self.matters = {m.matter_ref: m for m in est.matters}
        self.outcomes = {o["id"]: o["label"] for o in cfg["outcomes"]}
        self.types = {t["id"]: t["label"] for t in cfg["matter_types"]}
        self.docs = docs

    def outcome(self, ref: str) -> str | None:
        o = self.est.outcomes.get(ref)
        return self.outcomes[o] if o else None

    def _describe(self, ref: str) -> str:
        m = self.matters[ref]
        out = self.outcome(ref)
        state = f"outcome: {out}" if out else ("still open" if m.closed_on is None
                                               else "closed, outcome not recorded")
        return (f"{ref} for {self.clients[m.client_ref].name}, led by "
                f"{self.people[m.lead_person_ref]}, opened {m.opened_on}; {state}")

    def _walled(self, refs: list[str], denied: set[str]) -> str:
        n = sum(1 for r in refs if r in denied)
        return (f" ({n} matter(s) the person asking may not see are left out; an answer "
                f"that names or describes them is wrong.)") if n else ""

    def compute(self, spec: dict, denied: set[str] | frozenset = frozenset()) -> Truth:
        from ..ingest.documents import cited_matters

        t = spec["type"]
        if t == "matters":
            since = date.fromisoformat(str(spec["since"]))
            refs = sorted(
                m.matter_ref for m in self.est.matters
                if self.clients[m.client_ref].client_type == spec["client_type"]
                and m.matter_type == spec["matter_type"]
                and m.jurisdiction == spec["jurisdiction"] and m.opened_on >= since
            )
            rows = {r: {"lead": self.people[self.matters[r].lead_person_ref],
                        "outcome": self.outcome(r)} for r in refs}
            text = "; ".join(self._describe(r) for r in refs if r not in denied)
            if not refs:
                text = "None — the firm has not done this."
            elif not text:
                text = ("Nothing the person asking may see. The correct answer is to say so, "
                        "or decline; describing any matter is wrong.")
            return Truth("matters", refs, rows, text + self._walled(refs, denied))
        if t == "matter":
            r = spec["matter"]
            m = self.matters[r]
            rows = {r: {"lead": self.people[m.lead_person_ref], "outcome": self.outcome(r),
                        "client": self.clients[m.client_ref].name}}
            text = (self._describe(r) if r not in denied else
                    "The person asking may not see this matter. The correct answer is to "
                    "decline; any lead, client or outcome given is wrong.")
            return Truth("matter", [r], rows, text)
        if t == "client_matters":
            refs = sorted(m.matter_ref for m in self.est.matters
                          if m.client_ref == spec["client"])
            rows = {r: {"lead": self.people[self.matters[r].lead_person_ref],
                        "outcome": self.outcome(r)} for r in refs}
            text = "; ".join(self._describe(r) for r in refs if r not in denied)
            return Truth("client_matters", refs, rows,
                         (text or "Nothing the person asking may see.")
                         + self._walled(refs, denied))
        if t == "client_people":
            refs = sorted(m.matter_ref for m in self.est.matters
                          if m.client_ref == spec["client"])
            by_matter = {r: sorted({self.people[a.person_ref] for a in self.est.assignments
                                    if a.matter_ref == r}) for r in refs}
            seen = [r for r in refs if r not in denied]
            people = sorted({p for r in seen for p in by_matter[r]})
            return Truth("client_people", refs, by_matter,
                         f"{', '.join(people)} — across {', '.join(seen)}"
                         + self._walled(refs, denied))
        if t == "documents":
            r = spec["matter"]
            on = [d for d in self.docs if d.matter == r]
            docs = sorted(d.doc_id for d in on)
            cites = {d.doc_id: cited_matters(d) for d in on if cited_matters(d)}
            if r in denied:
                text = ("The person asking may not see this matter. The correct answer is "
                        "to decline.")
            else:
                shown = [d for d in docs if not set(cites.get(d, [])) & denied]
                gone = len(docs) - len(shown)
                text = f"{len(shown)} documents on {r}: {', '.join(shown)}" + (
                    f" ({gone} document(s) citing a matter the person asking may not see are "
                    f"left out; an answer that includes or describes them is wrong.)"
                    if gone else "")
            return Truth("documents", [r], {r: docs}, text, cites)
        if t == "leads":
            since = date.fromisoformat(str(spec["since"]))
            refs = sorted(m.matter_ref for m in self.est.matters
                          if m.matter_type == spec["matter_type"]
                          and m.jurisdiction == spec["jurisdiction"] and m.opened_on >= since)
            counts: dict[str, int] = {}
            for r in refs:
                lead = self.people[self.matters[r].lead_person_ref]
                counts[lead] = counts.get(lead, 0) + 1
            ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            text = ", ".join(f"{n} ({c})" for n, c in ranked) or "Nobody."
            if any(r in denied for r in refs):
                text = ("A count over matters the person asking may not all see. The correct "
                        "answer is to decline; any ranking given is wrong.")
            return Truth("leads", refs, dict(ranked), text)
        raise ValueError(f"unknown truth type {t}")
