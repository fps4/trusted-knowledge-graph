"""The MCP boundary: one process per persona, started as that persona.

    docker run -i --rm --network tkg_edge \
        -v …/secrets/sanne.key:/run/secrets/persona.key:ro tkg-mcp --as sanne

The container holds one key — its own — and can reach one service, the resolver.
There is no tool here that takes a persona, a principal or a role: who is asking
is fixed when the process starts. A role the model can pass as a parameter is not
a boundary. See docs/decisions/0011.

There is also no document() tool. A tool that turns an identifier into content is
a second door; citations carry what may be opened.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer

from tkg.identity import mint, read_key

INSTRUCTIONS = """\
You are connected to a firm's knowledge layer as one specific person, fixed for this
session — call whoami() to see who. Everything you are shown has already been
decided for that person: never suggest another person could ask instead.

Questions are answered by competency-question templates, never by free-form queries.
Call questions() once, pick the template that fits, and fill its slots. Slots take
short identifiers: matters like M-2022-0117, clients like C-0042, people like
P-0101, and vocabulary like gl:matter-type/regulatory-investigation or
id:jurisdiction/NL. Defaults are used for slots you leave out.

Business words are not yours to interpret. Before filling a slot from a word the
user used — "AIFM", "AFM investigation", "active client" — call resolve_term() on it
and use what it says the word means, then pass the term ids you relied on in
ask(..., terms=[...]). If a term has several readings, do not pick one: show the
readings, their owners and their counts, and ask the user which they mean.

Report what comes back faithfully:
- Every row cites the named graph it came from; keep the citation.
- A fact whose review state is "unconfirmed" must be reported as unconfirmed.
- A matter with no outcome has no outcome. Do not supply one.
- If the outcome is refused, refused-aggregate, or answered-with-withheld, say so
  and quote the rule, owner and date from explain. Do not guess what was withheld,
  and do not try to reconstruct it from other questions.
"""


def build(persona: str, key: bytes, resolver_url: str) -> MCPServer:
    server = MCPServer(name=f"tkg-{persona}", instructions=INSTRUCTIONS, version="0.2.0")

    def call(method: str, path: str, body: dict | None = None) -> dict | list:
        headers = {"Authorization": f"Bearer {mint(persona, key)}"}
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.request(method, resolver_url + path, json=body, headers=headers)
        except httpx.HTTPError as exc:
            return {"outcome": "unavailable", "reason": f"the resolver did not answer: {exc}"}
        if response.status_code == 401:
            return response.json().get("detail", {"outcome": "refused-identity"})
        response.raise_for_status()
        return response.json()

    @server.tool()
    def whoami() -> dict:
        """Who this session is. Fixed when the session started; no tool changes it."""
        return call("GET", "/whoami")

    @server.tool()
    def questions() -> list:
        """The competency questions the knowledge layer answers, with their slots and defaults."""
        return call("GET", "/templates")

    @server.tool()
    def ask(question_id: str, slots: dict[str, str] | None = None,
            terms: list[str] | None = None) -> dict:
        """Ask one competency question, e.g. ask("CQ-06", {"matter": "M-2021-0043"}).

        `terms` lists the glossary term ids you used to fill the slots, so the answer
        records which definitions it rests on. Returns rows with the named graph each
        came from, the route and why, the outcome, and — when anything was withheld —
        explain: the rule, its owner, the date it was set, and how many facts were
        blocked directly or by lineage. An answered question also carries a
        short-lived permit for passages().
        """
        return call("POST", "/ask", {"template_id": question_id, "slots": slots or {},
                                     "terms": terms or []})

    @server.tool()
    def resolve_term(text: str) -> dict:
        """What a business word means in this firm, and who decides that.

        Returns the glossary entry — definition, owner, the slot values it stands
        for — or, for a word with several readings, every reading with its owner
        and its count as you are allowed to see it. Call this before interpreting
        any business term yourself.
        """
        return call("POST", "/resolve_term", {"text": text})

    @server.tool()
    def audit_subject(matter: str) -> dict:
        """Risk & Compliance only: who has ever been shown anything derived from a matter.

        Anyone else is refused, and the attempt is recorded.
        """
        return call("POST", "/audit/subject", {"matter": matter})

    @server.tool()
    def audit_person(person: str, since: str | None = None, until: str | None = None) -> dict:
        """Risk & Compliance only: what one person was shown, between two ISO times.

        `person` is who is being asked about, not who is asking — that is fixed.
        """
        return call("POST", "/audit/person", {"person": person, "since": since,
                                               "until": until})

    @server.tool()
    def audit_trace(trace: str) -> dict:
        """Risk & Compliance only: the full stored record of one decision, identifiers resolved."""
        return call("POST", "/audit/trace", {"trace": trace})

    @server.tool()
    def explain(trace: str) -> dict:
        """Why one of your earlier questions was decided as it was, from the stored record."""
        return call("POST", "/explain", {"trace": trace})

    @server.tool()
    def passages(permit: str, text: str = "") -> dict:
        """Passages from the document index, limited to what ask() permitted.

        Needs the permit returned by ask(). The index arrives in M3; the permit is
        checked now.
        """
        return call("POST", "/passages", {"permit": permit, "text": text})

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="tkg MCP server, as one persona")
    parser.add_argument("--as", dest="persona", required=True)
    parser.add_argument("--key", default="/run/secrets/persona.key")
    parser.add_argument(
        "--resolver", default=os.environ.get("TKG_RESOLVER_URL", "http://resolver:8080")
    )
    args = parser.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build(args.persona, read_key(Path(args.key)), args.resolver.rstrip("/")).run("stdio")


if __name__ == "__main__":
    main()
