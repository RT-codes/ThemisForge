"""Workflows that move and make tasks across boards, and the guard that keeps them from chasing a task for ever."""

import asyncio

from sqlalchemy import select, update

from app.models import Task
from app.workflows import Graph, WorkflowRunner, _Ctx
from tests.conftest import drain, make_task, register
from tests.test_workflows import (
    by_id,
    edge,
    make_workflow,
    node,
    run,
    runs_of,
    save,
    setup,
    status_trigger,
    wait_for_run,
    wait_for_runs,
)


async def boards_of(client, pid):
    [workspace] = (await client.get(f"/api/projects/{pid}/workspaces")).json()
    first = workspace["boards"][0]
    second = (await client.post(f"/api/workspaces/{workspace['id']}/boards", json={"name": "QA"})).json()
    return workspace, first, second


async def events(client, pid, **params):
    return (await client.get(f"/api/projects/{pid}/history", params=params)).json()


async def task_of(client, task_id):
    return (await client.get(f"/api/tasks/{task_id}")).json()


# ----- where a Trigger looks -----


async def test_a_trigger_can_watch_one_board_or_one_workspace(client, runner):
    _, pid = await setup(client)
    workspace, first, second = await boards_of(client, pid)
    elsewhere = (await client.post(f"/api/projects/{pid}/workspaces", json={"name": "Other"})).json()
    far = (await client.post(f"/api/workspaces/{elsewhere['id']}/boards", json={"name": "Far"})).json()
    on_board = await make_workflow(client, pid, "Board")
    in_workspace = await make_workflow(client, pid, "Workspace")
    for wid, where in ((on_board, f"b:{second['id']}"), (in_workspace, f"w:{elsewhere['id']}")):
        trigger = node("t", "trigger", type="task_status", status="review", where=where)
        await save(client, wid, [trigger, node("e", "end")], [edge("t", "e")])

    await make_task(client, pid, status="review")  # first board: neither watches it
    await asyncio.sleep(0.2)
    assert await runs_of(client, on_board) == [] and await runs_of(client, in_workspace) == []

    await make_task(client, pid, status="review", board_id=second["id"])
    await wait_for_runs(client, on_board, 1)
    assert await runs_of(client, in_workspace) == []

    await make_task(client, pid, status="review", board_id=far["id"])
    await wait_for_runs(client, in_workspace, 1)
    assert len(await runs_of(client, on_board)) == 1
    assert workspace["id"] and first["id"]


async def test_the_board_sees_which_workflows_watch_it(client, runner):
    _, pid = await setup(client)
    _, _, second = await boards_of(client, pid)
    wid = await make_workflow(client, pid)
    trigger = node("t", "trigger", type="task_status", status="done", where=f"b:{second['id']}")
    await save(client, wid, [trigger, node("e", "end")], [edge("t", "e")])
    (summary,) = [w for w in (await client.get(f"/api/projects/{pid}/workflows")).json() if w["id"] == wid]
    assert summary["watches"] == [{"status": "done", "where": f"b:{second['id']}"}]


# ----- making and moving tasks across boards -----


async def test_a_step_can_follow_up_the_task_that_started_the_run_on_another_board(client, runner):
    _, pid = await setup(client)
    _, first, second = await boards_of(client, pid)
    wid = await make_workflow(client, pid, "Hand over")
    await save(
        client,
        wid,
        [
            status_trigger("review"),
            node(
                "m",
                "task",
                action="create",
                title="Build it",
                description="From research",
                status="blocked",
                boardId=str(second["id"]),
                link="1",
            ),
        ],
        [edge("t", "m")],
    )
    origin = await make_task(client, pid, title="Research", status="backlog")
    await client.patch(f"/api/tasks/{origin['id']}", json={"status": "review"})
    (started,) = await wait_for_runs(client, wid, 1)
    detail = await wait_for_run(client, started["id"])
    assert detail["status"] == "succeeded", detail

    child = next(
        t for t in (await client.get(f"/api/projects/{pid}/tasks")).json() if t["title"] == "Build it"
    )
    assert (child["board_id"], child["origin_task_id"], child["status"], child["hops"]) == (
        second["id"],
        origin["id"],
        "blocked",
        1,
    )
    assert (await task_of(client, origin["id"]))["board_id"] == first["id"]  # the origin stays

    [spawned] = await events(client, pid, kind="task_spawned")
    assert spawned["actor"] == "Workflow Hand over" and spawned["cause"] == f"run:{started['id']}:m"


