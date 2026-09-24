"""Write the generated estate into the systems of record.

This is the only thing in the lab that writes to Postgres, and it runs as the
admin role. Everything downstream reads as tkg_ro, which cannot write at all.
"""

from __future__ import annotations

import psycopg

from .estate import Estate

TABLES = [
    "pms.matter_restriction",
    "pms.matter_team",
    "pms.matter",
    "pms.client",
    "crm.contact",
    "crm.account",
    "hr.person",
]


def seed(admin_dsn: str, est: Estate) -> dict[str, int]:
    with psycopg.connect(admin_dsn) as conn, conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")

        cur.executemany(
            "INSERT INTO hr.person (person_ref, given_name, family_name, office, grade,"
            " practice_area, joined_on, left_on) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            [
                (p.person_ref, p.given_name, p.family_name, p.office, p.grade,
                 p.practice_area, p.joined_on, p.left_on)
                for p in est.people
            ],
        )
        cur.executemany(
            "INSERT INTO pms.client (client_ref, name, client_type, opened_on)"
            " VALUES (%s,%s,%s,%s)",
            [(c.client_ref, c.name, c.client_type, c.opened_on) for c in est.clients],
        )
        cur.executemany(
            "INSERT INTO pms.matter (matter_ref, client_ref, matter_type, practice_area,"
            " jurisdiction, office, lead_person_ref, opened_on, closed_on)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [
                (m.matter_ref, m.client_ref, m.matter_type, m.practice_area, m.jurisdiction,
                 m.office, m.lead_person_ref, m.opened_on, m.closed_on)
                for m in est.matters
            ],
        )
        cur.executemany(
            "INSERT INTO pms.matter_team (matter_ref, person_ref, role, from_date, to_date)"
            " VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            [(a.matter_ref, a.person_ref, a.role, a.from_date, a.to_date) for a in est.assignments],
        )
        cur.executemany(
            "INSERT INTO pms.matter_restriction (matter_ref, rule_id, kind, set_on, set_by)"
            " VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            [(r.matter_ref, r.rule_id, r.kind, r.set_on, r.set_by) for r in est.restrictions],
        )
        cur.executemany(
            "INSERT INTO crm.account (account_ref, name, account_type,"
            " relationship_partner_ref, since) VALUES (%s,%s,%s,%s,%s)",
            [
                (a.account_ref, a.name, a.account_type, a.relationship_partner_ref, a.since)
                for a in est.accounts
            ],
        )
        cur.executemany(
            "INSERT INTO crm.contact (contact_ref, account_ref, full_name, job_title, since)"
            " VALUES (%s,%s,%s,%s,%s)",
            [
                (c.contact_ref, c.account_ref, c.full_name, c.job_title, c.since)
                for c in est.contacts
            ],
        )
        conn.commit()

    return {
        "people": len(est.people),
        "clients": len(est.clients),
        "matters": len(est.matters),
        "assignments": len(est.assignments),
        "accounts": len(est.accounts),
        "contacts": len(est.contacts),
        "restrictions": len(est.restrictions),
    }
