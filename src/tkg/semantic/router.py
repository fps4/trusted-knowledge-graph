"""Step 3: route. graph · index · hybrid · refuse — and why, in the trace.

The route follows from two things the resolver knows before it touches evidence:
what the question needs (facts, passages, or both) and whether every term in it
resolved to one meaning. A question that names an ambiguous term and does not
choose a reading is refused here, with the readings listed back, rather than
answered with whichever reading happened to be first. docs/decisions/0017.
"""

from __future__ import annotations

from dataclasses import dataclass

# Without an index the router says so rather than pretending. The resolver passes
# whether its index answers; this is the default when none is wired in.
INDEX_AVAILABLE = False


@dataclass(frozen=True)
class Route:
    route: str  # graph | index | hybrid | refuse
    reason: str

    def public(self) -> dict:
        return {"route": self.route, "reason": self.reason}


def route(needs: str, template_id: str, ambiguous: str | None = None,
          index_available: bool = INDEX_AVAILABLE) -> Route:
    if ambiguous:
        return Route("refuse", ambiguous)
    if needs == "facts":
        return Route("graph", f"{template_id} is answered from facts in the graph")
    if not index_available:
        return Route(
            "refuse",
            f"{template_id} needs passages from documents, and the index is not available",
        )
    if needs == "passages":
        return Route("index", f"{template_id} is answered from passages, pre-filtered")
    return Route("hybrid", f"{template_id} needs facts and the passages that support them")
