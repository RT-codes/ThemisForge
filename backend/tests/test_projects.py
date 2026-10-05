from tests.conftest import make_project, make_task, register


async def test_projects_are_private_to_their_owner(client):
    await register(client, "a@b.co")
    project = await make_project(client)
    assert [p["name"] for p in (await client.get("/api/projects")).json()] == ["Alpha"]

    await register(client, "c@d.co", "Bob")
    assert (await client.get("/api/projects")).json() == []
    assert (await client.get(f"/api/projects/{project['id']}")).status_code == 404
    assert (await client.post(f"/api/projects/{project['id']}/tasks", json={"title": "x"})).status_code == 404


async def test_requires_login(client):
    assert (await client.get("/api/projects")).status_code == 401


async def test_project_summary_counts_tasks(client):
    await register(client)
    project = await make_project(client)
    await make_task(client, project["id"], status="ready", schedule_kind="cron", cron="0 9 * * *")
    await make_task(client, project["id"])
    summary = (await client.get("/api/projects")).json()[0]
    assert summary["task_counts"] == {"ready": 1, "inbox": 1}
    assert summary["next_run_at"] is not None


async def test_property_definitions_and_values(client):
    await register(client)
    project = await make_project(client)
    pid = project["id"]
    props = [
        {"key": "priority", "name": "Priority", "type": "select", "options": ["Low", "High"]},
        {"key": "cost", "name": "Cost", "type": "number"},
    ]
    assert (await client.patch(f"/api/projects/{pid}", json={"properties": props})).status_code == 200

    ok = await make_task(client, pid, properties={"priority": "High", "cost": 3, "unknown": "dropped"})
    assert ok["properties"] == {"priority": "High", "cost": 3}

    bad = await client.post(
        f"/api/projects/{pid}/tasks", json={"title": "t", "properties": {"priority": "Huge"}}
    )
    assert bad.status_code == 422 and "not an option" in bad.json()["detail"]

    dup = await client.patch(f"/api/projects/{pid}", json={"properties": props + [props[0]]})
    assert dup.status_code == 422
    empty_select = await client.patch(
        f"/api/projects/{pid}", json={"properties": [{"key": "k", "name": "K", "type": "select"}]}
    )
    assert empty_select.status_code == 422


async def test_task_crud_and_ordering(client):
    await register(client)
    pid = (await make_project(client))["id"]
    a = await make_task(client, pid, title="A")
    b = await make_task(client, pid, title="B")
    assert b["position"] > a["position"]

    moved = (await client.patch(f"/api/tasks/{a['id']}", json={"status": "review"})).json()
    assert moved["status"] == "review"
    renamed = (
        await client.patch(f"/api/tasks/{b['id']}", json={"title": "  B2  ", "description": "d"})
    ).json()
    assert renamed["title"] == "B2" and renamed["description"] == "d"

    titles = [t["title"] for t in (await client.get(f"/api/projects/{pid}/tasks")).json()]
    assert titles == ["A", "B2"]
    assert (await client.delete(f"/api/tasks/{a['id']}")).status_code == 204
    assert (await client.get(f"/api/tasks/{a['id']}")).status_code == 404


async def test_running_status_cannot_be_set_directly(client):
    await register(client)
    pid = (await make_project(client))["id"]
    r = await client.post(f"/api/projects/{pid}/tasks", json={"title": "t", "status": "running"})
    assert r.status_code == 422
    task = await make_task(client, pid)
    assert (await client.patch(f"/api/tasks/{task['id']}", json={"status": "running"})).status_code == 422


async def test_schedule_validation(client):
    await register(client)
    pid = (await make_project(client))["id"]
    for body in (
        {"schedule_kind": "cron"},
        {"schedule_kind": "cron", "cron": "not a cron"},
        {"schedule_kind": "cron", "cron": "* * * * * *"},
        {"schedule_kind": "once"},
        {"schedule_kind": "once", "run_at": "2030-01-01T10:00:00"},  # no timezone
    ):
        r = await client.post(f"/api/projects/{pid}/tasks", json={"title": "t", **body})
        assert r.status_code == 422, body


async def test_cron_next_run_uses_the_configured_timezone(client):
    await register(client)
    await client.put("/api/settings", json={"timezone": "Asia/Tokyo"})
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready", schedule_kind="cron", cron="0 9 * * *")
    from datetime import datetime

    nxt = datetime.fromisoformat(task["next_run_at"])
    assert nxt.hour == 0 and nxt.minute == 0  # 09:00 in Tokyo is 00:00 UTC


async def test_paused_cron_task_has_no_next_run_until_ready(client):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, schedule_kind="cron", cron="*/5 * * * *")
    assert task["status"] == "inbox" and task["next_run_at"] is None
    task = (await client.patch(f"/api/tasks/{task['id']}", json={"status": "ready"})).json()
    assert task["next_run_at"] is not None
    task = (await client.patch(f"/api/tasks/{task['id']}", json={"status": "inbox"})).json()
    assert task["next_run_at"] is None


async def test_upcoming_runs_expands_recurring_tasks(client):
    await register(client)
    pid = (await make_project(client))["id"]
    await make_task(client, pid, title="hourly", status="ready", schedule_kind="cron", cron="0 * * * *")
    await make_task(client, pid, title="paused", schedule_kind="cron", cron="0 * * * *")
    runs = (await client.get(f"/api/projects/{pid}/schedule?hours=6")).json()
    assert {r["title"] for r in runs} == {"hourly"}
    assert 5 <= len(runs) <= 6 and all(r["recurring"] for r in runs)
