# One persona's way in. Small on purpose: an MCP client library, an HTTP client,
# a JWT library, and the two files it needs. No store driver is installed, and
# the container joins a network on which the resolver is the only other service.
# See docs/decisions/0011.
FROM python:3.12-slim

RUN pip install --no-cache-dir "mcp==2.2.0" "httpx>=0.27,<1" "PyJWT>=2.8,<3"

WORKDIR /app
COPY src/tkg/__init__.py tkg/__init__.py
COPY src/tkg/identity.py tkg/identity.py
COPY src/tkg/mcp tkg/mcp

ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
USER 10001
ENTRYPOINT ["python", "-m", "tkg.mcp.server"]
