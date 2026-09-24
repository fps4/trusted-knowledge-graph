"""Step 5: the graph says what is connected, OPA says what is allowed.

Lineage is traversed here, in SPARQL over prov:wasDerivedFrom+ in g:prov, and
passed to OPA as input. The rules are evaluated there, never here — this module
has no idea what a barrier is. See docs/decisions/0008.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from .. import iri

LINEAGE = """
SELECT ?g ?src WHERE {
  GRAPH <%(prov)s> {
    VALUES ?g { %(graphs)s }
    ?g prov:wasDerivedFrom+ ?src .
  }
  FILTER (STRSTARTS(STR(?src), "%(matters)s"))
}
"""


def lineage(fuseki, graphs: list[str]) -> dict[str, list[str]]:
    """derived graph -> every matter it derives from, transitively. [] if none."""
    if not graphs:
        return {}
    result = fuseki.query(
        iri.PREFIXES
        + LINEAGE
        % {
            "prov": iri.G_PROV,
            "graphs": " ".join(f"<{g}>" for g in graphs),
            "matters": iri.ID + "matter/",
        }
    )
    out: dict[str, set[str]] = {g: set() for g in graphs}
    for row in result["results"]["bindings"]:
        ref, graph = iri.matter_ref(row["src"]["value"]), row["g"]["value"]
        if ref and graph in out:
            out[graph].add(ref)
    return {g: sorted(ms) for g, ms in out.items()}


class PolicyUnavailable(RuntimeError):
    """OPA did not answer. The resolver refuses; it never decides on its own."""


@dataclass
class Decision:
    policy_version: str
    disclosure: str
    principal: list[dict]
    matters: dict[str, dict] = field(default_factory=dict)
    graphs: dict[str, dict] = field(default_factory=dict)

    def denied_matters(self) -> list[str]:
        return sorted(m for m, d in self.matters.items() if not d["allow"])

    def denied_graphs(self) -> list[str]:
        return sorted(g for g, d in self.graphs.items() if not d["allow"])


class Opa:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def decide(
        self, principal: str, matters: list[str], lineage_map: dict[str, list[str]]
    ) -> Decision:
        payload = {"input": {"principal": principal, "matters": matters, "lineage": lineage_map}}
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(f"{self.base}/v1/data/tkg/access/decision", json=payload)
                response.raise_for_status()
                result = response.json().get("result")
        except httpx.HTTPError as exc:
            raise PolicyUnavailable(str(exc)) from exc
        if not result:
            raise PolicyUnavailable("OPA returned no decision — is the policy data loaded?")
        return Decision(
            policy_version=result["policy_version"],
            disclosure=result["disclosure"],
            principal=result["principal"],
            matters=result.get("matters", {}),
            graphs=result.get("graphs", {}),
        )

    def may_read_record(self, principal: str) -> tuple[bool, list[dict]]:
        """Reading the decision record is an access decision, made here like any other."""
        payload = {"input": {"principal": principal}}
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(f"{self.base}/v1/data/tkg/access/audit", json=payload)
                response.raise_for_status()
                result = response.json().get("result")
        except httpx.HTTPError as exc:
            raise PolicyUnavailable(str(exc)) from exc
        if not result:
            raise PolicyUnavailable("OPA returned no audit decision")
        return result["allow"], result["grounds"]

    def ping(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                return client.get(f"{self.base}/health").status_code == 200
        except httpx.HTTPError:
            return False
