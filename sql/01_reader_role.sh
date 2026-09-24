#!/bin/sh
# The role the lab reads the systems of record with. Read-only by construction:
# a firm's DBA says yes to this and not to a role that could write back.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
    CREATE ROLE ${TKG_DB_READER} LOGIN PASSWORD '${TKG_DB_READER_PASSWORD}';
    GRANT USAGE ON SCHEMA pms, crm, hr TO ${TKG_DB_READER};
    GRANT SELECT ON ALL TABLES IN SCHEMA pms, crm, hr TO ${TKG_DB_READER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA pms, crm, hr
        GRANT SELECT ON TABLES TO ${TKG_DB_READER};
SQL
