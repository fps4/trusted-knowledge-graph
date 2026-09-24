"""The resolver as a service.

At M0 it exposes what the CLI does and nothing more. It exists now so that M1's
MCP containers have something to talk to, and so that the seam between the agent
and the knowledge layer is in place before there is anything to protect.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .. import settings
from ..ingest.loader import Fuseki
from ..semantic.templates import TEMPLATES
from .engine import Resolver

app = FastAPI(title="tkg resolver", version="0.1.0")
_settings = settings.load()
_fuseki = Fuseki(_settings.fuseki_url)
_resolver = Resolver(_fuseki)


class AskRequest(BaseModel):
    template_id: str
    slots: dict[str, str] = {}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok" if _fuseki.ping() else "degraded", "store": _settings.fuseki_url}


@app.get("/templates")
def templates() -> list[dict]:
    return [
        {
            "id": t.id,
            "question": t.question,
            "slots": [
                {"name": s.name, "kind": s.kind, "default": s.default, "about": s.description}
                for s in t.slots
            ],
            "note": t.note,
        }
        for t in TEMPLATES.values()
    ]


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    try:
        answer = _resolver.ask(request.template_id, request.slots)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "template": answer.template.id,
        "question": answer.template.question,
        "slots": answer.slots,
        "query": answer.bound_query,
        "rows": answer.rows,
        "graphs": answer.graphs,
        "note": answer.template.note,
    }
