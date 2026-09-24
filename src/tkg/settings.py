import os
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(os.environ.get("TKG_ROOT", "/app"))


@dataclass(frozen=True)
class Settings:
    fuseki_url: str
    opa_url: str
    resolver_url: str
    db_dsn: str
    db_admin_dsn: str
    seed: int
    config_dir: Path
    ontology_dir: Path
    mappings_dir: Path
    vocab_dir: Path
    data_dir: Path
    reports_dir: Path
    build_dir: Path
    audit_path: Path
    secrets_dir: Path
    minio_url: str
    minio_public_url: str
    index_url: str

    @property
    def sqlalchemy_url(self) -> str:
        """morph-kgc reaches the systems of record through SQLAlchemy."""
        return self.db_dsn.replace("postgresql://", "postgresql+psycopg://", 1)

    @property
    def documents_path(self) -> Path:
        return self.data_dir / "fixtures" / "documents.jsonl"

    @property
    def extraction_path(self) -> Path:
        return self.data_dir / "fixtures" / "extraction.jsonl"


def load() -> Settings:
    root = APP_ROOT
    return Settings(
        fuseki_url=os.environ.get("TKG_FUSEKI_URL", "http://fuseki:3030/tkg").rstrip("/"),
        opa_url=os.environ.get("TKG_OPA_URL", "http://opa:8181").rstrip("/"),
        resolver_url=os.environ.get("TKG_RESOLVER_URL", "http://resolver:8080").rstrip("/"),
        db_dsn=os.environ.get("TKG_DB_DSN", ""),
        db_admin_dsn=os.environ.get("TKG_DB_ADMIN_DSN", ""),
        seed=int(os.environ.get("TKG_SEED", "20260924")),
        config_dir=root / "config",
        ontology_dir=root / "ontology",
        mappings_dir=root / "mappings",
        vocab_dir=root / "vocab",
        data_dir=root / "data",
        reports_dir=root / "reports",
        build_dir=root / "build",
        audit_path=root / "audit" / "decisions.jsonl",
        secrets_dir=Path(os.environ.get("TKG_SECRETS_DIR", "/run/secrets/tkg")),
        minio_url=os.environ.get("TKG_MINIO_URL", "http://minio:9000"),
        # What a presigned URL is signed for: where the person opening it reaches
        # the store. On a remote Docker host that is a tunnel to its loopback.
        minio_public_url=os.environ.get("TKG_MINIO_PUBLIC_URL", "http://127.0.0.1:9100"),
        index_url=os.environ.get("TKG_INDEX_URL", "http://opensearch:9200"),
    )

