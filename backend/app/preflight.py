"""What Themis needs in order to work, checked.

The same list of checks serves three places, so what `themis doctor` prints is what the app saw:

  * at every start (after the database is migrated), recorded in the run trail (see runlog.py),
  * again in the background while the app runs, because Docker can be stopped or updated under it,
  * by `themis doctor` (see doctor.py).

A problem never stops the app from starting: a stopped Docker Desktop must not turn into a crash loop. Instead the
problems are shown to administrators, and while cells cannot run the scheduler leaves tasks waiting, instead of
failing them (see Scheduler.cells_ready).
"""

import asyncio
import contextlib
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from .app_settings import AppSettings, load_settings
from .config import DEFAULT_SECRET_KEY, settings
from .docker_check import DockerStatus, check_docker, docker_env, run_command
from .harness import plan_for
from .migrate import _config

log = logging.getLogger(__name__)

OK, WARN, FAIL = "ok", "warn", "fail"

# how often the background check looks again: soon after a problem (so a fix is noticed), rarely when all is well
RECHECK_PROBLEM_SECONDS = 15
RECHECK_OK_SECONDS = 300


@dataclass(frozen=True)
class Check:
    id: str
    level: str  # ok | warn | fail
    message: str
    hint: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "level": self.level, "message": self.message, "hint": self.hint}


# ----- the checks that need nothing but this machine -----


def check_python() -> Check:
    if sys.version_info >= (3, 13):  # noqa: UP036 - the point of the check: a wrong interpreter may run this far
        return Check("python", OK, f"Python {sys.version.split()[0]}")
    return Check(
        "python",
        FAIL,
        "Python 3.13+ is required",
        "Install Python 3.13, or run Themis with uv, which fetches it.",
    )


def check_secret_key() -> Check:
    if settings.secret_key == DEFAULT_SECRET_KEY:
        return Check(
            "secret_key",
            WARN,
            "THEMIS_SECRET_KEY is the insecure default",
            "Set a real one in backend/.env before exposing this server (the installer does this for you).",
        )
    return Check("secret_key", OK, "Secret key is set")


def check_data_dir() -> Check:
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".doctor"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        return Check(
            "data_dir",
            FAIL,
            f"Data directory {settings.data_dir} is not writable: {e}",
            "Check the folder's permissions and that the disk is not full.",
        )
    return Check("data_dir", OK, f"Data directory {settings.data_dir} is writable")


def check_database() -> Check:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite":
        return Check("database", WARN, f"Database {url.get_backend_name()}: not checked")
    path = url.database
    if not path:
        return Check(
            "database",
            FAIL,
            "No database path configured",
            "Set THEMIS_DATABASE_URL, or leave it unset for the default.",
        )
    engine = create_engine(url.set(drivername="sqlite"))
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    except SQLAlchemyError as e:
        return Check(
            "database",
            FAIL,
            f"Database {path} cannot be opened: {e}",
            "Is the file damaged, or on a disk that is full or read only? A backup is kept in the backups folder next to it.",
        )
    finally:
        engine.dispose()
    head = ScriptDirectory.from_config(_config(settings.database_url)).get_current_head()
    if current is None:
        return Check(
            "database", WARN, f"Database {path} is empty: it is created when the server first starts"
        )
    if current != head:
        return Check(
            "database",
            WARN,
            f"Database {path} is at revision {current}, latest is {head}: it upgrades on the next start",
        )
    return Check("database", OK, f"Database {path} is up to date (revision {head})")


def check_frontend() -> Check:
    if (settings.frontend_dist / "index.html").is_file():
        return Check("frontend", OK, "Frontend is built")
    return Check(
        "frontend",
        WARN,
        "Frontend is not built",
        "Fine in development; otherwise run: cd frontend && npm run build",
    )


# ----- Docker -----


def docker_check_result(docker: DockerStatus) -> Check:
    if docker.ok:
        return Check("docker", OK, f"Docker {docker.version} reachable ({docker.host}), {docker.cpus} CPUs")
    return Check("docker", FAIL, f"Docker: {docker.error}", docker.hint or "")


