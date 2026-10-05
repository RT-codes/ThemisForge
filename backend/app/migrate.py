import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from .config import BACKEND_DIR, settings

BASELINE = "0001"  # the schema as it was before migrations existed (users table only)


def _config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _is_unversioned_legacy_db(url: str) -> bool:
    """A database created by the old create_all() has tables but no alembic_version."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or not Path(parsed.database).exists():
        return False
    engine = create_engine(parsed.set(drivername="sqlite"))
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    return "users" in tables and "alembic_version" not in tables


def _upgrade(url: str) -> None:
    cfg = _config(url)
    if _is_unversioned_legacy_db(url):
        command.stamp(cfg, BASELINE)
    command.upgrade(cfg, "head")


async def upgrade_database(url: str | None = None) -> None:
    """Bring the database to the latest schema. Safe to run on every start."""
    await asyncio.to_thread(_upgrade, url or settings.database_url)
