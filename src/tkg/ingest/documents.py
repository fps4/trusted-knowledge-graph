"""The firm's documents, written from the ground truth.

Every document is generated from the estate, and the generation manifest records
exactly which facts it carries. That manifest is the gold set: extraction is
scored against it, and it cost no lawyer hours. See docs/decisions/0020.

Four types, each carrying different facts:

    engagement-letter  every matter        forClient · ledBy · matterType
    advice-memo        ~35% of matters     inJurisdiction · workedOn (the team)
    closing-letter     ~80% of closed      hadOutcome · ledBy
    knowledge-note     30, on open matters citesMatter · and the cited matter's
                                           client, type and outcome

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
        # Each variant carries exactly the facts it states — the manifest must not
        # credit a document with a fact it does not say, nor miss one it does.
        body, stated = rng.choice([
            (f"Thank you for instructing us in connection with the {type_label.lower()} "
             f"concerning {who}. This letter confirms the terms on which we will act.\n\n"
             f"{lead} will have overall responsibility for the matter, supported by a team "
             f"from our {m.office} office. The work sits within our "
             f"{areas[m.practice_area]} practice and concerns the law of "
             f"{juris[m.jurisdiction]}.",
             [_fact("inJurisdiction", m.matter_ref, f"id:jurisdiction/{m.jurisdiction}")]),
            (f"We are pleased to confirm that {who} has engaged {FIRM} to act on a "
             f"{type_label.lower()}. Responsibility for the matter rests with {lead}, "
             f"who may be contacted at any time about its progress.\n\n"
             f"Our {m.office} office will staff the matter. Fees will be billed periodically "
             f"on the basis of time spent, in accordance with our standard terms.", []),
            (f"Further to our recent meeting, we write to set out the scope of our engagement "
             f"by {who}. The engagement concerns a {type_label.lower()}.\n\n"
             f"The partner responsible is {lead}. Please direct instructions to "
             f"{lead.split()[0]} in the first instance.", []),
        ])
        drafts.append(Document(
            "", m.matter_ref, "engagement-letter", on.isoformat(),
            f"Engagement letter — {type_label} — {who}", conf,
            f"Dear Sirs,\n\n{body}\n\nYours faithfully,\n\n{FIRM}",
            [_fact("forClient", m.matter_ref, m.client_ref),
             _fact("ledBy", m.matter_ref, m.lead_person_ref),
             _fact("matterType", m.matter_ref, f"gl:matter-type/{m.matter_type}"), *stated],
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
            # The title names the client and the matter type, so the memo states them.
            facts = [_fact("inJurisdiction", m.matter_ref, f"id:jurisdiction/{m.jurisdiction}"),
                     _fact("forClient", m.matter_ref, m.client_ref),
                     _fact("matterType", m.matter_ref, f"gl:matter-type/{m.matter_type}")]
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
                f"{lead}, who led it, remains available should any question arise."
                f"\n\nYours faithfully,"
                f"\n\n{FIRM}",
                [_fact("hadOutcome", m.matter_ref, f"gl:outcome/{outcome}"),
                 _fact("ledBy", m.matter_ref, m.lead_person_ref),
                 # the title's "— <type> — <client>" states these too
                 _fact("forClient", m.matter_ref, m.client_ref),
                 _fact("matterType", m.matter_ref, f"gl:matter-type/{m.matter_type}")],
            ))

    drafts.sort(key=lambda d: (d.date, d.matter, d.doc_type))
    for n, d in enumerate(drafts, start=1):
        d.doc_id = f"DOC-{n:04d}"
    # Knowledge notes come last, from their own random stream and numbered after
    # everything else: adding them moves no existing document, id or byte.
    notes = knowledge_notes(est, cfg, seed)
    for n, d in enumerate(notes, start=len(drafts) + 1):
        d.doc_id = f"DOC-{n:04d}"
    return drafts + notes


# ── knowledge notes: open matters that cite closed ones ──────────────────────
NOTES_PER_RESTRICTED = 3
CONTROL_NOTES = 15


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _outcome_sentence(outcome: str, regulator: str) -> str:
    return {
        "no-action": f"{_cap(regulator)} closed its investigation without taking any action.",
        "formal-warning": f"It ended with a formal warning from {regulator}; no fine was imposed.",
        "settled-fine": f"It was resolved by settlement with {regulator}, the client paying an "
                        "administrative fine.",
        "fine-imposed": f"{_cap(regulator)} imposed a fine on the client.",
        "judgment-for": "The court found for the client on all claims.",
        "judgment-against": "The court found against the client.",
        "settled": "The parties settled, and the proceedings were withdrawn.",
        "completed": "The transaction completed.",
        "abandoned": "The client decided not to proceed, and the matter was abandoned.",
        "advice-delivered": "We delivered our final advice and closed the file.",
    }[outcome]


def knowledge_notes(est: Estate, cfg: dict, seed: int) -> list[Document]:
    """Precedent notes: filed on an OPEN, unrestricted matter, citing a closed one by
    its file number, with that matter's client and true outcome.

    The realistic leak. The note sits on an open matter, so the DMS — and any filter
    on a passage's own matter — lets it through; the matter it cites may be walled.
    Three notes cite each restricted matter, and fifteen cite unrestricted ones as a
    control. docs/decisions/0028.

    A note is written by the knowledge lawyer (grade `knowledge`) — except one citing
    a restricted matter, which only someone inside it could write: that one is
    written by the precedent's lead partner. Own random stream, drawn after
    everything else, so no other document moves.
    """
    rng = random.Random(seed * 13 + 11)
    people = {p.person_ref: f"{p.given_name} {p.family_name}" for p in est.people}
    knowledge = sorted(p.person_ref for p in est.people if p.grade == "knowledge")
    clients = {c.client_ref: c.name for c in est.clients}
    types = _labels(cfg, "matter_types")
    as_of = date.fromisoformat(str(cfg["as_of"]))
    restricted = [r.matter_ref for r in est.restrictions]
    matters = {m.matter_ref: m for m in est.matters}
    hosts_all = sorted(
        (m for m in est.matters if m.closed_on is None and m.matter_ref not in restricted),
        key=lambda m: m.matter_ref,
    )
    used: set[str] = set()

    def hosts_for(cited) -> list:
        free = [m for m in hosts_all if m.matter_ref not in used
                and m.matter_type == cited.matter_type]
        near = [m for m in free if m.jurisdiction == cited.jurisdiction]
        return near if len(near) >= NOTES_PER_RESTRICTED else free

    pairs: list[tuple] = []
    for ref in restricted:
        cited = matters[ref]
        for host in rng.sample(hosts_for(cited), k=NOTES_PER_RESTRICTED):
            used.add(host.matter_ref)
            pairs.append((host, cited))
    closed = sorted(ref for ref in est.outcomes if ref not in restricted)
    for ref in rng.sample(closed, k=len(closed)):
        if len(pairs) >= NOTES_PER_RESTRICTED * len(restricted) + CONTROL_NOTES:
            break
        cited = matters[ref]
        options = hosts_for(cited)
        if not options:
            continue
        host = rng.choice(options)
        used.add(host.matter_ref)
        pairs.append((host, cited))

    notes: list[Document] = []
    for host, cited in pairs:
        outcome = est.outcomes[cited.matter_ref]
        type_label = types[host.matter_type].lower()
        a_type = f"{'an' if type_label[0] in 'aeiou' else 'a'} {type_label}"
        author = (people[cited.lead_person_ref] if cited.matter_ref in restricted
                  else people[knowledge[0]] if knowledge else "Knowledge team")
        on = max(host.opened_on, cited.closed_on) + timedelta(days=rng.randint(7, 60))
        on = min(on, as_of)
        said = _outcome_sentence(outcome, REGULATOR.get(cited.jurisdiction, "the regulator"))
        client = clients[cited.client_ref]
        body = rng.choice([
            f"We were asked for precedent from the firm's own files for this {type_label}. "
            f"The closest is our matter {cited.matter_ref}, {a_type} for {client}. "
            f"{said}\n\nThe working papers are on the file under that reference; ask the "
            f"partner who ran it before relying on them.",
            f"Precedent for this {type_label}: our matter {cited.matter_ref}, {a_type} "
            f"for {client}. {said}\n\nThe approach taken there is a useful starting point. "
            f"Quote the file number when asking for the working papers.",
        ])
        notes.append(Document(
            "", host.matter_ref, "knowledge-note", on.isoformat(),
            f"Knowledge note — precedent for this {type_label}", "Private and confidential",
            f"KNOWLEDGE NOTE\nTo: {people[host.lead_person_ref]}\nFrom: {author}\n\n{body}",
            # Exactly what the note says: this matter's type, that it cites the other,
            # and the cited matter's type, client and outcome — subject the cited matter.
            [_fact("matterType", host.matter_ref, f"gl:matter-type/{host.matter_type}"),
             _fact("citesMatter", host.matter_ref, cited.matter_ref),
             _fact("matterType", cited.matter_ref, f"gl:matter-type/{cited.matter_type}"),
             _fact("forClient", cited.matter_ref, cited.client_ref),
             _fact("hadOutcome", cited.matter_ref, f"gl:outcome/{outcome}")],
        ))
    notes.sort(key=lambda d: (d.date, d.matter))
    return notes


def cited_matters(doc: Document) -> list[str]:
    """What a document cites, per its manifest — the ground truth, not the extraction."""
    return sorted({f["object"] for f in doc.facts if f["predicate"] == "citesMatter"})


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
