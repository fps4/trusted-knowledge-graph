"""The three questions the record exists to answer, for Risk & Compliance.

    Who has ever been shown anything derived from this matter?     subject
    What did this person see, between these times?                 person
    Why was this trace decided as it was?                          trace

Only Risk may ask, and OPA decides that (docs/decisions/0018). Risk is the one
reader who can resolve a salted hash back to a matter, because the resolver holds
the salt and can hash every identifier in the estate to compare. Risk learns that
a decision was made, about what, on which rule — never what the documents say.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .. import iri
from .chain import Hasher, read

MATTERS = "SELECT ?ref WHERE { GRAPH ?g { ?m a ssf:Matter ; ssf:matterRef ?ref } }"
DERIVED = "SELECT ?g WHERE { GRAPH <%s> { ?g a ssf:DerivedGraph } }"
DERIVED_FROM = (
    "SELECT ?g WHERE { GRAPH <%(prov)s> { ?g prov:wasDerivedFrom+ <%(matter)s> } }"
)


def _parts(record: dict) -> list[dict]:
    """An ask is one decision; a resolve_term carries one per reading it counted."""
    if record.get("request") in ("ask", "passages"):
        return [record]
    if record.get("request") == "resolve_term":
        return list(record.get("readings", []))
    return []


def _when(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


class AuditReader:
    def __init__(self, path, hasher: Hasher, fuseki) -> None:
        self.path = path
        self.hasher = hasher
        self.fuseki = fuseki

    def _rows(self, query: str) -> list[dict]:
        return self.fuseki.query(iri.PREFIXES + query)["results"]["bindings"]

    def _clear(self) -> dict[str, str]:
        """Every hash the record could hold, back to what it hashes."""
        out = {}
        for row in self._rows(MATTERS):
            ref = row["ref"]["value"]
            out[self.hasher("matter", ref)] = ref
        for row in self._rows(DERIVED % iri.G_PROV):
            g = row["g"]["value"]
            out[self.hasher("graph", g)] = iri.shorten(g)
        return out

    def _resolve(self, value, clear: dict[str, str]):
        if isinstance(value, str):
            for prefix in ("matter:", "graph:"):
                if value.startswith(prefix + "h:"):
                    return prefix + clear.get(value[len(prefix):], value[len(prefix):])
            return clear.get(value, value)
        if isinstance(value, list):
            return [self._resolve(v, clear) for v in value]
        if isinstance(value, dict):
            return {k: self._resolve(v, clear) for k, v in value.items()}
        return value

    # ── who has ever been shown anything derived from this matter ───────────
    def subject(self, matter_ref: str) -> dict:
        derived = {
            row["g"]["value"]
            for row in self._rows(DERIVED_FROM % {"prov": iri.G_PROV,
                                                  "matter": iri.matter(matter_ref)})
        }
        derived_short = {iri.shorten(g) for g in derived}
        h_matter = self.hasher("matter", matter_ref)
        h_graphs = {self.hasher("graph", g) for g in derived}
        shown, refused = [], []
        for record in read(self.path):
            for part in _parts(record):
                returned = part.get("returned") or {}
                how = []
                if matter_ref in (returned.get("matters") or []):
                    how.append("shown the matter")
                if matter_ref in (returned.get("counted") or []):
                    how.append("counted in an aggregate")
                if matter_ref in (returned.get("passage_matters") or []):
                    how.append("shown passages from its documents")
                for g in returned.get("graphs") or []:
                    if g in derived_short or g in derived:
                        how.append(f"by lineage: {iri.shorten(g)}")
                base = {
                    "ts": record["ts"], "persona": record["persona"], "trace": record["trace"],
                    "template": part.get("template") or record.get("template"),
                }
                if how:
                    shown.append({**base, "how": how})
                    continue
                considered = part.get("considered") or {}
                reached = [h for h in considered.get("matters", []) if h == h_matter]
                reached += [h for h in considered.get("graphs", []) if h in h_graphs]
                if reached:
                    rules = sorted({r for d in part.get("decisions", []) if not d["allow"]
                                    for r in d["rules"]})
                    refused.append({**base, "outcome": part.get("outcome"), "rules": rules,
                                    "blocked": len(reached)})
        return {
            "matter": matter_ref,
            "derived_graphs": sorted(derived_short),
            "shown": shown,
            "refused": refused,
        }

    # ── what did this person see ────────────────────────────────────────────
    def person(self, persona: str, since: str | None, until: str | None) -> dict:
        lo = _when(since) if since else datetime.min.replace(tzinfo=UTC)
        hi = _when(until) if until else datetime.now(UTC)
        clear = self._clear()
        seen = []
        for record in read(self.path):
            if record.get("persona") != persona or not (lo <= _when(record["ts"]) <= hi):
                continue
            for part in _parts(record) or [record]:
                returned = part.get("returned") or {}
                denied = [
                    self._resolve(d["item"], clear)
                    for d in part.get("decisions", []) if not d["allow"]
                ]
                seen.append({
                    "ts": record["ts"], "trace": record["trace"], "request": record["request"],
                    "template": part.get("template") or record.get("template"),
                    "outcome": part.get("outcome") or record.get("outcome"),
                    "shown_matters": returned.get("matters") or [],
                    "counted_matters": len(returned.get("counted") or []),
                    "shown_graphs": returned.get("graphs") or [],
                    "withheld": denied,
                    "rules": sorted({r for d in part.get("decisions", []) if not d["allow"]
                                     for r in d["rules"]}),
                })
        return {"persona": persona, "since": lo.isoformat(), "until": hi.isoformat(),
                "requests": seen}

    # ── why was this decided as it was ──────────────────────────────────────
    def trace(self, trace_id: str) -> dict | None:
        found = next((r for r in read(self.path) if r.get("trace") == trace_id), None)
        if found is None:
            return None
        return self._resolve(found, self._clear())
