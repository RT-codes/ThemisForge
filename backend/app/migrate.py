import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
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


KEEP_BACKUPS = 5


class DatabaseTooNewError(RuntimeError):
    """The database was changed by a newer Themis than this one. Older code must not touch it: it could damage what it
    does not understand (this is what a failed upgrade that was rolled back would otherwise run into)."""


def too_new_message(found: str, head: str | None) -> str:
    return (
        f"This database was made by a newer version of Themis (it is at revision {found}; this version knows up to "
        f"{head}). Upgrade Themis (themis upgrade), or restore a database backup made before the newer version ran."
    )


def is_unknown_revision(url: str, revision: str | None) -> bool:
    """Whether the database is at a revision this code has never heard of, which means it came from a newer version."""
    if not revision:
        return False
    known = {r.revision for r in ScriptDirectory.from_config(_config(url)).walk_revisions()}
    return revision not in known


def _current_revision(db_file: Path) -> str | None:
    con = sqlite3.connect(db_file)
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None  # no version table: a brand new or an old unversioned database
    finally:
        con.close()


def backup_before_upgrade(url: str, head: str) -> Path | None:
    """Save a copy of the database before it is migrated. A migration that goes wrong must never be the only copy
    of someone's data. Returns the backup, or None when there was nothing to protect."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or not Path(parsed.database).exists():
        return None
    db_file = Path(parsed.database)
    current = _current_revision(db_file)
    if current == head:
        return None
    probe = sqlite3.connect(db_file)
    try:
        if probe.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0] == 0:
            return None  # an empty file has nothing to lose
    finally:
        probe.close()
    folder = db_file.parent / "backups"
    folder.mkdir(exist_ok=True)
    target = (
        folder / f"{db_file.stem}-{current or 'unversioned'}-to-{head}-{datetime.now(UTC):%Y%m%d-%H%M%S}.db"
    )
    src, dst = sqlite3.connect(db_file), sqlite3.connect(target)
    try:
        src.backup(dst)  # a consistent copy, even while the app is writing
    finally:
        dst.close()
        src.close()
    for old in sorted(folder.glob(f"{db_file.stem}-*.db"))[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
    return target


def _upgrade(url: str) -> None:
    cfg = _config(url)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database and Path(parsed.database).exists():
        found = _current_revision(Path(parsed.database))
        if is_unknown_revision(url, found):
            raise DatabaseTooNewError(too_new_message(str(found), head))
    if head:
        backup_before_upgrade(url, head)
    if _is_unversioned_legacy_db(url):
        command.stamp(cfg, BASELINE)
    command.upgrade(cfg, "head")


async def upgrade_database(url: str | None = None) -> None:
    """Bring the database to the latest schema. Safe to run on every start."""
    await asyncio.to_thread(_upgrade, url or settings.database_url)