async def test_a_step_can_send_the_task_that_started_the_run_to_another_board(client, runner):
    _, pid = await setup(client)
    _, _, second = await boards_of(client, pid)
    wid = await make_workflow(client, pid, "Route")
    await save(
        client,
        wid,
        [
            status_trigger("review"),
            node("m", "task", action="move_trigger", status="done", boardId=str(second["id"])),
        ],
        [edge("t", "m")],
    )
    task = await make_task(client, pid, title="Ship it", status="backlog")
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "review"})
    await wait_for_runs(client, wid, 1)
    async with asyncio.timeout(10):
        while (moved := await task_of(client, task["id"]))["board_id"] != second["id"]:
            await asyncio.sleep(0.02)
    assert (moved["status"], moved["hops"]) == ("done", 1)
    [event] = await events(client, pid, kind="task_moved")
    assert (event["actor"], event["title"]) == ("Workflow Route", "Ship it")


async def test_a_step_whose_board_was_deleted_says_so(client, runner):
    _, pid = await setup(client)
    _, first, second = await boards_of(client, pid)
    await client.delete(f"/api/boards/{second['id']}", params={"move_to": first["id"]})
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("m", "task", action="create", title="x", boardId=str(second["id"]))],
        [edge("s", "m")],
    )
    assert detail["status"] == "failed" and "no longer exists" in by_id(detail)["m"]["error"]


async def test_a_step_makes_its_task_once(client, runner, maker):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    nodes = [node("s", "start"), node("m", "task", action="create", title="Once", status="backlog")]
    detail = await run(client, pid, nodes, [edge("s", "m")], wid=wid)
    assert detail["status"] == "succeeded"

    graph = Graph.model_validate({"nodes": nodes, "edges": [edge("s", "m")]})
    again = WorkflowRunner(maker, lambda: None)
    outcome = await again._task(
        _Ctx(detail["id"], pid, graph), by_id(detail)["m"]["id"], next(n for n in graph.nodes if n.id == "m")
    )
    assert outcome.status == "succeeded"
    tasks = (await client.get(f"/api/projects/{pid}/tasks")).json()
    assert [t["title"] for t in tasks] == ["Once"]
    async with maker() as s:
        assert (await s.scalar(select(Task.origin_key))) == f"run:{detail['id']}:m"


# ----- the loop guard -----


async def set_hops(maker, task_id, hops):
    async with maker() as s:
        await s.execute(update(Task).where(Task.id == task_id).values(hops=hops))
        await s.commit()


async def mover(client, pid, second):
    wid = await make_workflow(client, pid, "Mover")
    await save(
        client,
        wid,
        [
            status_trigger("review"),
            node("m", "task", action="move_trigger", status="done", boardId=str(second["id"])),
        ],
        [edge("t", "m")],
    )
    return wid


async def put_in_review(maker, task_id):
    """The task lands in Review without a person: as if another workflow had put it there."""
    async with maker() as s:
        await s.execute(update(Task).where(Task.id == task_id).values(status="review"))
        await s.commit()


async def test_automation_stops_at_the_hop_limit_and_says_why(client, runner, maker):
    _, pid = await setup(client)
    _, _, second = await boards_of(client, pid)
    wid = await mover(client, pid, second)
    await client.patch(f"/api/projects/{pid}", json={"automation": {"max_hops": 3}})
    task = await make_task(client, pid, status="backlog")

    await set_hops(maker, task["id"], 2)  # handled twice in a row: one more is allowed
    await put_in_review(maker, task["id"])
    await runner._fire([(pid, task["id"], "review")])
    (first_run,) = await wait_for_runs(client, wid, 1)
    assert (await wait_for_run(client, first_run["id"]))["status"] == "succeeded"
    assert (await task_of(client, task["id"]))["hops"] == 3

    await put_in_review(maker, task["id"])  # and now the limit is reached
    await runner._fire([(pid, task["id"], "review")])
    runs = await wait_for_runs(client, wid, 2)
    detail = await wait_for_run(client, runs[0]["id"])
    error = by_id(detail)["m"]["error"]
    assert detail["status"] == "failed" and "keep automation from looping" in error and "limit is 3" in error
    assert (await task_of(client, task["id"]))["hops"] == 3  # untouched
    [stopped] = await events(client, pid, kind="automation_stopped")
    assert (stopped["task_id"], stopped["data"]["limit"], stopped["actor"]) == (
        task["id"],
        3,
        "Workflow Mover",
    )


async def test_a_person_acting_on_a_task_starts_the_count_again(client, maker):
    await register(client)
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    _, first, second = await boards_of(client, pid)
    task = await make_task(client, pid)
    for by_hand in (
        lambda: client.patch(f"/api/tasks/{task['id']}", json={"status": "review"}),
        lambda: client.post(f"/api/tasks/{task['id']}/move", json={"board_id": second["id"]}),
    ):
        await set_hops(maker, task["id"], 5)
        assert (await by_hand()).status_code == 200
        assert (await task_of(client, task["id"]))["hops"] == 0
    assert first["id"]