async def check_cell_image(cfg: AppSettings) -> Check:
    """Is the image agents run in on the machine Docker runs on? A missing one is only a warning: Docker pulls an image
    that lives in a registry by itself the first time it is needed."""
    hp = plan_for("codex", cfg)
    image = hp.image if hp else cfg.cell_image
    code, _, _ = await run_command(["docker", "image", "inspect", image], docker_env(cfg.docker_host), 20)
    if code == 0:
        return Check("cell_image", OK, f"Cell image {image} is present")
    return Check(
        "cell_image",
        WARN,
        f"Cell image {image} is not on this machine yet",
        "Agents need it. Build it with ./themis build-images, or pick another image in Settings.",
    )


async def run_checks(cfg: AppSettings, *, docker: DockerStatus | None = None) -> list[Check]:
    """Every check, in the order a person should read them. `docker` skips asking Docker again when it was just asked."""
    checks = [check_python(), check_secret_key()]
    for local in (check_data_dir, check_database, check_frontend):
        try:
            checks.append(local())
        except (OSError, SQLAlchemyError) as e:
            checks.append(Check(local.__name__.removeprefix("check_"), FAIL, f"Check failed: {e}"))
    if settings.cell_backend == "docker":
        status = docker or await check_docker(cfg.docker_host)
        checks.append(docker_check_result(status))
        if status.ok:
            checks.append(await check_cell_image(cfg))
    else:
        checks.append(
            Check(
                "cell_backend",
                WARN,
                f"THEMIS_CELL_BACKEND={settings.cell_backend}: cells are simulated, not run in Docker",
            )
        )
    return checks


def cells_can_run(checks: list[Check]) -> bool:
    """Cells need Docker, unless they are simulated. Everything else is a warning the app can live with."""
    return not any(c.id == "docker" and c.level == FAIL for c in checks)


# ----- the running app's view of it -----


class Preflight:
    """The latest result, kept by the app. `refresh` looks again, and `watch` keeps looking."""

    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.checked_at: datetime | None = None
        self.cells_ready = True  # until a look says otherwise: tests and a fresh start must not be blocked by a missing check
        self._wake = asyncio.Event()

    @property
    def problems(self) -> list[Check]:
        return [c for c in self.checks if c.level != OK]

    def wake(self) -> None:
        """Look again now (the Docker host was changed in Settings)."""
        self._wake.set()

    async def refresh(self, maker: async_sessionmaker, scheduler=None, trail=None) -> None:
        async with maker() as session:
            cfg = await load_settings(session)
        before = {c.id: c.level for c in self.checks}
        self.checks = await run_checks(cfg)
        self.checked_at = datetime.now(UTC)
        ready = cells_can_run(self.checks)
        changed = ready != self.cells_ready
        self.cells_ready = ready
        if scheduler is not None:
            scheduler.cells_ready = ready
            if changed and ready:
                scheduler.wake()  # waiting tasks start as soon as Docker is back
        if trail is not None:
            if not before:  # the first look is the start's own: it records the whole list
                trail.event("preflight", checks=[c.to_dict() for c in self.checks], cells_ready=ready)
            else:
                for c in self.checks:
                    if before.get(c.id) != c.level:  # only what changed, so a long run's trail stays short
                        trail.event("check_changed", id=c.id, level=c.level, message=c.message)
        for c in self.problems:
            if before.get(c.id) in (None, OK):
                log.warning("Preflight: %s", c.message)
        if changed:
            log.warning("Cells %s", "can run again" if ready else "cannot run: tasks wait until Docker works")

    async def watch(self, maker: async_sessionmaker, scheduler=None, trail=None) -> None:
        while True:
            delay = RECHECK_PROBLEM_SECONDS if self.problems else RECHECK_OK_SECONDS
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), delay)
            self._wake.clear()
            try:
                await self.refresh(maker, scheduler, trail)
            except Exception:
                log.exception("The background check failed")
