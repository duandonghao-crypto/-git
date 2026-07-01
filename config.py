"""Application configuration with PostgreSQL (Neon/Render compatible)."""
import os, re
from pathlib import Path
try:
    import yaml
except ImportError:
    yaml = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"


def _load_yaml(path: Path) -> dict:
    if yaml and path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_config = _load_yaml(BASE_DIR / "config.yaml")


def _env(key, default=""):
    return os.environ.get(key, default)


class Config:
    HOST: str = "0.0.0.0"
    PORT: int = int(_env("PORT", "8018"))

    # DATABASE_URL is standard on Render/Heroku/Neon
    DB_URL: str = _env("DATABASE_URL", "")
    DB_TYPE: str = "postgresql"  # always PG now

    @classmethod
    def pg_host(cls): return _env("PG_HOST", "localhost")
    @classmethod
    def pg_port(cls): return int(_env("PG_PORT", "5432"))
    @classmethod
    def pg_db(cls): return _env("PG_DB", "electricity")
    @classmethod
    def pg_user(cls): return _env("PG_USER", "postgres")
    @classmethod
    def pg_pass(cls): return _env("PG_PASS", "duandonghao")

    @classmethod
    def db_url(cls):
        """Return the PG connection string. Uses DATABASE_URL if set (Render/Neon)."""
        if cls.DB_URL:
            return cls.DB_URL
        return f"postgresql://{cls.pg_user()}:{cls.pg_pass()}@{cls.pg_host()}:{cls.pg_port()}/{cls.pg_db()}"

    # Directories
    ATTACHMENTS_DIR: str = str(DATA_DIR / "attachments")
    BACKUP_DIR: str = str(DATA_DIR / "backups")
    VERSIONS_DIR: str = str(DATA_DIR / "versions")
    STATIC_DIR: str = str(STATIC_DIR)

    # Email
    EMAIL_ADDRESS: str = _env("EMAIL_ADDRESS", "")
    EMAIL_PASSWORD: str = _env("EMAIL_PASSWORD", "")
    EMAIL_SERVER: str = _env("EMAIL_SERVER", "imap.88.com")
    EMAIL_PORT: int = int(_env("EMAIL_PORT", "993"))
    DOWNLOADS_DIR: str = str(Path.home() / "Downloads")

    # Mapping file: check cloud (data/) then parent (local dev)
    _local_map = DATA_DIR / "简称对应表.xlsx"
    _parent_map = BASE_DIR.parent / "简称对应表.xlsx"
    MAPPING_FILE: str = str(_config.get("mapping_file",
        _local_map if _local_map.exists() else _parent_map))

    # Limits
    MAX_BACKUPS: int = int(_config.get("max_backups", 20))
    LOG_LEVEL: str = _config.get("log_level", "INFO")
    LOG_FILE: str = str(BASE_DIR / "app.log")

    # Flask session
    SECRET_KEY: str = _env("SECRET_KEY", "fee-manager-secret-2026")


class TestConfig(Config):
    DB_TYPE = "sqlite"
