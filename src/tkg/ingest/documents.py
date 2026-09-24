"""The firm's documents, written from the ground truth.

Every document is generated from the estate, and the generation manifest records
exactly which facts it carries. That manifest is the gold set: extraction is
scored against it, and it cost no lawyer hours. See docs/decisions/0020.

Three types, each carrying different facts:

    engagement-letter  every matter        forClient · ledBy · matterType
    advice-memo        ~35% of matters     inJurisdiction · workedOn (the team)
    closing-letter     ~80% of closed      hadOutcome · ledBy

Outcomes are in no system of record; a closed matter with no closing letter has
an outcome the lab can never learn, which is the point. The mess is carried
through: some documents name the client as the CRM spells it, not as the
practice-management system does.

Templates, not a language model, write the text: deterministic, reviewable, and
free. The cost is that the prose is more regular than a real firm's, and the
extraction scores are therefore an upper bound — the README says so.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .estate import Estate

FIRM = "Lab Firm LLP"
FOOTER = (
    "SYNTHETIC DOCUMENT — generated for fps4/trusted-knowledge-graph. "
    "No real firm, client or matter."
)
REGULATOR = {"NL": "the AFM", "GB": "the FCA", "DE": "BaFin", "EU": "ESMA"}


@dataclass
class Document:
    doc_id: str
    matter: str
    doc_type: str
    date: str
    title: str
    confidentiality: str
    text: str
    facts: list[dict] = field(default_factory=list)


def _fact(predicate: str, subject: str, obj: str) -> dict:
    return {"predicate": predicate, "subject": subject, "object": obj}


def _labels(cfg: dict, key: str) -> dict[str, str]:
    return {x["id"]: x["label"] for x in cfg[key]}


def build(est: Estate, cfg: dict, seed: int) -> list[Document]:
    rng = random.Random(seed * 7 + 3)
    people = {p.person_ref: p for p in est.people}
    clients = {c.client_ref: c for c in est.clients}
    accounts = {a.account_ref: a for a in est.accounts}
    name = {ref: f"{p.given_name} {p.family_name}" for ref, p in people.items()}
    types = _labels(cfg, "matter_types")
    areas = _labels(cfg, "practice_areas")
    juris = {j["id"]: j["label"] for j in cfg["jurisdictions"]}
    as_of = date.fromisoformat(str(cfg["as_of"]))
    restricted = {r.matter_ref for r in est.restrictions}
    # The demo's matters always carry a memo and, once closed, a closing letter —
    # the scenes depend on them. The draw still happens, so nothing else moves.
    pinned = {m["matter_ref"] for m in cfg.get("pinned", {}).get("matters", [])}
    pinned |= set(cfg.get("pinned", {}).get("outcomes") or {})
    team: dict[str, list[str]] = {}
    for a in est.assignments:
        if a.role != "lead":
            team.setdefault(a.matter_ref, []).append(a.person_ref)

    def client_name(ref: str) -> str:
        account = accounts.get(f"A-{ref.split('-')[1]}")
        if account and account.name != clients[ref].name and rng.random() < 0.3:
            return account.name  # the CRM's spelling — the mess, carried through
        return clients[ref].name

    drafts: list[Document] = []
    for m in est.matters:
        conf = (
            "STRICTLY PRIVATE AND CONFIDENTIAL — RESTRICTED MATTER"
            if m.matter_ref in restricted
            else "Private and confidential"
        )
        type_label = types[m.matter_type]
        lead = name[m.lead_person_ref]

        # ── engagement letter ───────────────────────────────────────────────
        on = m.opened_on + timedelta(days=rng.randint(0, 7))
        who = client_name(m.client_ref)
        body = rng.choice([
            f"Thank you for instructing us in connection with the {type_label.lower()} "
            f"concerning {who}. This letter confirms the terms on which we will act.\n\n"
            f"{lead} will have overall responsibility for the matter, supported by a team "
            f"from our {m.office} office. The work sits within our "
            f"{areas[m.practice_area]} practice and concerns the law of {juris[m.jurisdiction]}.",
            f"We are pleased to confirm that {who} has engaged {FIRM} to act on a "
            f"{type_label.lower()}. Responsibility for the matter rests with {lead}, "
            f"who may be contacted at any time about its progress.\n\n"
            f"Our {m.office} office will staff the matter. Fees will be billed periodically "
            f"on the basis of time spent, in accordance with our standard terms.",
            f"Further to our recent meeting, we write to set out the scope of our engagement "
            f"by {who}. The engagement concerns a {type_label.lower()}.\n\n"
            f"The partner responsible is {lead}. Please direct instructions to {lead.split()[0]} "
            f"in the first instance.",
        ])
        drafts.append(Document(
            "", m.matter_ref, "engagement-letter", on.isoformat(),
            f"Engagement letter — {type_label} — {who}", conf,
            f"Dear Sirs,\n\n{body}\n\nYours faithfully,\n\n{FIRM}",
            [_fact("forClient", m.matter_ref, m.client_ref),
             _fact("ledBy", m.matter_ref, m.lead_person_ref),
             _fact("matterType", m.matter_ref, f"gl:matter-type/{m.matter_type}")],
        ))

        # ── advice memo ────────────────────────────────────────────────────
        members = sorted(team.get(m.matter_ref, []))
        if members and (rng.random() < 0.35 or m.matter_ref in pinned):
            end = min(m.closed_on or as_of, as_of)
            span = max((end - m.opened_on).days, 21)
            on = m.opened_on + timedelta(days=rng.randint(20, span))
            chosen = rng.sample(members, k=min(2, len(members)))
            author = name[chosen[0]]
            helpers = " and ".join(name[p] for p in chosen[1:])
            with_whom = f", with {helpers}," if helpers else ""
            body = rng.choice([
                f"This memorandum summarises our analysis to date. {author}{with_whom} has "
                f"reviewed the position under the law of {juris[m.jurisdiction]} and the "
                f"relevant guidance.\n\nOur preliminary view is set out below for discussion "
                f"with {lead} before anything is sent to the client.",
                f"Prepared by {author}{with_whom} for {lead}. The questions raised are "
                f"governed by the law of {juris[m.jurisdiction]}. We have not yet formed a "
                f"final view and flag the points on which further instructions are needed.",
            ])
            facts = [_fact("inJurisdiction", m.matter_ref, f"id:jurisdiction/{m.jurisdiction}")]
            facts += [_fact("workedOn", m.matter_ref, p) for p in chosen]
            drafts.append(Document(
                "", m.matter_ref, "advice-memo", on.isoformat(),
                f"Memorandum — {type_label} — {client_name(m.client_ref)}", conf,
                f"MEMORANDUM\nTo: {lead}\nFrom: {author}\n\n{body}", facts,
            ))

        # ── closing letter: the only place an outcome is ever written ───────
        outcome = est.outcomes.get(m.matter_ref)
        if outcome and (rng.random() < 0.8 or m.matter_ref in pinned):
            on = m.closed_on + timedelta(days=rng.randint(0, 5))
            regulator = REGULATOR.get(m.jurisdiction, "the regulator")
            fine = rng.randrange(50_000, 2_500_000, 25_000)
            said = {
                "no-action": rng.choice([
                    f"{regulator} has informed us that it has closed its investigation "
                    f"without taking any further action.",
                    f"We are pleased to report that {regulator} will not be pursuing the "
                    f"matter further. No sanction will be imposed.",
                ]),
                "formal-warning": f"{regulator} has concluded its enquiries and issued a "
                f"formal warning. No fine has been imposed.",
                "settled-fine": rng.choice([
                    f"The matter has been resolved by settlement with {regulator}, under which "
                    f"the client pays an administrative fine of EUR {fine:,}.",
                    f"Following negotiation, {regulator} accepted a settlement. The client has "
                    f"agreed to an administrative fine of EUR {fine:,}.",
                ]),
                "fine-imposed": f"{regulator} has imposed a fine of EUR {fine:,}. We have "
                f"advised on the prospects of an objection.",
                "judgment-for": "The court has ruled in the client's favour on all claims.",
                "judgment-against": "The court found against the client. We are considering "
                "the prospects of an appeal.",
                "settled": "The parties have reached a settlement, and the proceedings have "
                "been withdrawn.",
                "completed": "The transaction completed and all conditions have been satisfied.",
                "abandoned": "The client has decided not to proceed, and we have closed our file.",
                "advice-delivered": "We delivered our final advice and have closed our file.",
            }[outcome]
            drafts.append(Document(
                "", m.matter_ref, "closing-letter", on.isoformat(),
                f"Closing letter — {type_label} — {client_name(m.client_ref)}", conf,
                f"Dear Sirs,\n\n{said}\n\nThank you for instructing us on this matter. "
                f"{lead} remains available should any question arise.\n\nYours faithfully,"
                f"\n\n{FIRM}",
                [_fact("hadOutcome", m.matter_ref, f"gl:outcome/{outcome}"),
                 _fact("ledBy", m.matter_ref, m.lead_person_ref)],
            ))

    drafts.sort(key=lambda d: (d.date, d.matter, d.doc_type))
    for n, d in enumerate(drafts, start=1):
        d.doc_id = f"DOC-{n:04d}"
    return drafts


def render_text(d: Document) -> str:
    """The document as a person reads it: header, body, footer."""
    return (
        f"{FIRM}\n{d.confidentiality}\n\nOur ref: {d.matter}\nDocument: {d.doc_id}\n"
        f"Date: {d.date}\n\n{d.title}\n\n{d.text}\n\n{FOOTER}\n"
    )


def write(docs: list[Document], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for d in docs:
            handle.write(json.dumps(asdict(d), ensure_ascii=False, sort_keys=True) + "\n")


def read(path: Path) -> list[Document]:
    return [Document(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()]
