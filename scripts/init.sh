#!/bin/sh
# make init: .env, per-persona keys, the permit key, the audit salt, and one MCP
# config per persona. Never overwrites a key — a new salt would make every hash
# in the existing decision record unresolvable. docs/decisions/0011 and 0013.
set -eu
cd "$(dirname "$0")/.."

[ -f .env ] || { cp .env.example .env; echo "wrote .env"; }
# The resolver and the jobs write into the repo (reports/, build/, data/, audit/).
# Run them as the host user, so what they write stays editable — and git-pullable —
# on a Linux Docker host.
grep -q '^TKG_PORT_MINIO=' .env || printf 'TKG_PORT_MINIO=9100\nTKG_PORT_OPENSEARCH=9200\nMINIO_ROOT_USER=tkg-root\n' >> .env
grep -q '^MINIO_ROOT_PASSWORD=' .env || printf 'MINIO_ROOT_PASSWORD=%s\n' "$(openssl rand -hex 24)" >> .env
grep -q '^TKG_UID=' .env || printf 'TKG_UID=%s\nTKG_GID=%s\n' "$(id -u)" "$(id -g)" >> .env
mkdir -p secrets audit build/opa mcp data/reviews
chmod 700 secrets

key() {
  if [ ! -f "secrets/$1" ]; then
    openssl rand -hex 32 > "secrets/$1"
    chmod 600 "secrets/$1"
    echo "wrote secrets/$1"
  fi
}

PERSONAS=$(sed -n 's/^  - id: //p' config/people.yaml)
for persona in $PERSONAS; do
  key "$persona.key"
  key "minio-$persona.secret"   # the persona's own document-store credentials
done
key resolver.key
key audit.salt
./scripts/mcp-configs.sh
