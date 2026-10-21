"""Construct the runtime and preserve the server's startup/shutdown sequence."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from app.config import DEFAULT_SECRET_KEY, settings
from app.control.server import ControlPlane
from app.execution.cells.manager import make_cell_manager
from app.execution.scheduler import Scheduler
from app.features.connections.codex import CodexLogins
from app.features.connections.service import DeviceLogins
from app.features.project_config.store import sync_all_configs
from app.features.system.preflight import Preflight
from app.features.system.runlog import Trail, setup_file_logging
from app.features.system.updates import UpdateChecker
from app.features.system.version import build_info
from app.features.tools.auth import McpLogins
from app.features.workflows.runner import WorkflowRunner
from app.persistence.db import SessionLocal
from app.persistence.migrate import upgrade_database

log = logging.getLogger("themis")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    trail: Trail = app.state.trail
    preflight: Preflight = app.state.preflight
    scheduler: Scheduler = app.state.scheduler
    settings.ensure_state_dirs()
    setup_file_logging(settings.log_dir)
    run_id = trail.begin()
    log.info("Themis %s starting (run %s)", build_info().version, run_id)
    served = AsyncExitStack()  # what stays open while requests are served
    watcher: asyncio.Task | None = None
    update_watcher: asyncio.Task | None = None
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
        await (
            app.state.workflows.resume_parked()
        )  # after the scheduler: the steps below an approval gate need it
        await served.enter_async_context(app.state.control.running())
        watcher = asyncio.create_task(
            preflight.watch(SessionLocal, scheduler, trail), name="themis-preflight"
        )
    except Exception as e:
        trail.event("startup_failed", error=f"{type(e).__name__}: {e}")
        log.exception("Themis could not start")
        raise
    trail.event("ready", cells_ready=preflight.cells_ready)
    yield
    for task in (watcher, update_watcher):
        if task:
            task.cancel()
    await served.aclose()
    await app.state.workflows.shutdown()
    await scheduler.stop()
    await app.state.codex_logins.shutdown()
    await app.state.device_logins.shutdown()
    trail.end()
    log.info("Themis stopped")


def configure_runtime(app: FastAPI) -> None:
    app.state.scheduler = Scheduler(
        SessionLocal, make_cell_manager(), interval=settings.scheduler_interval_seconds
    )

    app.state.trail = Trail(settings.log_dir)

    app.state.preflight = Preflight()

    app.state.updates = UpdateChecker()

    app.state.codex_logins = CodexLogins(SessionLocal)

    app.state.device_logins = DeviceLogins(SessionLocal)

    app.state.mcp_logins = McpLogins(SessionLocal)

    app.state.scheduler.mcp_logins = app.state.mcp_logins

    app.state.workflows = WorkflowRunner(SessionLocal, lambda: app.state.scheduler)

    app.state.control = ControlPlane(SessionLocal)

    app.state.scheduler.workflows = app.state.workflows
