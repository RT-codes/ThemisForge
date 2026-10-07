import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .cells import make_cell_manager
from .codex import CodexLogins
from .config import DEFAULT_SECRET_KEY, settings
from .db import SessionLocal
from .migrate import upgrade_database
from .preflight import Preflight
from .project_config import sync_all_configs
from .routers import access, agents, auth, codex, projects, skills, system, tools, volumes, workflows
from .runlog import Trail, setup_file_logging
from .scheduler import Scheduler
from .version import build_info
from .workflows import WorkflowRunner

log = logging.getLogger("themis")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    trail: Trail = app.state.trail
    preflight: Preflight = app.state.preflight
    scheduler: Scheduler = app.state.scheduler
    setup_file_logging(settings.log_dir)
    run_id = trail.begin()
    log.info("Themis %s starting (run %s)", build_info().version, run_id)
    watcher: asyncio.Task | None = None
    try:
        if settings.secret_key == DEFAULT_SECRET_KEY:
            log.warning(
                "THEMIS_SECRET_KEY is the insecure default: set a real one before exposing this server"
            )
        await upgrade_database()
        await sync_all_configs(SessionLocal)
        # What Themis needs is checked every start, and kept checked: a problem is shown, not fatal (see preflight.py)
        await preflight.refresh(SessionLocal, scheduler, trail)
        await app.state.workflows.reconcile()
        if settings.scheduler_enabled:
            await scheduler.start()
        watcher = asyncio.create_task(
            preflight.watch(SessionLocal, scheduler, trail), name="themis-preflight"
        )
    except Exception as e:
        trail.event("startup_failed", error=f"{type(e).__name__}: {e}")
        log.exception("Themis could not start")
        raise
    trail.event("ready", cells_ready=preflight.cells_ready)
    yield
    if watcher:
        watcher.cancel()
    await app.state.workflows.shutdown()
    await scheduler.stop()
    await app.state.codex_logins.shutdown()
    trail.end()
    log.info("Themis stopped")


# The interactive API reference lives under /api so that /docs is the user documentation (a frontend page).
app = FastAPI(
    title="Themis",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.state.scheduler = Scheduler(
    SessionLocal, make_cell_manager(), interval=settings.scheduler_interval_seconds
)

app.state.trail = Trail(settings.log_dir)
app.state.preflight = Preflight()
app.state.codex_logins = CodexLogins(SessionLocal)
app.state.workflows = WorkflowRunner(SessionLocal, lambda: app.state.scheduler)
app.state.scheduler.workflows = app.state.workflows

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(access.router)
api.include_router(projects.router)
api.include_router(system.router)
api.include_router(codex.router)
api.include_router(workflows.router)
api.include_router(volumes.router)
api.include_router(agents.router)
api.include_router(skills.router)
api.include_router(tools.router)


@api.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": build_info().version}


@api.get("/version")
async def version() -> dict[str, str]:
    """Which Themis this is (public, like /health): the release number, the commit it was built from and whether it is a
    release bundle or a git checkout."""
    return build_info().to_dict()


app.include_router(api)

# Serve the built frontend (single-page app) when it exists.
_dist = settings.frontend_dist
if _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (_dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(_dist.resolve()):
            return FileResponse(
                candidate, headers={"Cache-Control": "no-cache"} if path.startswith("favicon.") else None
            )
        # index.html names the hashed asset files, so it must never be served from a browser cache
        return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})
