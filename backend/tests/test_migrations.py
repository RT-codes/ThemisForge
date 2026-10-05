import sqlite3

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app import models  # noqa: F401
from app.db import Base
from app.migrate import upgrade_database


async def test_migrations_match_the_models(tmp_path):
    path = tmp_path / "m.db"
    await upgrade_database(f"sqlite+aiosqlite:///{path}")
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], f"models and migrations differ, generate a migration: {diff}"


async def test_existing_unversioned_database_is_adopted(tmp_path):
    """A database made by the old create_all() (users table, no alembic_version) must upgrade in place."""
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(320) NOT NULL, name VARCHAR(100) NOT NULL,
            password_hash VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL);
        CREATE UNIQUE INDEX ix_users_email ON users (email);
        INSERT INTO users VALUES (1, 'a@b.co', 'Ada', 'x', '2026-01-01 00:00:00'), (2, 'c@d.co', 'Bob', 'x', '2026-01-02 00:00:00');
        """
    )
    con.commit()
    con.close()

    await upgrade_database(f"sqlite+aiosqlite:///{path}")
    await upgrade_database(f"sqlite+aiosqlite:///{path}")  # idempotent

    con = sqlite3.connect(path)
    assert con.execute("SELECT id, is_admin FROM users ORDER BY id").fetchall() == [(1, 1), (2, 0)]
    assert "tasks" in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
