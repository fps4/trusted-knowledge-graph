-- The systems of record. Three schemas standing in for practice management,
-- CRM and HR. The lab reads these; nothing it does may write back.
-- See docs/decisions/0001-systems-of-record-are-a-database.md

CREATE SCHEMA pms;
CREATE SCHEMA crm;
CREATE SCHEMA hr;

-- ── hr ──────────────────────────────────────────────────────────────────────
CREATE TABLE hr.person (
    person_id     serial PRIMARY KEY,
    person_ref    text NOT NULL UNIQUE,
    given_name    text NOT NULL,
    family_name   text NOT NULL,
    office        text NOT NULL,
    grade         text NOT NULL,
    practice_area text,
    joined_on     date NOT NULL,
    left_on       date
);

-- ── pms ─────────────────────────────────────────────────────────────────────
CREATE TABLE pms.client (
    client_id   serial PRIMARY KEY,
    client_ref  text NOT NULL UNIQUE,
    name        text NOT NULL,
    client_type text NOT NULL,
    opened_on   date NOT NULL
);

CREATE TABLE pms.matter (
    matter_id       serial PRIMARY KEY,
    matter_ref      text NOT NULL UNIQUE,
    client_ref      text NOT NULL REFERENCES pms.client(client_ref),
    matter_type     text NOT NULL,
    practice_area   text NOT NULL,
    jurisdiction    text NOT NULL,
    office          text NOT NULL,
    lead_person_ref text NOT NULL REFERENCES hr.person(person_ref),
    opened_on       date NOT NULL,
    closed_on       date
);

-- Valid-time on who worked a matter: "how expertise has been applied over time"
-- is a question about time, and a table that only knows the present cannot answer it.
CREATE TABLE pms.matter_team (
    matter_ref text NOT NULL REFERENCES pms.matter(matter_ref),
    person_ref text NOT NULL REFERENCES hr.person(person_ref),
    role       text NOT NULL,
    from_date  date NOT NULL,
    to_date    date,
    PRIMARY KEY (matter_ref, person_ref, from_date)
);

-- Read in M1. Present from M0 so the mapping and the schema do not move later.
CREATE TABLE pms.matter_restriction (
    matter_ref text NOT NULL REFERENCES pms.matter(matter_ref),
    rule_id    text NOT NULL,
    kind       text NOT NULL,
    set_on     date NOT NULL,
    set_by     text NOT NULL,
    PRIMARY KEY (matter_ref, rule_id)
);

-- ── crm ─────────────────────────────────────────────────────────────────────
-- Deliberately not joined to pms.client. The same organisation is spelled
-- differently here, and resolving that is a later milestone's job, not a JOIN.
CREATE TABLE crm.account (
    account_id               serial PRIMARY KEY,
    account_ref              text NOT NULL UNIQUE,
    name                     text NOT NULL,
    account_type             text NOT NULL,
    relationship_partner_ref text REFERENCES hr.person(person_ref),
    since                    date NOT NULL
);

CREATE TABLE crm.contact (
    contact_id  serial PRIMARY KEY,
    contact_ref text NOT NULL UNIQUE,
    account_ref text NOT NULL REFERENCES crm.account(account_ref),
    full_name   text NOT NULL,
    job_title   text,
    since       date NOT NULL
);

CREATE INDEX ON pms.matter (client_ref);
CREATE INDEX ON pms.matter (lead_person_ref);
CREATE INDEX ON pms.matter (matter_type, jurisdiction);
CREATE INDEX ON pms.matter_team (person_ref);
