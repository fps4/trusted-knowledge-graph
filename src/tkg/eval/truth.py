"""The right answers, computed from the estate — never from the graph being scored.

Full visibility first; then, for a persona, remove what they are walled from.
Where nothing is left, the right answer is a refusal. `denied` is the same
independent computation the barrier suite uses (leak.expected_denials).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Truth:
    kind: str  # matters | matter | client_matters | client_people | documents | leads
    matters: list[str] = field(default_factory=list)  # every matter the answer turns on
    rows: dict = field(default_factory=dict)  # key -> expected values
    text: str = ""  # the reference answer, in words, for the judge


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

    def compute(self, spec: dict) -> Truth:
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
            text = "; ".join(self._describe(r) for r in refs)
            text = text or "None — the firm has not done this."
            return Truth("matters", refs, rows, text)
        if t == "matter":
            r = spec["matter"]
            m = self.matters[r]
            rows = {r: {"lead": self.people[m.lead_person_ref], "outcome": self.outcome(r),
                        "client": self.clients[m.client_ref].name}}
            return Truth("matter", [r], rows, self._describe(r))
        if t == "client_matters":
            refs = sorted(m.matter_ref for m in self.est.matters
                          if m.client_ref == spec["client"])
            rows = {r: {"lead": self.people[self.matters[r].lead_person_ref],
                        "outcome": self.outcome(r)} for r in refs}
            return Truth("client_matters", refs, rows, "; ".join(self._describe(r) for r in refs))
        if t == "client_people":
            refs = sorted(m.matter_ref for m in self.est.matters
                          if m.client_ref == spec["client"])
            by_matter = {r: sorted({self.people[a.person_ref] for a in self.est.assignments
                                    if a.matter_ref == r}) for r in refs}
            people = sorted({p for ps in by_matter.values() for p in ps})
            return Truth("client_people", refs, by_matter,
                         f"{', '.join(people)} — across {', '.join(refs)}")
        if t == "documents":
            r = spec["matter"]
            docs = sorted(d.doc_id for d in self.docs if d.matter == r)
            return Truth("documents", [r], {r: docs},
                         f"{len(docs)} documents on {r}: {', '.join(docs)}")
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
            return Truth("leads", refs, dict(ranked),
                         ", ".join(f"{n} ({c})" for n, c in ranked) or "Nobody.")
        raise ValueError(f"unknown truth type {t}")
