"""R2RML over the live systems of record.

The mapping is data in git, not code: mappings/*.r2rml.ttl say how a row in the
practice management system becomes a fact about a matter, and changing that is a
reviewable diff rather than a pull request against a loader.

morph-kgc's `materialize` returns an rdflib Graph, which cannot hold a named
graph — so it comes back empty for mappings that use rr:graphMap, which all of
ours do. `materialize_set` returns the quads as N-Quads lines, graph included,
and that is what the spine needs: the named graph is the unit of provenance, and
from M1 the unit of access.
"""

from __future__ import annotations

from pathlib import Path

CONFIG = """[CONFIGURATION]
output_format: N-QUADS
logging_level: WARNING
# A NULL date must produce no triple at all, not the literal string "None" typed
# as xsd:date. The shapes caught this on the first run of the load gate, which is
# what a load contract is for. See docs/decisions/0005-null-is-not-a-value.md
na_values: ,#N/A,N/A,NULL,null,None,NaN,nan,<NA>

[pms]
mappings: {mappings}/pms.r2rml.ttl
db_url: {db}

[crm]
mappings: {mappings}/crm.r2rml.ttl
db_url: {db}

[hr]
mappings: {mappings}/hr.r2rml.ttl
db_url: {db}
"""


def materialize(sqlalchemy_url: str, mappings_dir: Path, out_path: Path) -> int:
    import morph_kgc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    config = CONFIG.format(mappings=mappings_dir, db=sqlalchemy_url)
    quads = morph_kgc.materialize_set(config)
    # Sorted, so the same estate produces byte-identical output every run.
    with out_path.open("w", encoding="utf-8") as handle:
        for line in sorted(quads):
            handle.write(line + " .\n")
    return len(quads)
