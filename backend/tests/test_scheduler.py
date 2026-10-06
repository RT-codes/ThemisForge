import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.cells import CellResult, CellSpec
from app.models import Attempt, Task, TaskStatus, utcnow
from tests.conftest import drain, make_project, make_task, register


async def test_ready_task_runs_in_a_cell_and_is_recorded(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="Write report", status="ready")

    assert await scheduler.tick() == 1
    await drain(scheduler)

    done = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert done["status"] == "done" and done["last_attempt_status"] == "succeeded"
    attempts = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()
    assert len(attempts) == 1 and attempts[0]["exit_code"] == 0
    detail = (await client.get(f"/api/attempts/{attempts[0]['id']}")).json()
    assert "Write report" in detail["log"] and "finished" in detail["result"]


async def test_failing_cell_marks_the_task_failed_and_run_now_retries(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="will fail", status="ready")
    await scheduler.tick()
    await drain(scheduler)
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "failed"

    assert (await client.post(f"/api/tasks/{task['id']}/run")).json()["status"] == "ready"
    await scheduler.tick()
    await drain(scheduler)
    assert len((await client.get(f"/api/tasks/{task['id']}/attempts")).json()) == 2


async def test_review_on_success(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready", review_on_success=True)
    await scheduler.tick()
    await drain(scheduler)
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "review"


async def test_future_task_waits_until_due(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    soon = (utcnow() + timedelta(hours=1)).isoformat()
    task = await make_task(client, pid, status="ready", schedule_kind="once", run_at=soon)
    assert await scheduler.tick() == 0
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "ready"

    past = (utcnow() - timedelta(minutes=1)).isoformat()
    await client.patch(f"/api/tasks/{task['id']}", json={"run_at": past})
    assert await scheduler.tick() == 1
    await drain(scheduler)


async def test_recurring_task_goes_back_to_ready_with_a_future_next_run(client, scheduler, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready", schedule_kind="cron", cron="0 9 * * *")
    async with maker() as s:  # make it due now
        (await s.get(Task, task["id"])).next_run_at = utcnow() - timedelta(seconds=1)
        await s.commit()

    assert await scheduler.tick() == 1
    await drain(scheduler)
    after = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert after["status"] == "ready" and after["last_attempt_status"] == "succeeded"
    assert after["next_run_at"] > utcnow().isoformat()
    assert await scheduler.tick() == 0


async def test_concurrency_limit(client, scheduler, cells, monkeypatch):
    await register(client)
    await client.put("/api/settings", json={"budget": {"cpus": 1, "memory_mb": 1024}})
    pid = (await make_project(client))["id"]
    a = await make_task(client, pid, title="a", status="ready")
    b = await make_task(client, pid, title="b", status="ready")

    gate = asyncio.Event()

    async def slow_run(spec: CellSpec, on_log):
        await gate.wait()
        return CellResult(exit_code=0)

    monkeypatch.setattr(cells, "run", slow_run)
    assert await scheduler.tick() == 1
    assert await scheduler.tick() == 0  # the only slot is taken
    assert scheduler.active_cells == 1
    gate.set()
    await drain(scheduler)
    assert await scheduler.tick() == 1  # the second task now gets its turn
    await drain(scheduler)
    statuses = {(await client.get(f"/api/tasks/{t['id']}")).json()["status"] for t in (a, b)}
    assert statuses == {"done"}


async def test_cancel_a_running_task(client, scheduler, cells, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready")

    async def forever(spec: CellSpec, on_log):
        await on_log("working\n")
        await asyncio.Event().wait()

    monkeypatch.setattr(cells, "run", forever)
    await scheduler.tick()
    await asyncio.sleep(0.05)
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "running"
    assert (await client.patch(f"/api/tasks/{task['id']}", json={"title": "x"})).status_code == 409
    assert (await client.delete(f"/api/tasks/{task['id']}")).status_code == 409

    cancelled = (await client.post(f"/api/tasks/{task['id']}/cancel")).json()
    assert cancelled["status"] == "blocked" and cancelled["last_attempt_status"] == "cancelled"
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    assert "[Cancelled]" in (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    assert (await client.post(f"/api/tasks/{task['id']}/cancel")).status_code == 409


async def test_restart_recovery(client, scheduler, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    once = await make_task(client, pid, title="one-off", status="ready")
    cron = await make_task(
        client, pid, title="recurring", status="ready", schedule_kind="cron", cron="0 9 * * *"
    )
    async with maker() as s:  # simulate a crash: both were mid-flight
        for t in (once, cron):
            task = await s.get(Task, t["id"])
            task.status = TaskStatus.RUNNING
            task.next_run_at = None
            s.add(Attempt(task_id=task.id))
        await s.commit()

    await scheduler.reconcile()

    once_after = (await client.get(f"/api/tasks/{once['id']}")).json()
    cron_after = (await client.get(f"/api/tasks/{cron['id']}")).json()
    assert once_after["status"] == "failed"  # not silently re-run: a human decides
    assert cron_after["status"] == "ready" and cron_after["next_run_at"] is not None
    async with maker() as s:
        attempts = (await s.scalars(select(Attempt))).all()
        assert {a.status for a in attempts} == {"failed"}
        assert all("restarted" in a.log for a in attempts)


async def test_unexpected_cell_error_is_recorded(client, scheduler, cells, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready")

    async def boom(spec, on_log):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cells, "run", boom)
    await scheduler.tick()
    await drain(scheduler)
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "failed"
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    assert "kaboom" in (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]


async def test_running_recurring_task_stays_on_the_timeline(client, scheduler, cells, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready", schedule_kind="cron", cron="0 * * * *")

    async def forever(spec: CellSpec, on_log):
        await asyncio.Event().wait()

    monkeypatch.setattr(cells, "run", forever)
    await client.post(f"/api/tasks/{task['id']}/run")
    await scheduler.tick()
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "running"
    assert len((await client.get(f"/api/projects/{pid}/schedule?hours=6")).json()) >= 5
    await scheduler.stop()
