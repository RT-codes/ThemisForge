import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .cells import make_cell_manager
from .config import DEFAULT_SECRET_KEY, settings
from .db import SessionLocal
from .migrate import upgrade_database
from .routers import auth, projects, system
from .scheduler import Scheduler

log = logging.getLogger("themis")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.secret_key == DEFAULT_SECRET_KEY:
        log.warning("THEMIS_SECRET_KEY is the insecure default: set a real one before exposing this server")
    await upgrade_database()
    scheduler: Scheduler = app.state.scheduler
    if settings.scheduler_enabled:
        await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(title="ThemisForge", lifespan=lifespan)
app.state.scheduler = Scheduler(
    SessionLocal, make_cell_manager(), interval=settings.scheduler_interval_seconds
)

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(projects.router)
api.include_router(system.router)


@api.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
