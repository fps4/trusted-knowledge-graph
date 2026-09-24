"""barriers.yaml + people.yaml + the systems of record → the data OPA evaluates.

The Rego is written by hand (policy/access.rego); this compiles only its data.
Three sources meet here and the compiler refuses to write a policy when they
disagree — which is the point of compiling rather than copying:

- the rules, from config/barriers.yaml — the only place a rule may be written;
- the restriction records, from pms.matter_restriction — the evidence that a
  rule exists in the firm's own system;
- who a person is, and who is on each matter team, from hr and pms.

See docs/decisions/0007 and 0008.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

SOURCE = "config/barriers.yaml"
KINDS = {"barrier", "need-to-know"}


class PolicyError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("policy refused:\n  " + "\n  ".join(problems))


@dataclass(frozen=True)
class Records:
    """What the systems of record say. Read-only, read as tkg_ro."""

    restrictions: list[dict]  # matter_ref, rule_id, kind
    teams: dict[str, set[str]]  # matter_ref -> person_refs
    people: dict[str, dict]  # person_ref -> {grade, office, practice_area}


def read_records(dsn: str) -> Records:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute("SELECT matter_ref, rule_id, kind FROM pms.matter_restriction")
        restrictions = list(cur.fetchall())
        cur.execute("SELECT matter_ref, person_ref FROM pms.matter_team")
        teams: dict[str, set[str]] = {}
        for row in cur.fetchall():
            teams.setdefault(row["matter_ref"], set()).add(row["person_ref"])
        cur.execute("SELECT person_ref, grade, office, practice_area FROM hr.person")
        people = {row["person_ref"]: dict(row) for row in cur.fetchall()}
    return Records(restrictions=restrictions, teams=teams, people=people)


def _day(value) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def compile_policy(barriers: dict, personas: dict, records: Records) -> dict:
    problems: list[str] = []

    # ── rules against the restriction records, both directions ──────────────
    recorded = {r["rule_id"]: r for r in records.restrictions}
    rules = {r["id"]: r for r in barriers.get("rules", [])}
    if len(rules) != len(barriers.get("rules", [])):
        problems.append("a rule id appears twice in barriers.yaml")
    for rule_id, rule in rules.items():
        row = recorded.get(rule_id)
        if row is None:
            problems.append(
                f"{rule_id}: in barriers.yaml but not in pms.matter_restriction — "
                "a rule the firm's records have never heard of"
            )
            continue
        if row["matter_ref"] != rule["matter"]:
            problems.append(
                f"{rule_id}: barriers.yaml says {rule['matter']}, "
                f"the system of record says {row['matter_ref']}"
            )
        if row["kind"] != rule["kind"]:
            problems.append(
                f"{rule_id}: barriers.yaml says {rule['kind']}, "
                f"the system of record says {row['kind']}"
            )
        if rule["kind"] not in KINDS:
            problems.append(f"{rule_id}: unknown kind {rule['kind']!r}")
    for rule_id, row in recorded.items():
        if rule_id not in rules:
            problems.append(
                f"{rule_id}: restricts {row['matter_ref']} in the system of record "
                "but has no rule in barriers.yaml — nothing would enforce it"
            )

    # ── principals: who they are comes from HR, not from this file ───────────
    principals: dict[str, dict] = {}
    for p in personas.get("personas", []):
        entry = {
            "persona": p["id"],
            "kind": p["kind"],
            "role": p.get("role"),
            "person": None,
            "practice_area": None,
            "office": None,
        }
        ref = p.get("person_ref")
        if ref:
            hr = records.people.get(ref)
            if hr is None:
                problems.append(f"persona {p['id']}: {ref} is not in hr.person")
            else:
                entry.update(
                    person=ref, practice_area=hr["practice_area"], office=hr["office"]
                )
        elif p["kind"] == "person" and p.get("role") is None:
            problems.append(f"persona {p['id']}: a person persona needs a person_ref")
        principals[p["principal"]] = entry

    # ── restrictions, with insiders resolved against the matter team ─────────
    restrictions: dict[str, list[dict]] = {}
    for rule_id in sorted(rules):
        rule = rules[rule_id]
        insiders: set[str] = set(rule.get("insiders", {}).get("people", []) or [])
        if rule.get("insiders", {}).get("matter_team"):
            insiders |= records.teams.get(rule["matter"], set())
        screened = rule.get("screened", {}) or {}
        named = set(screened.get("people", []) or [])
        both = sorted(named & insiders)
        if both:
            problems.append(
                f"{rule_id}: {', '.join(both)} is both inside and screened — a contradiction, "
                "not a precedence question"
            )
        for ref in named:
            if ref not in records.people:
                problems.append(f"{rule_id}: screens {ref}, who is not in hr.person")
        restrictions.setdefault(rule["matter"], []).append(
            {
                "rule": rule_id,
                "kind": rule["kind"],
                "insiders": sorted(insiders),
                "screened": {
                    "people": sorted(named),
                    "practice_areas": sorted(screened.get("practice_areas", []) or []),
                    "offices": sorted(screened.get("offices", []) or []),
                },
                "owner": rule["owner"],
                "set_on": _day(rule["set_on"]),
                "set_by": rule["set_by"],
                "review": rule.get("review"),
                "source": SOURCE,
            }
        )

    if barriers.get("disclosure") not in {"withheld-count", "silent"}:
        problems.append(
            f"disclosure: expected withheld-count or silent, got {barriers.get('disclosure')!r}"
        )

    if problems:
        raise PolicyError(problems)

    baseline = {
        b["id"]: {
            "rule": b["id"],
            "kind": "identity",
            "text": b["rule"],
            "owner": b["owner"],
            "set_on": _day(b["set_on"]),
            "source": SOURCE,
        }
        for b in barriers.get("baseline", [])
    }
    body = {
        "disclosure": barriers["disclosure"],
        "source": SOURCE,
        "baseline": baseline,
        "principals": principals,
        "restrictions": restrictions,
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]
    return {"barriers": {"policy_version": f"{_day(barriers['version'])}+{digest}", **body}}


def compile_files(config_dir: Path, records: Records) -> dict:
    barriers = yaml.safe_load((config_dir / "barriers.yaml").read_text())
    personas = yaml.safe_load((config_dir / "people.yaml").read_text())
    return compile_policy(barriers, personas, records)


def write(data: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
