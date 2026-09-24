import os
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(os.environ.get("TKG_ROOT", "/app"))


@dataclass(frozen=True)
class Settings:
    fuseki_url: str
    db_dsn: str
    db_admin_dsn: str
    seed: int
    config_dir: Path
    ontology_dir: Path
    mappings_dir: Path
    data_dir: Path
    reports_dir: Path

    @property
    def sqlalchemy_url(self) -> str:
        """morph-kgc reaches the systems of record through SQLAlchemy."""
        return self.db_dsn.replace("postgresql://", "postgresql+psycopg://", 1)


def load() -> Settings:
    root = APP_ROOT
    return Settings(
        fuseki_url=os.environ.get("TKG_FUSEKI_URL", "http://fuseki:3030/tkg").rstrip("/"),
        db_dsn=os.environ.get("TKG_DB_DSN", ""),
        db_admin_dsn=os.environ.get("TKG_DB_ADMIN_DSN", ""),
        seed=int(os.environ.get("TKG_SEED", "20260924")),
        config_dir=root / "config",
        ontology_dir=root / "ontology",
        mappings_dir=root / "mappings",
        data_dir=root / "data",
        reports_dir=root / "reports",
    )
