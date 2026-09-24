"""Who is asking — asserted, not federated. See docs/decisions/0011.

A persona's MCP container holds one key, its own, and mints a short-lived HS256
assertion on every call. The resolver holds every persona's key, verifies the
assertion, and looks the persona up in config/people.yaml. Nothing here takes a
persona as a tool argument: identity is fixed when the container starts.

In the programme this is the OAuth 2.0 on-behalf-of flow on Entra. This module is
the one place the lab is weaker than the design, and the README says so.

Deliberately dependency-light: the MCP image ships this file and nothing that can
reach a store.
"""

from __future__ import annotations

import time
from pathlib import Path

import jwt

AUDIENCE = "tkg-resolver"
TTL_SECONDS = 60


class IdentityError(Exception):
    """Raised with a reason safe to record: it never echoes the token."""


def read_key(path: Path) -> bytes:
    key = path.read_text().strip()
    if len(key) < 32:
        raise IdentityError(f"{path.name}: key too short — run `make init`")
    return key.encode()


def mint(persona: str, key: bytes, now: float | None = None) -> str:
    issued = int(now if now is not None else time.time())
    claims = {"persona": persona, "aud": AUDIENCE, "iat": issued, "exp": issued + TTL_SECONDS}
    return jwt.encode(claims, key, algorithm="HS256", headers={"kid": persona})


def verify(token: str, keys: dict[str, bytes]) -> str:
    """The persona the token proves, or IdentityError."""
    try:
        claimed = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError as exc:
        raise IdentityError("not an assertion") from exc
    key = keys.get(claimed or "")
    if key is None:
        raise IdentityError("unknown persona")
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            audience=AUDIENCE,
            options={"require": ["exp", "iat", "aud", "persona"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise IdentityError("assertion expired") from exc
    except jwt.PyJWTError as exc:
        raise IdentityError("assertion does not verify") from exc
    if claims["persona"] != claimed:
        raise IdentityError("assertion names a different persona from its key")
    return claimed
