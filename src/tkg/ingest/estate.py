"""The synthetic firm, generated deterministically from config/estate.yaml.

Same seed, same estate, same identifiers, every time — which is what makes the
demo reproducible and the extraction scoring meaningful later. Nothing here
describes a real firm, person, client or matter.

The mess is generated rather than hand-written, because a firm's mess is
systemic: the same organisation spelled differently in two systems, two lawyers
who share a surname, matters that never closed. Those are the conditions the
design has to survive, so they are conditions of the data, not exceptions in it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

GRADE_WEIGHTS = [("partner", 15), ("counsel", 10), ("knowledge", 5), ("associate", 70)]
OFFICE_JURISDICTION = {
    "Amsterdam": [("NL", 75), ("EU", 20), ("DE", 5)],
    "London": [("GB", 80), ("EU", 15), ("NL", 5)],
    "Frankfurt": [("DE", 75), ("EU", 20), ("GB", 5)],
}


@dataclass
class Person:
    person_ref: str
    given_name: str
    family_name: str
    office: str
    grade: str
    practice_area: str | None
    joined_on: date
    left_on: date | None = None


@dataclass
class Client:
    client_ref: str
    name: str
    client_type: str
    opened_on: date
    crm_name: str | None = None


@dataclass
class Matter:
    matter_ref: str
    client_ref: str
    matter_type: str
    practice_area: str
    jurisdiction: str
    office: str
    lead_person_ref: str
    opened_on: date
    closed_on: date | None = None


@dataclass
class Assignment:
    matter_ref: str
    person_ref: str
    role: str
    from_date: date
    to_date: date | None = None


@dataclass
class Account:
    account_ref: str
    name: str
    account_type: str
    relationship_partner_ref: str | None
    since: date


@dataclass
class Contact:
    contact_ref: str
    account_ref: str
    full_name: str
    job_title: str
    since: date


@dataclass
class Restriction:
    matter_ref: str
    rule_id: str
    kind: str
    set_on: date
    set_by: str


@dataclass
class Estate:
    people: list[Person] = field(default_factory=list)
    clients: list[Client] = field(default_factory=list)
    matters: list[Matter] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    contacts: list[Contact] = field(default_factory=list)
    restrictions: list[Restriction] = field(default_factory=list)


def _as_date(value) -> date | None:
    if value is None:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _weighted(rng: random.Random, pairs: list[tuple[str, int]]) -> str:
    options, weights = zip(*pairs, strict=True)
    return rng.choices(options, weights=weights, k=1)[0]


def _drift(name: str, rng: random.Random) -> str:
    """A plausible other spelling of the same organisation.

    Not corruption — the CRM was filled in by a different person on a different
    day, and this is what that looks like.
    """
    forms = ["Stichting", "N.V.", "B.V.", "plc", "AG", "GmbH", "Group", "Holdings"]
    tokens = name.split()
    if tokens[0] in forms and len(tokens) > 2:
        choice = rng.random()
        if choice < 0.5:
            return " ".join(tokens[1:] + [tokens[0]])
        return " ".join(["St."] + tokens[1:]) if tokens[0] == "Stichting" else " ".join(tokens[1:])
    if tokens[-1] in forms and len(tokens) > 2:
        return " ".join(tokens[:-1])
    return name.replace(" & ", " and ") if " & " in name else name + " Ltd"


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def build(cfg: dict, seed: int) -> Estate:  # noqa: C901 - a generator reads better whole
    rng = random.Random(seed)
    est = Estate()
    vol = cfg["volumes"]
    pools = cfg["name_pools"]
    offices = cfg["offices"]
    areas = [a["id"] for a in cfg["practice_areas"]]
    types = cfg["matter_types"]
    ctypes = [c["id"] for c in cfg["client_types"]]
    pinned = cfg.get("pinned", {})

    # ── people ───────────────────────────────────────────────────────────────
    for p in pinned.get("people", []):
        est.people.append(
            Person(
                person_ref=p["person_ref"],
                given_name=p["given_name"],
                family_name=p["family_name"],
                office=p["office"],
                grade=p["grade"],
                practice_area=p.get("practice_area"),
                joined_on=_as_date(p["joined_on"]),
            )
        )
    combos = [(g, f) for g in pools["given"] for f in pools["family"]]
    rng.shuffle(combos)
    taken = {(p.given_name, p.family_name) for p in est.people}
    idx = 0
    while len(est.people) < vol["lawyers"]:
        given, family = combos[idx]
        idx += 1
        if (given, family) in taken:
            continue
        taken.add((given, family))
        office = rng.choice(offices)
        grade = _weighted(rng, GRADE_WEIGHTS)
        est.people.append(
            Person(
                person_ref=f"P-{200 + len(est.people):04d}",
                given_name=given,
                family_name=family,
                office=office,
                grade=grade,
                practice_area=rng.choice(areas),
                joined_on=date(rng.randint(2005, 2024), rng.randint(1, 12), rng.randint(1, 28)),
            )
        )
    # Make some colleagues share a family name on purpose. Matching on a label is
    # wrong, and the lab should be able to show why rather than assert it.
    fillers = [p for p in est.people if not p.person_ref.startswith("P-01")]
    for i in range(cfg["mess"]["shared_surname_pairs"]):
        if 2 * i + 1 < len(fillers):
            fillers[2 * i + 1].family_name = fillers[2 * i].family_name

    # ── clients ──────────────────────────────────────────────────────────────
    for c in pinned.get("clients", []):
        est.clients.append(
            Client(
                client_ref=c["client_ref"],
                name=c["name"],
                client_type=c["client_type"],
                opened_on=_as_date(c["opened_on"]),
                crm_name=c.get("crm_name"),
            )
        )
    name_combos = [
        (ct, stem, form)
        for ct in ctypes
        for stem in pools["client_stem"]
        for form in pools["client_form"][ct]
    ]
    rng.shuffle(name_combos)
    used_names = {c.name for c in est.clients}
    for ct, stem, form in name_combos:
        if len(est.clients) >= vol["clients"]:
            break
        name = form.replace("{stem}", stem)
        if name in used_names:
            continue
        used_names.add(name)
        est.clients.append(
            Client(
                client_ref=f"C-{1000 + len(est.clients):04d}",
                name=name,
                client_type=ct,
                opened_on=date(rng.randint(2012, 2024), rng.randint(1, 12), rng.randint(1, 28)),
            )
        )

    # ── matters ──────────────────────────────────────────────────────────────
    reserved = {m["matter_ref"] for m in pinned.get("matters", [])}
    for m in pinned.get("matters", []):
        est.matters.append(
            Matter(
                matter_ref=m["matter_ref"],
                client_ref=m["client_ref"],
                matter_type=m["matter_type"],
                practice_area=m["practice_area"],
                jurisdiction=m["jurisdiction"],
                office=m["office"],
                lead_person_ref=m["lead_person_ref"],
                opened_on=_as_date(m["opened_on"]),
                closed_on=_as_date(m.get("closed_on")),
            )
        )
        for r in m.get("restrictions", []) or []:
            est.restrictions.append(
                Restriction(
                    matter_ref=m["matter_ref"],
                    rule_id=r["rule_id"],
                    kind=r["kind"],
                    set_on=_as_date(r["set_on"]),
                    set_by=r["set_by"],
                )
            )

    leads_by_area: dict[str, list[Person]] = {}
    for p in est.people:
        if p.grade in ("partner", "counsel") and p.practice_area:
            leads_by_area.setdefault(p.practice_area, []).append(p)
    years = list(range(vol["first_year"], vol["last_year"] + 1))
    counters = dict.fromkeys(years, 0)
    while len(est.matters) < vol["matters"]:
        year = rng.choice(years)
        counters[year] += 1
        ref = f"M-{year}-{counters[year]:04d}"
        if ref in reserved:
            continue
        mtype = rng.choice(types)
        area = rng.choice(mtype.get("practice_bias") or areas)
        candidates = leads_by_area.get(area) or [p for p in est.people if p.grade == "partner"]
        lead = rng.choice(candidates)
        office = lead.office
        opened = date(year, rng.randint(1, 12), rng.randint(1, 28))
        closed = None
        if rng.random() > vol["open_matter_share"]:
            closed = opened + timedelta(days=rng.randint(30, 900))
            if closed > date(vol["last_year"], 12, 31):
                closed = None
        est.matters.append(
            Matter(
                matter_ref=ref,
                client_ref=rng.choice(est.clients).client_ref,
                matter_type=mtype["id"],
                practice_area=area,
                jurisdiction=_weighted(rng, [tuple(x) for x in OFFICE_JURISDICTION[office]]),
                office=office,
                lead_person_ref=lead.person_ref,
                opened_on=opened,
                closed_on=closed,
            )
        )

    # ── teams, with a validity period on every assignment ────────────────────
    lo, hi = vol["team_size"]
    by_office: dict[str, list[Person]] = {}
    for p in est.people:
        by_office.setdefault(p.office, []).append(p)
    for m in est.matters:
        members = {m.lead_person_ref}
        est.assignments.append(
            Assignment(m.matter_ref, m.lead_person_ref, "lead", m.opened_on, m.closed_on)
        )
        pool = by_office.get(m.office) or est.people
        for _ in range(rng.randint(lo, hi) - 1):
            person = rng.choice(pool)
            if person.person_ref in members:
                continue
            members.add(person.person_ref)
            start = m.opened_on + timedelta(days=rng.randint(0, 60))
            est.assignments.append(
                Assignment(m.matter_ref, person.person_ref, "team", start, m.closed_on)
            )

    # ── CRM: the same organisations, entered by different people ─────────────
    partners = [p for p in est.people if p.grade == "partner"]
    for client in est.clients:
        if client.crm_name is None and rng.random() < cfg["mess"]["crm_missing_share"]:
            continue  # a client the CRM never heard of
        name = client.crm_name
        if name is None:
            name = _drift(client.name, rng) if rng.random() < cfg["mess"]["crm_name_drift"] else client.name
        ref = f"A-{client.client_ref.split('-')[1]}"
        est.accounts.append(
            Account(
                account_ref=ref,
                name=name,
                account_type=client.client_type,
                relationship_partner_ref=rng.choice(partners).person_ref,
                since=client.opened_on,
            )
        )
        for n in range(rng.randint(1, 3)):
            est.contacts.append(
                Contact(
                    contact_ref=f"{ref}-K{n + 1}",
                    account_ref=ref,
                    full_name=f"{rng.choice(pools['given'])} {rng.choice(pools['family'])}",
                    job_title=rng.choice(
                        ["General Counsel", "Head of Compliance", "CFO", "Company Secretary"]
                    ),
                    since=client.opened_on,
                )
            )

    # ── restrictions: five matters behind a barrier, as the spec says ────────
    unrestricted = [m for m in est.matters if m.matter_ref not in {r.matter_ref for r in est.restrictions}]
    while len(est.restrictions) < 5:
        m = rng.choice(unrestricted)
        est.restrictions.append(
            Restriction(
                matter_ref=m.matter_ref,
                rule_id=f"B-{len(est.restrictions) + 10:02d}",
                kind="barrier",
                set_on=m.opened_on + timedelta(days=rng.randint(1, 30)),
                set_by="Risk",
            )
        )
    return est
