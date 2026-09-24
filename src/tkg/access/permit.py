"""The permit: what step 5 decided, carried to the one tool that could go around it.

`passages()` reads the index. Without a permit the agent could ask the index
directly and skip the access decision, so ask() returns a short-lived token
naming the caller, the trace and the matters and graphs it was allowed, and
passages() refuses without one, with another caller's, or with an expired one.
See lab-architecture.md §11.
"""

from __future__ import annotations

import time

import jwt

AUDIENCE = "tkg-passages"
TTL_SECONDS = 120


class PermitError(Exception):
    pass


def mint(
    persona: str, trace: str, matters: list[str], graphs: list[str], key: bytes,
    now: float | None = None,
) -> tuple[str, int]:
    issued = int(now if now is not None else time.time())
    exp = issued + TTL_SECONDS
    token = jwt.encode(
        {
            "sub": persona,
            "trace": trace,
            "matters": sorted(matters),
            "graphs": sorted(graphs),
            "aud": AUDIENCE,
            "iat": issued,
            "exp": exp,
        },
        key,
        algorithm="HS256",
    )
    return token, exp


def verify(token: str, key: bytes, caller: str) -> dict:
    try:
        claims = jwt.decode(
            token, key, algorithms=["HS256"], audience=AUDIENCE,
            options={"require": ["exp", "sub", "trace"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise PermitError("permit expired") from exc
    except jwt.PyJWTError as exc:
        raise PermitError("not a permit") from exc
    if claims["sub"] != caller:
        raise PermitError("permit was issued to someone else")
    return claims
