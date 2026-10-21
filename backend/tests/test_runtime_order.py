"""The refactor must preserve transaction, reservation and lifecycle order."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from sqlalchemy import event
from sqlalchemy.orm import Session

from app import bootstrap
from app.persistence.models import Task
from tests.conftest import drain, make_project, make_task, register


async def test_folders_are_reserved_during_commit_and_attempts_launch_after_commit(
    client, scheduler, maker, monkeypatch
):
    await register(client)
    project = await make_project(client)
    task = await make_task(client, project["id"], status="ready")
    assert (await client.get(f"/api/projects/{project['id']}/volumes")).status_code == 200
    committed = []

    def after_commit(session):
        if session.get_bind() is maker.kw["bind"].sync_engine:
            assert not scheduler.runs.live
            assert scheduler.runs.starting
            volume_ids, task_id, _ = scheduler.runs.starting[0]
            assert task_id == task["id"]
            assert volume_ids
            for volume_id in volume_ids:
                assert scheduler.runs_using(volume_id) == [(task["id"], task["title"])]
            committed.append(True)

    launch = scheduler._launch

    def checked_launch(*args):
        assert committed == [True]
        launch(*args)

    monkeypatch.setattr(scheduler, "_launch", checked_launch)
    event.listen(Session, "after_commit", after_commit)
    try:
        assert await scheduler.tick() == 1
    finally:
        event.remove(Session, "after_commit", after_commit)
    assert not scheduler.runs.starting
    await drain(scheduler)


async def test_status_triggers_discard_rollbacks_and_fire_after_commit(client, runner, maker, monkeypatch):
    await register(client)
    project = await make_project(client)
    task = await make_task(client, project["id"], status="backlog")
    await asyncio.gather(*runner.triggers._firing)
    fire = AsyncMock()
    monkeypatch.setattr(runner.triggers, "_fire", fire)

    async with maker() as session:
        row = await session.get(Task, task["id"])
        row.status = "review"
        await session.flush()
        assert session.sync_session.info["status_moves"]
        fire.assert_not_called()
        await session.rollback()
        assert "status_moves" not in session.sync_session.info
    fire.assert_not_called()

    async with maker() as session:
        row = await session.get(Task, task["id"])
        row.status = "review"
        await session.flush()
        fire.assert_not_called()
        await session.commit()
    await asyncio.gather(*runner.triggers._firing)
    fire.assert_awaited_once_with([(project["id"], task["id"], "review")])


async def test_startup_and_shutdown_keep_the_existing_dependency_order(monkeypatch):
    calls = []

    def step(name):
        async def record(*args):
            calls.append(name)

        return record

    @asynccontextmanager
    async def control_running():
        calls.append("control.start")
        yield
        calls.append("control.stop")

    async def watch(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(
        bootstrap,
        "settings",
        SimpleNamespace(
            ensure_state_dirs=Mock(), scheduler_enabled=True, log_dir="unused", secret_key="test"
        ),
    )
    monkeypatch.setattr(bootstrap, "setup_file_logging", Mock())
    monkeypatch.setattr(bootstrap, "upgrade_database", step("migrations"))
    monkeypatch.setattr(bootstrap, "sync_all_configs", step("config.sync"))
    state = SimpleNamespace(
        trail=SimpleNamespace(
            begin=Mock(return_value="test"), event=Mock(), end=lambda: calls.append("trail.end")
        ),
        preflight=SimpleNamespace(refresh=step("preflight"), watch=watch, cells_ready=True),
        scheduler=SimpleNamespace(start=step("scheduler.start"), stop=step("scheduler.stop")),
        workflows=SimpleNamespace(
            reconcile=step("workflows.reconcile"),
            resume_parked=step("workflows.resume"),
            shutdown=step("workflows.stop"),
        ),
        control=SimpleNamespace(running=control_running),
        codex_logins=SimpleNamespace(shutdown=step("codex.stop")),
        device_logins=SimpleNamespace(shutdown=step("connections.stop")),
    )
    async with bootstrap.lifespan(SimpleNamespace(state=state)):
        calls.append("serving")
    assert calls == [
        "migrations",
        "config.sync",
        "preflight",
        "workflows.reconcile",
        "scheduler.start",
        "workflows.resume",
        "control.start",
        "serving",
        "control.stop",
        "workflows.stop",
        "scheduler.stop",
        "codex.stop",
        "connections.stop",
        "trail.end",
    ]
