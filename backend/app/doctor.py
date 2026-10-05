"""`./themis doctor`: check that this machine can run ThemisForge. Exit code 1 if something is broken."""

import asyncio
import sys
from collections.abc import Callable

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from .app_settings import AppSettings, load_settings
from .config import DEFAULT_SECRET_KEY, settings
from .docker_check import check_docker
from .migrate import _config

OK, WARN, FAIL = "ok", "warn", "fail"
_MARK = {OK: "\033[32m✓\033[0m", WARN: "\033[33m!\033[0m", FAIL: "\033[31m✗\033[0m"}


def _database() -> tuple[str, str]:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite":
        return WARN, f"Database {url.get_backend_name()}: not checked"
    path = url.database
    if not path:
        return FAIL, "No database path configured"
    engine = create_engine(url.set(drivername="sqlite"))
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    head = ScriptDirectory.from_config(_config(settings.database_url)).get_current_head()
    if current is None:
        return WARN, f"Database {path} is empty: it is created when the server first starts"
    if current != head:
        return (
            WARN,
            f"Database {path} is at revision {current}, latest is {head}: it upgrades on the next start",
        )
    return OK, f"Database {path} is up to date (revision {head})"


def _data_dir() -> tuple[str, str]:
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".doctor"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        return FAIL, f"Data directory {settings.data_dir} is not writable: {e}"
    return OK, f"Data directory {settings.data_dir} is writable"


def _app_settings() -> AppSettings:
    """The Docker host the operator saved in the Settings page, if the database exists."""
    from .db import make_engine

    async def read() -> AppSettings:
        engine = make_engine(settings.database_url)
        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            async with async_sessionmaker(engine)() as session:
                return await load_settings(session)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(read())
    except SQLAlchemyError:  # no database yet (or no settings table): defaults apply
        return AppSettings()


def run() -> int:
    results: list[tuple[str, str]] = []

    def add(check: Callable[[], tuple[str, str]]) -> None:
        try:
            results.append(check())
        except (OSError, SQLAlchemyError) as e:
            results.append((FAIL, f"Check failed: {e}"))

    add(
        lambda: (
            (OK, f"Python {sys.version.split()[0]}")
            if sys.version_info >= (3, 13)
            else (FAIL, "Python 3.13+ is required")
        )
    )
    add(
        lambda: (
            (
                WARN,
                "THEMIS_SECRET_KEY is the insecure default: set a real one in backend/.env before exposing this server",
            )
            if settings.secret_key == DEFAULT_SECRET_KEY
            else (OK, "Secret key is set")
        )
    )
    add(_data_dir)
    add(_database)
    add(
        lambda: (
            (OK, "Frontend is built")
            if (settings.frontend_dist / "index.html").is_file()
            else (WARN, "Frontend is not built (cd frontend && npm run build); fine in development")
        )
    )

    cfg = _app_settings()
    docker = asyncio.run(check_docker(cfg.docker_host))
    if docker.ok:
        results.append((OK, f"Docker {docker.version} reachable ({docker.host}), {docker.cpus} CPUs"))
    else:
        results.append((FAIL, f"Docker: {docker.error}" + (f"\n    {docker.hint}" if docker.hint else "")))
    if settings.cell_backend != "docker":
        results.append(
            (WARN, f"THEMIS_CELL_BACKEND={settings.cell_backend}: cells are simulated, not run in Docker")
        )

    for level, message in results:
        print(f" {_MARK[level]} {message}")
    failed = sum(1 for level, _ in results if level == FAIL)
    print(f"\n{'All good.' if not failed else f'{failed} problem(s) need attention.'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
