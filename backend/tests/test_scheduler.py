import asyncio
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.execution.active_runs import _Live
from app.execution.budget import Cost
from app.execution.cells.contract import CellError, CellResult, CellSpec, CellTimeout
from app.execution.failures import _judge
from app.features.tools.keys import Redactor
from app.persistence.models import Attempt, AttemptStatus, Task, TaskStatus, utcnow
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


async def test_tasks_beyond_the_budget_wait_in_ready_and_start_in_order(
    client, scheduler, cells, monkeypatch
):
    await register(client)
    await client.put("/api/settings", json={"budget": {"cpus": 2, "memory_mb": 2048}})
    pid = (await make_project(client))["id"]
    tasks = [await make_task(client, pid, title=f"t{i}", status="ready") for i in range(5)]

    gate = asyncio.Event()

    async def slow_run(spec: CellSpec, on_log):
        await gate.wait()
        return CellResult(exit_code=0)

    monkeypatch.setattr(cells, "run", slow_run)
    assert await scheduler.tick() == 2  # two cells fit; the other three are not started and not failed
    assert scheduler.active_cells == 2
    states = [(await client.get(f"/api/tasks/{t['id']}")).json()["status"] for t in tasks]
    assert states == ["running", "running", "ready", "ready", "ready"]
    gate.set()
    await drain(scheduler)
    assert await scheduler.tick() == 2  # as cells finish, the next ones in line start
    await drain(scheduler)
    assert await scheduler.tick() == 1
    await drain(scheduler)
    states = {(await client.get(f"/api/tasks/{t['id']}")).json()["status"] for t in tasks}
    assert states == {"done"}


async def test_ready_task_waits_for_the_start_cooldown(client, scheduler):
    await register(client)
    await client.put("/api/settings", json={"start_cooldown_seconds": 60})
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready")
    assert await scheduler.tick() == 0  # only just moved to Ready
    await client.put("/api/settings", json={"start_cooldown_seconds": 0})
    assert await scheduler.tick() == 1
    await drain(scheduler)
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "done"


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


# ----- the steps a tick and a run are made of, one at a time -----


class _Writes:
    """Stands in for the attempt's log buffer: collects what a run wrote to it."""

    def __init__(self) -> None:
        self.text = ""

    async def write(self, chunk: str) -> None:
        self.text += chunk


def _plan(cpus: float, volume_ids: tuple[int, ...] = (), writers: tuple[int, ...] = ()):
    """The parts of a planned cell that choosing which cells start looks at."""
    mounts = [SimpleNamespace(volume_id=v, lock=v in writers) for v in volume_ids]
    return SimpleNamespace(
        cost=Cost(cpus, 512), mounts=mounts, locks=frozenset(m.volume_id for m in mounts if m.lock)
    )


def test_a_run_is_judged_by_its_exit_code_unless_the_agent_said_it_was_blocked():
    redact = Redactor([])
    assert _judge(CellResult(exit_code=0), None, 0, redact) == (AttemptStatus.SUCCEEDED, None)
    outcome, failure = _judge(CellResult(exit_code=3), None, 0, redact)
    assert outcome == AttemptStatus.FAILED and "exit code 3" in failure["reason"]
    # an agent that stopped and wrote why is the answer, even when the program itself exited cleanly
    blocked = CellResult(exit_code=0, blocked="Reason: no browser in the cell.\nFix: add one to the image.\n")
    assert _judge(blocked, None, 0, redact) == (
        AttemptStatus.FAILED,
        {"source": "agent", "reason": "no browser in the cell.", "action": "add one to the image."},
    )


def test_what_the_agent_wrote_when_blocked_never_shows_a_key():
    secret = "sk-this-is-a-secret-value"
    _, failure = _judge(
        CellResult(exit_code=1, blocked=f"Reason: {secret} was refused"), None, 0, Redactor([secret])
    )
    assert secret not in failure["reason"] and failure["source"] == "agent"


def test_a_writer_waits_while_another_run_holds_its_folder(scheduler):
    scheduler.runs.live[1] = _Live(task=None, locks=frozenset({7}))
    waiting, free = _plan(1, (7,), writers=(7,)), _plan(1, (8,), writers=(8,))
    assert scheduler.runs.admit(Cost(8, 8192), [waiting, free]) == [free]  # the next task goes first


def test_two_writers_of_one_folder_never_start_in_the_same_tick(scheduler):
    first, second, reader = _plan(1, (7,), writers=(7,)), _plan(1, (7,), writers=(7,)), _plan(1, (7,))
    assert scheduler.runs.admit(Cost(8, 8192), [first, second, reader]) == [first, reader]


def test_a_folder_that_is_being_renamed_starts_nothing(scheduler):
    scheduler.runs.renaming_ids.add(7)
    started = scheduler.runs.admit(Cost(8, 8192), [(a := _plan(1, (7,))), (b := _plan(1, (8,)))])
    assert started == [b] and a not in started


def test_cells_start_in_order_as_far_as_the_budget_reaches(scheduler):
    plans = [_plan(2), _plan(2), _plan(2)]
    assert scheduler.runs.admit(Cost(4, 8192), plans) == plans[:2]
    # a cell that is already running uses part of the budget
    scheduler.runs.live[1] = _Live(task=None, spec=SimpleNamespace(cpus=2, memory_mb=512))
    assert scheduler.runs.admit(Cost(4, 8192), plans) == plans[:1]


async def test_a_cancel_the_person_asked_for_is_not_a_failure(scheduler):
    scheduler.runs.live[1] = _Live(task=None, cancel_reason="user")
    buf = _Writes()
    assert await scheduler.executor._explain(asyncio.CancelledError(), 1, buf) == (
        AttemptStatus.CANCELLED,
        None,
    )
    assert "[Cancelled]" in buf.text


async def test_a_run_cut_off_by_a_shutdown_fails_and_says_to_run_it_again(scheduler):
    scheduler.runs.live[1] = _Live(task=None, cancel_reason="shutdown")
    buf = _Writes()
    outcome, failure = await scheduler.executor._explain(asyncio.CancelledError(), 1, buf)
    assert outcome == AttemptStatus.FAILED and failure["action"] == "Run it again with Run now."
    assert "shut down" in buf.text


async def test_each_kind_of_error_ends_the_attempt_with_its_own_reason(scheduler, caplog):
    buf = _Writes()
    outcome, failure = await scheduler.executor._explain(CellTimeout("took too long"), 1, buf)
    assert (
        outcome == AttemptStatus.FAILED
        and failure["reason"] == "took too long"
        and "time limit" in failure["action"]
    )
    outcome, failure = await scheduler.executor._explain(CellError("no docker"), 1, buf)
    assert failure["reason"] == "no docker" and failure["action"] == ""
    outcome, failure = await scheduler.executor._explain(RuntimeError("boom"), 1, buf)
    assert "unexpected error: boom" in failure["reason"] and "a bug in Themis" in failure["action"]
    assert "attempt 1 crashed" in caplog.text  # a bug is logged with its traceback; the others are not