async def drain_runs(client, wid):
    async with asyncio.timeout(10):
        while any(r["status"] == "running" for r in await runs_of(client, wid)):
            await asyncio.sleep(0.02)


async def test_a_task_can_have_a_hop_limit_of_its_own(client, runner, maker):
    _, pid = await setup(client)
    _, _, second = await boards_of(client, pid)
    wid = await mover(client, pid, second)
    task = await make_task(client, pid, status="backlog", max_hops=1)
    assert task["max_hops"] == 1 and task["hops"] == 0
    await set_hops(maker, task["id"], 1)
    await put_in_review(maker, task["id"])
    await runner._fire([(pid, task["id"], "review")])
    (started,) = await wait_for_runs(client, wid, 1)
    detail = await wait_for_run(client, started["id"])
    assert detail["status"] == "failed" and "limit is 1" in by_id(detail)["m"]["error"]


async def test_the_limit_comes_from_the_task_then_the_project_then_the_settings(client):
    await register(client)
    from app.app_settings import AppSettings
    from app.automation import hop_limit, start_cooldown
    from app.models import Project

    cfg = AppSettings(max_automation_hops=7, start_cooldown_seconds=5)
    task = Task(max_hops=None, cooldown_seconds=None)
    assert (hop_limit(cfg, None, task), start_cooldown(cfg, None, task)) == (7, 5)
    project = Project(automation={"max_hops": 4, "start_cooldown_seconds": 9})
    assert (hop_limit(cfg, project, task), start_cooldown(cfg, project, task)) == (4, 9)
    task = Task(max_hops=2, cooldown_seconds=0)  # zero is a real value, not "unset"
    assert (hop_limit(cfg, project, task), start_cooldown(cfg, project, task)) == (2, 0)


async def test_guard_settings_are_validated_and_can_be_put_back(client):
    await register(client)
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    assert (
        await client.patch(f"/api/projects/{pid}", json={"automation": {"max_hops": 0}})
    ).status_code == 422
    assert (await client.patch(f"/api/projects/{pid}", json={"automation": {"nope": 1}})).status_code == 422
    r = await client.patch(
        f"/api/projects/{pid}", json={"automation": {"max_hops": 5, "start_cooldown_seconds": 30}}
    )
    assert r.json()["automation"] == {"max_hops": 5, "start_cooldown_seconds": 30}
    assert (await client.patch(f"/api/projects/{pid}", json={"automation": None})).json()[
        "automation"
    ] is None

    task = await make_task(client, pid, cooldown_seconds=0, max_hops=3)
    assert (task["cooldown_seconds"], task["max_hops"]) == (0, 3)
    reset = (await client.patch(f"/api/tasks/{task['id']}", json={"cooldown_seconds": None})).json()
    assert (reset["cooldown_seconds"], reset["max_hops"]) == (None, 3)
    assert (await client.patch(f"/api/tasks/{task['id']}", json={"max_hops": 500})).status_code == 422
    settings = (await client.get("/api/settings")).json()
    assert settings["max_automation_hops"] == 10


async def test_the_start_cooldown_can_be_set_per_project_and_per_task(client, scheduler, cells):
    await register(client)
    pid = (await client.post("/api/projects", json={"name": "P"})).json()["id"]
    waits = await make_task(client, pid, title="waits", status="ready", cooldown_seconds=3600)
    goes = await make_task(client, pid, title="goes", status="ready", cooldown_seconds=0)
    await client.patch(f"/api/projects/{pid}", json={"automation": {"start_cooldown_seconds": 3600}})
    inherits = await make_task(client, pid, title="inherits", status="ready")  # the project's hour

    await scheduler.tick()
    await drain(scheduler)
    started = {t["title"]: t for t in (await client.get(f"/api/projects/{pid}/tasks")).json()}
    assert started["goes"]["last_run_at"] is not None
    assert started["waits"]["last_run_at"] is None and started["inherits"]["last_run_at"] is None

    await client.patch(f"/api/projects/{pid}", json={"automation": None})  # the settings' 0 again
    await client.patch(f"/api/tasks/{waits['id']}", json={"cooldown_seconds": None})
    await scheduler.tick()
    await drain(scheduler)
    after = {t["title"]: t for t in (await client.get(f"/api/projects/{pid}/tasks")).json()}
    assert after["waits"]["last_run_at"] is not None and after["inherits"]["last_run_at"] is not None
    assert inherits["id"] != goes["id"]
