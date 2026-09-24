"""The resolver, called as a persona — how the CLI jobs ask questions.

The jobs container is the operator's tool and holds every persona's key; it
mints an assertion per call exactly as a persona's MCP container does. Asking
through the resolver rather than running the engine in-process keeps the
resolver the only writer of the decision record. docs/decisions/0012.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from . import identity


class ResolverClient:
    def __init__(self, base_url: str, secrets_dir: Path, persona: str) -> None:
        self.base = base_url.rstrip("/")
        self.persona = persona
        self.key = identity.read_key(secrets_dir / f"{persona}.key")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {identity.mint(self.persona, self.key)}"}

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        with httpx.Client(timeout=60.0) as client:
            response = client.request(method, self.base + path, json=body, headers=self._headers())
        if response.status_code == 401:
            return response.json()["detail"]
        response.raise_for_status()
        return response.json()

    def whoami(self) -> dict:
        return self._call("GET", "/whoami")

    def templates(self) -> list[dict]:
        return self._call("GET", "/templates")

    def ask(self, template_id: str, slots: dict[str, str] | None = None) -> dict:
        return self._call("POST", "/ask", {"template_id": template_id, "slots": slots or {}})

    def explain(self, trace: str) -> dict:
        return self._call("POST", "/explain", {"trace": trace})

    def passages(self, permit: str, text: str = "") -> dict:
        return self._call("POST", "/passages", {"permit": permit, "text": text})
