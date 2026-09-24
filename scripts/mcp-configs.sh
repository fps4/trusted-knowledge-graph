#!/bin/sh
# One MCP config per persona, for Claude Code. One session, one person: a single
# .mcp.json listing everyone would give one session every persona's tools.
#
#   scripts/mcp-configs.sh              the stack runs on this machine
#   scripts/mcp-configs.sh ds1          the stack runs on a Docker host reached by ssh;
#                                       Claude Code stays here, the MCP container and
#                                       the persona's key stay there
#
# The container runs as the owner of the key file, so a key can stay 0600.
set -eu
cd "$(dirname "$0")/.."

HOST="${1:-}"
PERSONAS=$(sed -n 's/^  - id: //p' config/people.yaml)
mkdir -p mcp

if [ -n "$HOST" ]; then
  DIR="${2:-$(ssh "$HOST" 'cd ~/trusted-knowledge-graph && pwd')}"
  IDS=$(ssh "$HOST" 'echo "$(id -u):$(id -g)"')
else
  DIR="$PWD"
  IDS="$(id -u):$(id -g)"
fi

for persona in $PERSONAS; do
  if [ -n "$HOST" ]; then
    cat > "mcp/$persona.json" <<JSON
{
  "mcpServers": {
    "tkg-$persona": {
      "command": "ssh",
      "args": ["-T", "$HOST",
               "docker run -i --rm --network tkg_edge --user $IDS -v $DIR/secrets/$persona.key:/run/secrets/persona.key:ro tkg-mcp:latest --as $persona"]
    }
  }
}
JSON
  else
    cat > "mcp/$persona.json" <<JSON
{
  "mcpServers": {
    "tkg-$persona": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--network", "tkg_edge", "--user", "$IDS",
               "-v", "$DIR/secrets/$persona.key:/run/secrets/persona.key:ro",
               "tkg-mcp:latest", "--as", "$persona"]
    }
  }
}
JSON
  fi
done
echo "mcp/<persona>.json for: $(echo $PERSONAS | tr '\n' ' ')${HOST:+(via ssh $HOST)}"
