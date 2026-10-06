import asyncio
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


def _alembic(url: str, action: str, revision: str) -> None:
    from alembic import command

    from app.migrate import _config

    getattr(command, action)(_config(url), revision)


async def test_the_workflow_library_migration_keeps_existing_workflows_and_runs(tmp_path):
    """0006 gave each project one workflow; 0007 must carry it, and its runs, into the library."""
    path = tmp_path / "w.db"
    url = f"sqlite+aiosqlite:///{path}"
    await asyncio.to_thread(_alembic, url, "upgrade", "0006")
    con = sqlite3.connect(path)
    con.executescript(
        """
        INSERT INTO users (id, email, name, password_hash, is_admin, created_at) VALUES (1, 'a@b.co', 'Ada', 'x', 1, '2026-01-01 00:00:00');
        INSERT INTO projects (id, owner_id, name, description, properties, created_at) VALUES (1, 1, 'P', '', '[]', '2026-01-01 00:00:00');
        INSERT INTO workflows (id, project_id, graph, updated_at) VALUES (5, 1, '{"nodes": [], "edges": []}', '2026-02-02 00:00:00');
        INSERT INTO workflow_runs (id, project_id, status, trigger, outcome, started_at, graph) VALUES (9, 1, 'succeeded', 'test', '', '2026-02-03 00:00:00', '{}');
        INSERT INTO tasks (id, project_id, title, description, status, position, properties, schedule_kind, review_on_success, harness, created_at, updated_at)
            VALUES (3, 1, 'T', '', 'done', 1.0, '{}', 'none', 0, '', '2026-01-01 00:00:00', '2026-01-01 00:00:00');
        INSERT INTO attempts (id, task_id, status, started_at, log, result) VALUES (4, 3, 'succeeded', '2026-01-01 00:00:00', 'the log', 'the result');
        INSERT INTO workflow_node_runs (run_id, node_id, kind, label, seq, status, log, result, error) VALUES (9, 'n1', 'start', 'Start', 1, 'succeeded', '', '', '');
        """
    )
    con.commit()
    con.close()

    await asyncio.to_thread(_alembic, url, "upgrade", "head")

    con = sqlite3.connect(path)
    assert con.execute("SELECT id, name, description, created_at FROM workflows").fetchall() == [
        (5, "Workflow", "", "2026-02-02 00:00:00")
    ]
    assert con.execute("SELECT id, workflow_id FROM workflow_runs").fetchall() == [(9, 5)]
    assert con.execute("SELECT count(*) FROM workflow_node_runs").fetchone() == (1,)
    # recreating tables must not have cascaded into the rows that point at them
    assert con.execute("SELECT id, log, result FROM attempts").fetchall() == [(4, "the log", "the result")]
    assert con.execute("SELECT id, workflow_id FROM tasks").fetchall() == [(3, None)]
    con.execute(
        "INSERT INTO workflows (project_id, name, description, graph, created_at, updated_at) VALUES (1, 'Second', '', '{}', '2026-03-01 00:00:00', '2026-03-01 00:00:00')"
    )
    assert con.execute("SELECT count(*) FROM workflows WHERE project_id = 1").fetchone() == (
        2,
    )  # no longer one per project
    con.close()

    await asyncio.to_thread(_alembic, url, "downgrade", "0006")  # and it can be undone
    con = sqlite3.connect(path)
    assert con.execute("SELECT id FROM workflows").fetchall() == [(5,)]
    con.close()


async def test_the_database_is_backed_up_before_a_migration_changes_it(tmp_path):
    path = tmp_path / "b.db"
    url = f"sqlite+aiosqlite:///{path}"
    await asyncio.to_thread(_alembic, url, "upgrade", "0005")
    con = sqlite3.connect(path)
    con.execute(
        "INSERT INTO users (id, email, name, password_hash, is_admin, created_at) VALUES (1, 'a@b.co', 'Ada', 'x', 1, '2026-01-01 00:00:00')"
    )
    con.commit()
    con.close()

    await upgrade_database(url)

    backups = list((tmp_path / "backups").glob("b-0005-to-*.db"))
    assert len(backups) == 1
    old = sqlite3.connect(backups[0])
    assert old.execute("SELECT email FROM users").fetchall() == [("a@b.co",)]
    assert old.execute("SELECT version_num FROM alembic_version").fetchone() == ("0005",)  # exactly as it was
    old.close()

    await upgrade_database(url)  # already up to date: nothing to protect, no new copy
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


async def test_a_new_database_needs_no_backup(tmp_path):
    await upgrade_database(f"sqlite+aiosqlite:///{tmp_path / 'n.db'}")
    assert not (tmp_path / "backups").exists()


async def test_only_the_latest_backups_are_kept(tmp_path):
    from app.migrate import KEEP_BACKUPS

    folder = tmp_path / "backups"
    folder.mkdir()
    for i in range(KEEP_BACKUPS + 3):
        (folder / f"k-0001-to-0009-2026010{i}-000000.db").write_bytes(b"x")
    path = tmp_path / "k.db"
    await asyncio.to_thread(_alembic, f"sqlite+aiosqlite:///{path}", "upgrade", "0005")
    await upgrade_database(f"sqlite+aiosqlite:///{path}")
    assert len(list(folder.glob("k-*.db"))) == KEEP_BACKUPS
