"""R2RML over the live systems of record.

The mapping is data in git, not code: mappings/*.r2rml.ttl say how a row in the
practice management system becomes a fact about a matter, and changing that is a
reviewable diff rather than a pull request against a loader.
"""

from __future__ import annotations

from pathlib import Path

CONFIG = """[CONFIGURATION]
output_file: {out}
output_format: N-QUADS
logging_level: WARNING

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


def materialize(sqlalchemy_url: str, mappings_dir: Path, out_path: Path) -> Path:
    import morph_kgc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    config = CONFIG.format(out=out_path, mappings=mappings_dir, db=sqlalchemy_url)
    morph_kgc.materialize_file(config)
    return out_path
