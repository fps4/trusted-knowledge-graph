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

    def ask(self, template_id: str, slots: dict[str, str] | None = None,
            terms: list[str] | None = None) -> dict:
        return self._call("POST", "/ask", {"template_id": template_id, "slots": slots or {},
                                           "terms": terms or []})

    def resolve_term(self, text: str) -> dict:
        return self._call("POST", "/resolve_term", {"text": text})

    def audit_subject(self, matter: str) -> dict:
        return self._call("POST", "/audit/subject", {"matter": matter})

    def audit_person(self, person: str, since: str | None = None,
                     until: str | None = None) -> dict:
        return self._call("POST", "/audit/person", {"person": person, "since": since,
                                                     "until": until})

    def review(self, fact: str, verdict: str) -> dict:
        return self._call("POST", "/review", {"fact": fact, "verdict": verdict})

    def lineage(self, graph: str) -> dict:
        return self._call("POST", "/lineage", {"graph": graph})

    def audit_verify(self) -> dict:
        return self._call("POST", "/audit/verify", {})

    def audit_trace(self, trace: str) -> dict:
        return self._call("POST", "/audit/trace", {"trace": trace})

    def explain(self, trace: str) -> dict:
        return self._call("POST", "/explain", {"trace": trace})

    def passages(self, permit: str, text: str = "") -> dict:
        return self._call("POST", "/passages", {"permit": permit, "text": text})
