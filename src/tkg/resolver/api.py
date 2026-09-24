"""The resolver as a service — the only thing an agent can talk to.

Every request but /healthz carries an assertion minted by a persona's MCP
container, and every request that decides anything writes one chained record,
including the ones refused at the door. There is no endpoint that takes a
persona as a parameter. See docs/decisions/0011 and 0012.
"""

from __future__ import annotations

from functools import lru_cache

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import identity, settings
from ..access.decide import Opa
from ..audit.chain import Hasher, Writer
from ..ingest.loader import Fuseki
from ..semantic.templates import TEMPLATES, TERM_QUESTIONS
from .engine import Resolver

app = FastAPI(title="tkg resolver", version="0.2.0")


class AskRequest(BaseModel):
    template_id: str
    slots: dict[str, str] = {}
    terms: list[str] = []


class TermRequest(BaseModel):
    text: str


class SubjectRequest(BaseModel):
    matter: str


class PersonRequest(BaseModel):
    person: str
    since: str | None = None
    until: str | None = None


class TraceRequest(BaseModel):
    trace: str


class ExplainRequest(BaseModel):
    trace: str


class PassagesRequest(BaseModel):
    permit: str
    text: str = ""


@lru_cache(maxsize=1)
def _state() -> tuple[Resolver, dict[str, bytes], dict[str, dict]]:
    cfg = settings.load()
    people = yaml.safe_load((cfg.config_dir / "people.yaml").read_text())["personas"]
    personas = {p["id"]: p for p in people}
    keys = {
        pid: identity.read_key(cfg.secrets_dir / f"{pid}.key")
        for pid in personas
        if (cfg.secrets_dir / f"{pid}.key").exists()
    }
    salt = (cfg.secrets_dir / "audit.salt").read_text().strip().encode()
    permit_key = identity.read_key(cfg.secrets_dir / "resolver.key")
    resolver = Resolver(
        fuseki=Fuseki(cfg.fuseki_url),
        opa=Opa(cfg.opa_url),
        writer=Writer(cfg.audit_path),
        hasher=Hasher(salt),
        permit_key=permit_key,
        personas=personas,
    )
    return resolver, keys, personas


def caller(request: Request, authorization: str = Header(default="")) -> str:
    resolver, keys, _ = _state()
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return identity.verify(token, keys)
    except identity.IdentityError as exc:
        refused = resolver.refuse_identity(request.url.path.strip("/"), str(exc))
        raise HTTPException(status_code=401, detail=refused) from exc


@app.get("/healthz")
def healthz() -> JSONResponse:
    cfg = settings.load()
    store = Fuseki(cfg.fuseki_url).ping()
    policy = Opa(cfg.opa_url).ping()
    ok = store and policy
    return JSONResponse(
        {"status": "ok" if ok else "degraded", "store": store, "policy": policy},
        status_code=200 if ok else 503,
    )


@app.get("/whoami")
def whoami(persona: str = Depends(caller)) -> dict:
    _, _, personas = _state()
    p = personas[persona]
    return {
        "persona": persona,
        "principal": p["principal"],
        "kind": p["kind"],
        "about": p.get("about", ""),
        "note": "Fixed when this session started. No tool changes who you are.",
    }


@app.get("/templates")
def templates(persona: str = Depends(caller)) -> list[dict]:
    listed = [
        {
            "id": t.id,
            "question": t.question,
            "kind": t.kind,
            "slots": [
                {"name": s.name, "kind": s.kind, "default": s.default, "about": s.description}
                for s in t.slots
            ],
            "note": t.note,
        }
        for t in TEMPLATES.values()
        if t.listed
    ]
    listed += [
        {
            "id": q.id,
            "question": q.question,
            "kind": "term",
            "slots": [{"name": "reading", "kind": "reading", "default": None,
                       "about": f"which reading of the glossary term {q.term!r}"}],
            "note": "Call resolve_term first: the readings have different owners and counts.",
        }
        for q in TERM_QUESTIONS.values()
    ]
    return listed


@app.post("/ask")
def ask(body: AskRequest, persona: str = Depends(caller)) -> dict:
    resolver, _, _ = _state()
    return resolver.ask(persona, body.template_id, body.slots, body.terms)


@app.post("/resolve_term")
def resolve_term(body: TermRequest, persona: str = Depends(caller)) -> dict:
    resolver, _, _ = _state()
    return resolver.resolve_term(persona, body.text)


@app.post("/audit/subject")
def audit_subject(body: SubjectRequest, persona: str = Depends(caller)) -> dict:
    resolver, _, _ = _state()
    return resolver.audit_subject(persona, body.matter)


@app.post("/audit/person")
def audit_person(body: PersonRequest, persona: str = Depends(caller)) -> dict:
    resolver, _, _ = _state()
    return resolver.audit_person(persona, body.person, body.since, body.until)


@app.post("/audit/trace")
def audit_trace(body: TraceRequest, persona: str = Depends(caller)) -> dict:
    resolver, _, _ = _state()
    return resolver.audit_trace(persona, body.trace)


@app.post("/explain")
def explain(body: ExplainRequest, persona: str = Depends(caller)) -> dict:
    resolver, _, _ = _state()
    return resolver.explain(persona, body.trace)


@app.post("/passages")
def passages(body: PassagesRequest, persona: str = Depends(caller)) -> dict:
    resolver, _, _ = _state()
    return resolver.passages(persona, body.permit, body.text)
