"""Duplicating a task: the same request and the same way of running, parked in the Backlog, with none of its past."""

from app.models import Task
from tests.conftest import make_project, make_task, register
from tests.test_workflows import make_workflow


async def test_a_copy_is_parked_in_the_backlog_with_what_the_task_asks_for(client):
    await register(client)
    pid = (await make_project(client))["id"]
    props = [{"key": "priority", "name": "Priority", "type": "select", "options": ["High", "Low"]}]
    assert (await client.patch(f"/api/projects/{pid}", json={"properties": props})).status_code == 200
    wid = await make_workflow(client, pid)
    task = await make_task(
        client,
        pid,
        title="Improve it",
        description="Focus on what a user notices",
        status="blocked",
        properties={"priority": "High"},
        review_on_success=True,
        harness="workflow",
        workflow_ids=[wid],
        cooldown_seconds=30,
        max_hops=4,
    )

    r = await client.post(f"/api/tasks/{task['id']}/duplicate")
    assert r.status_code == 201, r.text
    copy = r.json()
    assert copy["id"] != task["id"]
    assert copy["title"] == "Copy of Improve it"
    assert copy["status"] == "backlog"  # whatever the original's status was
    assert copy["board_id"] == task["board_id"]
    assert copy["description"] == "Focus on what a user notices"
    assert copy["properties"] == {"priority": "High"}
    assert copy["review_on_success"] is True
    assert copy["harness"] == "workflow" and [s["workflow_id"] for s in copy["stages"]] == [wid]
    assert [s["status"] for s in copy["stages"]] == ["pending"]
    assert (copy["cooldown_seconds"], copy["max_hops"]) == (30, 4)

    again = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert again["status"] == "blocked" and again["title"] == "Improve it"  # the original is left alone


async def test_a_copy_of_a_recurring_task_keeps_its_schedule_but_does_not_run(client):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready", schedule_kind="cron", cron="*/20 * * * *")
    assert task["next_run_at"] is not None

    copy = (await client.post(f"/api/tasks/{task['id']}/duplicate")).json()
    assert copy["status"] == "backlog"
    assert (copy["schedule_kind"], copy["cron"]) == ("cron", "*/20 * * * *")
    # parked like any task in the Backlog: it only runs once it is moved to Ready
    assert copy["next_run_at"] is None


async def test_a_copy_has_no_history_links_or_working_folder(client, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    workspace = (await client.get(f"/api/projects/{pid}/workspaces")).json()[0]
    other = (await client.post(f"/api/workspaces/{workspace['id']}/boards", json={"name": "QA"})).json()
    origin = await make_task(client, pid, title="Research")
    follow = (
        await client.post(
            f"/api/tasks/{origin['id']}/spawn", json={"board_id": other["id"], "title": "Build"}
        )
    ).json()
    assert follow["origin_task_id"] == origin["id"]
    async with maker() as s:
        row = await s.get(Task, follow["id"])
        row.run_options = {"workdir": 7}  # the folder a workflow handed this task
        row.hops = 3
        await s.commit()

    copy = (await client.post(f"/api/tasks/{follow['id']}/duplicate")).json()
    assert copy["origin_task_id"] is None  # a copy follows nothing
    assert copy["board_id"] == other["id"]  # it stays on the board of the task it copies
    async with maker() as s:
        row = await s.get(Task, copy["id"])
        assert row.run_options is None and row.hops == 0
    assert (await client.get(f"/api/tasks/{copy['id']}/attempts")).json() == []


async def test_a_copy_is_recorded_in_the_history_as_a_duplicate(client):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="Original")
    copy = (await client.post(f"/api/tasks/{task['id']}/duplicate")).json()

    events = (await client.get(f"/api/projects/{pid}/history", params={"task_id": copy["id"]})).json()
    assert [e["kind"] for e in events] == ["task_created"]
    assert events[0]["data"]["copy_of"] == "Original"


async def test_a_long_title_still_fits(client):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="x" * 200)
    copy = (await client.post(f"/api/tasks/{task['id']}/duplicate")).json()
    assert len(copy["title"]) == 200


async def test_a_workflow_step_cannot_be_duplicated(client, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid)
    async with maker() as s:
        (await s.get(Task, task["id"])).internal = True
        await s.commit()
    assert (await client.post(f"/api/tasks/{task['id']}/duplicate")).status_code == 422


async def test_a_task_that_does_not_exist_is_not_found(client):
    await register(client)
    assert (await client.post("/api/tasks/9999/duplicate")).status_code == 404
