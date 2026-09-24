#!/bin/sh
# make init: .env, per-persona keys, the permit key, the audit salt, and one MCP
# config per persona. Never overwrites a key — a new salt would make every hash
# in the existing decision record unresolvable. docs/decisions/0011 and 0013.
set -eu
cd "$(dirname "$0")/.."

[ -f .env ] || { cp .env.example .env; echo "wrote .env"; }
mkdir -p secrets audit build/opa mcp
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
  # One file per persona: a single .mcp.json listing everyone would give one
  # Claude session every persona's tools at once.
  cat > "mcp/$persona.json" <<JSON
{
  "mcpServers": {
    "tkg-$persona": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--network", "tkg_edge",
               "-v", "$PWD/secrets/$persona.key:/run/secrets/persona.key:ro",
               "tkg-mcp:latest", "--as", "$persona"]
    }
  }
}
JSON
done
key resolver.key
key audit.salt
echo "personas: $(echo $PERSONAS | tr '\n' ' ')— mcp/<persona>.json"
