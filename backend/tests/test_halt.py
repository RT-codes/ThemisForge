"""Halting a project or a board, and stopping one task: nothing starts while halted, what was running is stopped, and
what was interrupted waits in Blocked instead of starting again by itself."""

import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.cells import CellSpec
from app.models import Task, utcnow
from tests.conftest import drain, make_project, make_task, register
from tests.test_harness import connect
from tests.test_workflows import attempt_of, edge, make_workflow, node, play_task, save, setup


async def board_of(client, pid: int, name: str = "QA") -> dict:
    workspace = (await client.get(f"/api/projects/{pid}/workspaces")).json()[0]
    r = await client.post(f"/api/workspaces/{workspace['id']}/boards", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


async def status_of(client, task: dict) -> str:
    return (await client.get(f"/api/tasks/{task['id']}")).json()["status"]


def hold_cells(cells, monkeypatch) -> asyncio.Event:
    """Cells that run until told to finish, so a test can act while they are running."""
    gate = asyncio.Event()

    async def forever(spec: CellSpec, on_log):
        await on_log("working\n")
        await gate.wait()
        return type("R", (), {"exit_code": 0, "result": "", "writeback": {}})()

    monkeypatch.setattr(cells, "run", forever)
    return gate


# ----- nothing starts while halted -----


async def test_a_halted_project_starts_nothing_until_it_is_resumed(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready")
    halted = (await client.post(f"/api/projects/{pid}/halt", json={})).json()
    assert halted["halted_at"] is not None

    assert await scheduler.tick() == 0
    assert await status_of(client, task) == "ready"  # still waiting in line, not failed or moved
    assert (await client.post(f"/api/tasks/{task['id']}/run")).status_code == 409  # not even by hand

    resumed = (await client.post(f"/api/projects/{pid}/resume")).json()
    assert resumed["halted_at"] is None
    assert await scheduler.tick() == 1  # the queued task goes on, nothing was lost
    await drain(scheduler)
    assert await status_of(client, task) == "done"


async def test_a_halted_board_holds_only_its_own_tasks(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    qa = await board_of(client, pid)
    held = await make_task(client, pid, title="held", status="ready", board_id=qa["id"])
    free = await make_task(client, pid, title="free", status="ready")
    assert (await client.post(f"/api/boards/{qa['id']}/halt", json={})).json()["halted_at"] is not None

    assert await scheduler.tick() == 1
    await drain(scheduler)
    assert await status_of(client, free) == "done" and await status_of(client, held) == "ready"
    assert (await client.post(f"/api/tasks/{held['id']}/run")).status_code == 409

    assert (await client.post(f"/api/boards/{qa['id']}/resume")).json()["halted_at"] is None
    assert await scheduler.tick() == 1
    await drain(scheduler)
    assert await status_of(client, held) == "done"


async def test_halting_a_board_does_not_halt_the_project(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    qa = await board_of(client, pid)
    await client.post(f"/api/boards/{qa['id']}/halt", json={})
    assert (await client.get(f"/api/projects/{pid}")).json()["halted_at"] is None


# ----- stopping what is running -----


async def test_halt_stops_what_runs_and_parks_it_in_blocked(client, scheduler, cells, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    hold_cells(cells, monkeypatch)
    await client.put("/api/settings", json={"budget": {"cpus": 1, "memory_mb": 1024}})  # room for one cell
    task = await make_task(client, pid, status="ready")
    waiting = await make_task(client, pid, title="next in line", status="ready")
    await scheduler.tick()
    await asyncio.sleep(0.05)
    assert await status_of(client, task) == "running"

    await client.post(f"/api/projects/{pid}/halt", json={})
    stopped = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert stopped["status"] == "blocked" and stopped["last_attempt_status"] == "cancelled"
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    assert "[Cancelled]" in (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]

    assert await scheduler.tick() == 0
    assert await status_of(client, waiting) == "ready"
    # resuming does not start the interrupted task again: it waits for a decision
    await client.post(f"/api/projects/{pid}/resume")
    assert await status_of(client, task) == "blocked"
    history = (await client.get(f"/api/projects/{pid}/history")).json()
    kinds = (
        [e["kind"] for e in history["events"]] if isinstance(history, dict) else [e["kind"] for e in history]
    )
    assert "halted" in kinds and "resumed" in kinds


async def test_halt_can_let_running_work_finish(client, scheduler, cells, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    gate = hold_cells(cells, monkeypatch)
    running = await make_task(client, pid, title="running", status="ready")
    queued = await make_task(client, pid, title="queued", status="ready")
    await client.put("/api/settings", json={"budget": {"cpus": 1, "memory_mb": 1024}})
    await scheduler.tick()
    await asyncio.sleep(0.05)
    assert await status_of(client, running) == "running"

    r = await client.post(f"/api/projects/{pid}/halt", json={"stop_running": False})
    assert r.status_code == 200
    assert await status_of(client, running) == "running"  # a pause: it carries on
    gate.set()
    await drain(scheduler)
    assert await status_of(client, running) == "done"
    assert (
        await scheduler.tick() == 0 and await status_of(client, queued) == "ready"
    )  # and nothing new starts


async def test_halting_a_board_stops_only_the_tasks_on_it(client, scheduler, cells, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    qa = await board_of(client, pid)
    hold_cells(cells, monkeypatch)
    mine = await make_task(client, pid, title="on qa", status="ready", board_id=qa["id"])
    other = await make_task(client, pid, title="elsewhere", status="ready")
    await scheduler.tick()
    await asyncio.sleep(0.05)
    await client.post(f"/api/boards/{qa['id']}/halt", json={})
    assert await status_of(client, mine) == "blocked"
    assert await status_of(client, other) == "running"
    await client.post(f"/api/tasks/{other['id']}/cancel")


# ----- recurring tasks keep their schedule -----


async def test_stopping_a_recurring_task_by_hand_only_skips_that_run(client, scheduler, cells, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    hold_cells(cells, monkeypatch)
    task = await make_task(client, pid, status="ready", schedule_kind="cron", cron="0 9 * * *")
    await client.post(f"/api/tasks/{task['id']}/run")  # its time is tomorrow morning: start this one by hand
    await scheduler.tick()
    await asyncio.sleep(0.05)
    assert await status_of(client, task) == "running"

    stopped = (await client.post(f"/api/tasks/{task['id']}/cancel")).json()
    assert (
        stopped["status"] == "ready" and stopped["schedule_kind"] == "cron" and stopped["cron"] == "0 9 * * *"
    )
    assert stopped["next_run_at"] is not None and stopped["last_attempt_status"] == "cancelled"


async def test_resuming_does_not_run_what_a_recurring_task_missed(client, scheduler, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready", schedule_kind="cron", cron="0 9 * * *")
    await client.post(f"/api/projects/{pid}/halt", json={})
    async with maker() as s:  # the time it was due passed while the project was halted
        row = await s.get(Task, task["id"])
        row.next_run_at = utcnow() - timedelta(hours=3)
        await s.commit()
    await client.post(f"/api/projects/{pid}/resume")
    assert await scheduler.tick() == 0  # not a burst of what was missed
    again = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert again["status"] == "ready" and again["next_run_at"] > utcnow().isoformat()


# ----- workflows -----


async def test_a_halted_project_refuses_manual_runs_and_starts_no_workflows(client, runner, cells, maker):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid, "Flow")
    await save(client, wid, [node("s", "start"), node("e", "end")], [edge("s", "e")])
    listener = await make_workflow(client, pid, "Listener")
    await save(
        client, listener, [node("t", "trigger", type="task_status", status="backlog"), node("e", "end")],
        [edge("t", "e")],
    )  # fmt: skip
    await client.post(f"/api/projects/{pid}/halt", json={})
    refused = await client.post(f"/api/workflows/{wid}/runs")
    assert refused.status_code == 409 and "halted" in refused.json()["detail"]
    await make_task(client, pid, title="lands in backlog")  # a task arriving in a watched status
    await asyncio.sleep(0.3)
    assert (await client.get(f"/api/workflows/{listener}/runs")).json() == []
    await client.post(f"/api/projects/{pid}/resume")
    assert (await client.post(f"/api/workflows/{wid}/runs")).status_code == 201


async def test_halt_stops_a_task_playing_workflows_and_the_cell_under_it(
    client, runner, scheduler, cells, maker, monkeypatch
):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    hold_cells(cells, monkeypatch)
    wid = await make_workflow(client, pid, "Long")
    await save(
        client, wid,
        [node("s", "start"), node("a", "agent", "Slow step", harness="codex", instructions="Take a while"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )  # fmt: skip
    task = await play_task(client, pid, wid)
    async with asyncio.timeout(10):
        while not cells_started(cells, scheduler):
            await asyncio.sleep(0.02)
    await client.post(f"/api/projects/{pid}/halt", json={})
    done = await attempt_of(client, task["id"])
    assert done["status"] == "cancelled"
    assert await status_of(client, task) == "blocked"
    async with maker() as s:
        step = await s.scalar(select(Task).where(Task.title == "Slow step"))
        assert step is not None and step.status != "running"
    assert not scheduler._live


def cells_started(cells, scheduler) -> bool:
    return any(live.cell for live in scheduler._live.values())
