import asyncio

import pytest
from sqlalchemy import select

from app.codex import save_auth
from app.main import app
from app.models import NodeStatus, RunStatus, Workflow, WorkflowNodeRun, WorkflowRun, utcnow
from app.workflows import WorkflowRunner
from tests.conftest import login, make_project, make_task, register
from tests.test_harness import fake_auth


@pytest.fixture
async def runner(maker, scheduler):
    """The workflow engine, with a background pump standing in for the scheduler loop."""
    r = WorkflowRunner(maker, lambda: app.state.scheduler)
    r.POLL_SECONDS = 0.02
    app.state.workflows = r
    scheduler.workflows = r

    async def pump():
        while True:
            await scheduler.tick()
            await asyncio.sleep(0.02)

    pumper = asyncio.create_task(pump())
    yield r
    pumper.cancel()
    await r.shutdown()
    await asyncio.gather(pumper, return_exceptions=True)


def node(id: str, kind: str, label: str = "", **config) -> dict:
    return {"id": id, "kind": kind, "label": label or id, "config": config, "position": {"x": 0, "y": 0}}


def edge(a: str, b: str, handle: str | None = None) -> dict:
    return {"id": f"{a}-{b}-{handle}", "source": a, "target": b, "sourceHandle": handle}


async def make_workflow(client, pid: int, name: str = "Flow") -> int:
    r = await client.post(f"/api/projects/{pid}/workflows", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def save(client, wid: int, nodes: list[dict], edges: list[dict]) -> None:
    r = await client.patch(f"/api/workflows/{wid}", json={"graph": {"nodes": nodes, "edges": edges}})
    assert r.status_code == 200, r.text


async def wait_for_run(client, run_id: int) -> dict:
    async with asyncio.timeout(10):
        while (detail := (await client.get(f"/api/workflow-runs/{run_id}")).json())[
            "status"
        ] == RunStatus.RUNNING:
            await asyncio.sleep(0.02)
    return detail


async def run(client, pid: int, nodes: list[dict], edges: list[dict], wid: int | None = None) -> dict:
    wid = wid or await make_workflow(client, pid)
    await save(client, wid, nodes, edges)
    r = await client.post(f"/api/workflows/{wid}/runs")
    assert r.status_code == 201, r.text
    return await wait_for_run(client, r.json()["id"])


def by_id(detail: dict) -> dict[str, dict]:
    return {n["node_id"]: n for n in detail["nodes"]}


async def setup(client) -> tuple[dict, int]:
    me = await register(client)
    return me, (await make_project(client))["id"]


# ----- the library -----


async def test_new_workflows_get_the_first_free_numbered_name(client, runner):
    _, pid = await setup(client)
    made = []
    for _ in range(3):
        r = await client.post(f"/api/projects/{pid}/workflows", json={})
        made.append((r.json()["id"], r.json()["name"]))
    assert [n for _, n in made] == ["Workflow 1", "Workflow 2", "Workflow 3"]
    await client.patch(f"/api/workflows/{made[0][0]}", json={"name": "Nightly"})
    assert (await client.post(f"/api/projects/{pid}/workflows", json={})).json()[
        "name"
    ] == "Workflow 1"  # the gap is reused
    await client.patch(
        f"/api/workflows/{made[1][0]}", json={"name": "WORKFLOW 4"}
    )  # a different case still counts
    assert (await client.post(f"/api/projects/{pid}/workflows", json={})).json()["name"] == "Workflow 2"
    assert (await client.post(f"/api/projects/{pid}/workflows", json={})).json()[
        "name"
    ] == "Workflow 5"  # 4 is taken
    other = (await make_project(client, "Other"))["id"]
    assert (await client.post(f"/api/projects/{other}/workflows", json={})).json()[
        "name"
    ] == "Workflow 1"  # per project
    named = await client.post(f"/api/projects/{pid}/workflows", json={"name": "  Mine "})
    assert named.json()["name"] == "Mine"


async def test_a_workflow_can_be_created_with_its_graph(client, runner):
    _, pid = await setup(client)
    graph = {"nodes": [node("a", "start"), node("b", "end")], "edges": [edge("a", "b")]}
    r = await client.post(f"/api/projects/{pid}/workflows", json={"graph": graph})
    assert r.status_code == 201 and [n["id"] for n in r.json()["graph"]["nodes"]] == ["a", "b"]
    bad = await client.post(
        f"/api/projects/{pid}/workflows", json={"graph": {"nodes": [], "edges": [edge("a", "b")]}}
    )
    assert bad.status_code == 422


async def test_a_new_workflow_starts_with_a_start_node(client, runner):
    _, pid = await setup(client)
    r = await client.post(
        f"/api/projects/{pid}/workflows", json={"name": "Nightly", "description": "Does things"}
    )
    wf = r.json()
    assert r.status_code == 201 and wf["name"] == "Nightly" and wf["project_id"] == pid
    assert [(n["id"], n["kind"]) for n in wf["graph"]["nodes"]] == [("n1", "start")]
    detail = await client.post(f"/api/workflows/{wf['id']}/runs")
    assert detail.status_code == 201  # it can be tested straight away


async def test_a_project_has_a_library_of_workflows(client, runner):
    _, pid = await setup(client)
    a = await make_workflow(client, pid, "Alpha")
    b = await make_workflow(client, pid, "Beta")
    await run(client, pid, [node("s", "start"), node("e", "end")], [edge("s", "e")], wid=a)
    listing = (await client.get(f"/api/projects/{pid}/workflows")).json()
    assert [(w["name"], w["node_count"], w["runs"]) for w in listing] == [("Alpha", 2, 1), ("Beta", 1, 0)]
    assert listing[0]["last_run"]["status"] == "succeeded" and listing[1]["last_run"] is None
    assert {w["id"] for w in listing} == {a, b}


async def test_graph_round_trips_and_is_validated(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    nodes = [node("a", "start"), node("b", "end")]
    r = await client.patch(
        f"/api/workflows/{wid}", json={"graph": {"nodes": nodes, "edges": [edge("a", "b")]}}
    )
    assert r.status_code == 200
    saved = (await client.get(f"/api/workflows/{wid}")).json()
    assert [n["id"] for n in saved["graph"]["nodes"]] == ["a", "b"] and saved["updated_at"]
    ghost = {"graph": {"nodes": nodes, "edges": [edge("a", "ghost")]}}
    assert (await client.patch(f"/api/workflows/{wid}", json=ghost)).status_code == 422
    dup = {"graph": {"nodes": [node("a", "start"), node("a", "end")], "edges": []}}
    assert (await client.patch(f"/api/workflows/{wid}", json=dup)).status_code == 422


async def test_rename_and_describe(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    r = await client.patch(f"/api/workflows/{wid}", json={"name": "  Renamed ", "description": "Why"})
    assert (r.json()["name"], r.json()["description"]) == ("Renamed", "Why")
    assert (await client.patch(f"/api/workflows/{wid}", json={"name": "   "})).status_code == 422
    assert (await client.patch(f"/api/workflows/{wid}", json={"name": ""})).status_code == 422


async def test_delete_removes_the_workflow_and_its_runs(client, runner, maker):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    detail = await run(client, pid, [node("s", "start")], [], wid=wid)
    assert (await client.delete(f"/api/workflows/{wid}")).status_code == 204
    assert (await client.get(f"/api/workflows/{wid}")).status_code == 404
    assert (await client.get(f"/api/workflow-runs/{detail['id']}")).status_code == 404
    assert (await client.get(f"/api/projects/{pid}/workflows")).json() == []


async def test_a_running_workflow_cannot_be_deleted(client, runner, cells, scheduler):
    _, pid = await setup(client)
    cells.duration = 30
    wid = await make_workflow(client, pid)
    await save(
        client, wid, [node("s", "start"), node("t", "task", title="slow", status="ready")], [edge("s", "t")]
    )
    run_id = (await client.post(f"/api/workflows/{wid}/runs")).json()["id"]
    assert (await client.delete(f"/api/workflows/{wid}")).status_code == 409
    await client.post(f"/api/workflow-runs/{run_id}/cancel")
    assert (await client.delete(f"/api/workflows/{wid}")).status_code == 204


async def test_only_the_owner_can_use_a_projects_workflows(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    detail = await run(client, pid, [node("s", "start")], [], wid=wid)
    await register(client, "other@b.co", "Other")
    for r in (
        await client.get(f"/api/projects/{pid}/workflows"),
        await client.post(f"/api/projects/{pid}/workflows", json={}),
        await client.get(f"/api/workflows/{wid}"),
        await client.patch(f"/api/workflows/{wid}", json={"name": "x"}),
        await client.delete(f"/api/workflows/{wid}"),
        await client.post(f"/api/workflows/{wid}/runs"),
        await client.get(f"/api/workflows/{wid}/runs"),
        await client.get(f"/api/workflow-runs/{detail['id']}"),
    ):
        assert r.status_code == 404
    await login(client, "a@b.co")
    assert (await client.get(f"/api/workflow-runs/{detail['id']}")).status_code == 200


async def test_a_run_needs_a_start_node(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    await save(client, wid, [node("t", "task", title="x")], [])
    r = await client.post(f"/api/workflows/{wid}/runs")
    assert r.status_code == 422 and "Start node" in r.json()["detail"]


# ----- running -----


async def test_linear_run_records_every_node_in_order(client, runner, cells):
    _, pid = await setup(client)
    detail = await run(
        client, pid,
        [node("s", "start", "Begin"), node("t", "task", "Write report", action="create", title="Report", status="ready"), node("e", "end", note="All good")],
        [edge("s", "t"), edge("t", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded" and detail["outcome"] == "All good"
    assert [(n["seq"], n["node_id"], n["status"]) for n in detail["nodes"]] == [
        (1, "s", "succeeded"),
        (2, "t", "succeeded"),
        (3, "e", "succeeded"),
    ]
    task_node = by_id(detail)["t"]
    assert "[fake cell]" in task_node["log"] and "finished" in task_node["result"]
    assert task_node["task_id"] and task_node["attempt_id"]
    tasks = (await client.get(f"/api/projects/{pid}/tasks")).json()
    assert [(t["title"], t["status"]) for t in tasks] == [("Report", "done")]


async def test_a_task_that_is_not_ready_is_only_created(client, runner, cells):
    _, pid = await setup(client)
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("t", "task", title="Later", status="backlog")],
        [edge("s", "t")],
    )
    assert detail["status"] == "succeeded" and not cells.specs
    assert "Created task" in by_id(detail)["t"]["log"]


async def test_a_failing_task_stops_its_branch_and_says_why(client, runner):
    _, pid = await setup(client)
    detail = await run(
        client, pid,
        [node("s", "start"), node("t", "task", title="will fail", status="ready"), node("e", "end")],
        [edge("s", "t"), edge("t", "e")],
    )  # fmt: skip
    nodes = by_id(detail)
    assert detail["status"] == "failed" and "failed" in detail["outcome"]
    assert nodes["t"]["status"] == "failed" and "The task failed" in nodes["t"]["error"] and nodes["t"]["log"]
    assert nodes["e"]["status"] == "skipped" and "'t' failed before this node" in nodes["e"]["error"]
    assert [n["node_id"] for n in detail["nodes"]] == ["s", "t", "e"]  # ran first, never-run last


async def test_condition_follows_the_matching_branch(client, runner):
    _, pid = await setup(client)
    detail = await run(
        client, pid,
        [node("s", "start"), node("t", "task", title="ok job", status="ready"),
         node("c", "condition", source="result", operator="contains", value="finished"),
         node("yes", "end", note="took yes"), node("no", "end", outcome="failed", note="took no")],
        [edge("s", "t"), edge("t", "c"), edge("c", "yes", "yes"), edge("c", "no", "no")],
    )  # fmt: skip
    nodes = by_id(detail)
    assert detail["status"] == "succeeded" and detail["outcome"] == "took yes"
    assert nodes["c"]["result"] == "yes" and "-> yes" in nodes["c"]["log"]
    assert nodes["no"]["status"] == "skipped" and "answered yes" in nodes["no"]["error"]


async def test_condition_no_branch_and_end_as_failed(client, runner):
    _, pid = await setup(client)
    detail = await run(
        client, pid,
        [node("s", "start"), node("t", "task", title="ok job", status="ready"),
         node("c", "condition", source="status", operator="equals", value="failed"),
         node("yes", "end"), node("no", "end", outcome="failed", note="not failed, but we call it so")],
        [edge("s", "t"), edge("t", "c"), edge("c", "yes", "yes"), edge("c", "no", "no")],
    )  # fmt: skip
    assert by_id(detail)["no"]["status"] == "succeeded" and by_id(detail)["yes"]["status"] == "skipped"
    assert detail["status"] == "failed" and detail["outcome"] == "not failed, but we call it so"


async def test_a_condition_nothing_leads_to_is_not_run(client, runner):
    _, pid = await setup(client)
    detail = await run(client, pid, [node("c", "condition"), node("s", "start")], [])
    assert by_id(detail)["c"]["status"] == "skipped" and detail["status"] == "succeeded"


async def test_a_trigger_node_also_starts_a_run(client, runner):
    _, pid = await setup(client)
    detail = await run(client, pid, [node("c", "trigger")], [])
    assert detail["status"] == "succeeded" and by_id(detail)["c"]["status"] == "succeeded"


async def test_agent_without_a_codex_login_fails_with_the_reason(client, runner):
    _, pid = await setup(client)
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("a", "agent", "Researcher", harness="codex", instructions="Look into it")],
        [edge("s", "a")],
    )
    agent = by_id(detail)["a"]
    assert detail["status"] == "failed" and agent["status"] == "failed"
    assert "Connect it in Settings" in agent["log"] and "The task failed" in agent["error"]


async def test_agent_runs_with_the_owners_login_and_gets_the_previous_result(client, runner, cells, maker):
    me, pid = await setup(client)
    async with maker() as s:
        await save_auth(s, me["id"], fake_auth(), fresh=True)
    detail = await run(
        client, pid,
        [node("s", "start"), node("t", "task", title="Gather", status="ready"), node("a", "agent", "Writer", harness="codex", instructions="Summarise it"), node("e", "end")],
        [edge("s", "t"), edge("t", "a"), edge("a", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded"
    spec = next(s for s in cells.specs if s.harness == "codex")
    assert "Summarise it" in spec.prompt and "Result of the previous step (t)" in spec.prompt
    tasks = {t["title"]: t for t in (await client.get(f"/api/projects/{pid}/tasks")).json()}
    assert tasks["Writer"]["harness"] == "codex" and tasks["Writer"]["status"] == "done"


async def test_agent_can_be_told_to_carry_on_after_failing(client, runner):
    _, pid = await setup(client)
    detail = await run(
        client, pid,
        [node("s", "start"), node("a", "agent", harness="codex", instructions="x", onFailure="continue"), node("e", "end", note="went on")],
        [edge("s", "a"), edge("a", "e")],
    )  # fmt: skip
    nodes = by_id(detail)
    assert nodes["a"]["status"] == "failed" and nodes["e"]["status"] == "succeeded"
    assert detail["status"] == "succeeded" and detail["outcome"] == "went on"


async def test_agent_without_instructions_fails_before_running_anything(client, runner, cells):
    _, pid = await setup(client)
    detail = await run(
        client, pid, [node("s", "start"), node("a", "agent", harness="codex")], [edge("s", "a")]
    )
    assert "no instructions" in by_id(detail)["a"]["error"] and not cells.specs


async def test_run_and_update_existing_tasks(client, runner, cells):
    _, pid = await setup(client)
    await make_task(client, pid, title="Existing")
    detail = await run(
        client, pid,
        [node("s", "start"), node("r", "task", action="run", title="Existing"), node("u", "task", action="update", title="Existing", status="review"), node("m", "task", action="run", title="Missing")],
        [edge("s", "r"), edge("r", "u"), edge("u", "m")],
    )  # fmt: skip
    nodes = by_id(detail)
    assert nodes["r"]["status"] == "succeeded" and nodes["u"]["status"] == "succeeded"
    assert nodes["m"]["status"] == "failed" and 'no task titled "Missing"' in nodes["m"]["error"]
    assert (await client.get(f"/api/projects/{pid}/tasks")).json()[0]["status"] == "review"


async def test_several_start_nodes_all_begin_and_a_shared_node_runs_once(client, runner):
    _, pid = await setup(client)
    detail = await run(
        client, pid,
        [node("s1", "start"), node("s2", "start"), node("e", "end")],
        [edge("s1", "e"), edge("s2", "e")],
    )  # fmt: skip
    assert [n["node_id"] for n in detail["nodes"]] == ["s1", "s2", "e"] and detail["status"] == "succeeded"


async def test_a_loop_does_not_run_forever(client, runner):
    _, pid = await setup(client)
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("t", "task", title="loop", status="backlog")],
        [edge("s", "t"), edge("t", "s"), edge("t", "t")],
    )
    assert detail["status"] == "succeeded" and len(detail["nodes"]) == 2


async def test_unconnected_nodes_are_recorded_as_not_run(client, runner):
    _, pid = await setup(client)
    detail = await run(client, pid, [node("s", "start"), node("lonely", "end")], [])
    assert (
        by_id(detail)["lonely"]["status"] == "skipped" and "nothing leads" in by_id(detail)["lonely"]["error"]
    )


# ----- history, cancelling, restarts -----


async def test_history_lists_runs_newest_first_with_counts(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    await run(client, pid, [node("s", "start"), node("e", "end")], [edge("s", "e")], wid=wid)
    await run(
        client, pid,
        [node("s", "start"), node("t", "task", title="will fail", status="ready")],
        [edge("s", "t")],
        wid=wid,
    )  # fmt: skip
    runs = (await client.get(f"/api/workflows/{wid}/runs")).json()
    assert [r["status"] for r in runs] == ["failed", "succeeded"]
    assert (runs[0]["nodes_total"], runs[0]["nodes_succeeded"], runs[0]["nodes_failed"]) == (2, 1, 1)
    other = await make_workflow(client, pid, "Other")
    assert (
        await client.get(f"/api/workflows/{other}/runs")
    ).json() == []  # a run belongs to its own workflow


async def test_cancel_stops_the_run_and_its_cell(client, runner, cells, scheduler):
    _, pid = await setup(client)
    cells.duration = 30
    wid = await make_workflow(client, pid)
    await save(
        client, wid, [node("s", "start"), node("t", "task", title="slow", status="ready")], [edge("s", "t")]
    )
    run_id = (await client.post(f"/api/workflows/{wid}/runs")).json()["id"]
    async with asyncio.timeout(10):
        while not scheduler._live:
            await asyncio.sleep(0.02)
    r = await client.post(f"/api/workflow-runs/{run_id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert by_id(r.json())["t"]["status"] == "cancelled"
    assert (await client.post(f"/api/workflow-runs/{run_id}/cancel")).status_code == 409
    assert not scheduler._live


async def test_a_restart_closes_dangling_runs(client, runner, maker):
    _, pid = await setup(client)
    async with maker() as s:
        wf = Workflow(project_id=pid)
        s.add(wf)
        await s.flush()
        wr = WorkflowRun(project_id=pid, workflow_id=wf.id, graph={})
        s.add(wr)
        await s.flush()
        s.add(WorkflowNodeRun(run_id=wr.id, node_id="x", kind="task", label="x", seq=1, started_at=utcnow()))
        await s.commit()
    await runner.reconcile()
    async with maker() as s:
        wr = (await s.scalars(select(WorkflowRun))).one()
        nr = (await s.scalars(select(WorkflowNodeRun))).one()
    assert wr.status == RunStatus.FAILED and "restarted" in wr.outcome
    assert nr.status == NodeStatus.FAILED and "restarted" in nr.error


# ----- tasks that play a workflow -----


async def play_task(client, pid: int, wid: int | None, title: str = "Player", **extra) -> dict:
    r = await client.post(
        f"/api/projects/{pid}/tasks",
        json={"title": title, "harness": "workflow", "workflow_id": wid, "status": "ready", **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def attempt_of(client, task_id: int) -> dict:
    async with asyncio.timeout(10):
        while (
            not (attempts := (await client.get(f"/api/tasks/{task_id}/attempts")).json())
            or attempts[0]["status"] == "running"
        ):
            await asyncio.sleep(0.02)
    return (await client.get(f"/api/attempts/{attempts[0]['id']}")).json()


async def test_a_task_validates_the_workflow_it_plays(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    other = (await make_project(client, "Other"))["id"]
    foreign = await make_workflow(client, other)
    for wf in (None, foreign, 9999):
        r = await client.post(
            f"/api/projects/{pid}/tasks", json={"title": "x", "harness": "workflow", "workflow_id": wf}
        )
        assert r.status_code == 422, wf
    task = await play_task(
        client, pid, wid, status="backlog"
    )  # not ready, so nothing starts it while we edit
    assert task["harness"] == "workflow" and task["workflow_id"] == wid
    back = await client.patch(f"/api/tasks/{task['id']}", json={"harness": ""})
    assert back.json()["harness"] == "" and back.json()["workflow_id"] is None  # not playing one any more
    again = await client.patch(f"/api/tasks/{task['id']}", json={"harness": "workflow", "workflow_id": wid})
    assert again.json()["workflow_id"] == wid
    assert (await client.patch(f"/api/tasks/{task['id']}", json={"workflow_id": foreign})).status_code == 422


async def test_a_task_plays_its_workflow_and_reports_the_run(client, runner, cells):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid, "Flow")
    await save(
        client, wid,
        [node("s", "start"), node("t", "task", "Step", title="Inner", status="ready"), node("e", "end", note="All done")],
        [edge("s", "t"), edge("t", "e")],
    )  # fmt: skip
    task = await play_task(client, pid, wid)
    attempt = await attempt_of(client, task["id"])
    assert attempt["status"] == "succeeded" and attempt["result"] == "All done"
    assert (
        'Playing the workflow "Flow"' in attempt["log"]
        and "[2] Step (task)" in attempt["log"]
        and "Workflow succeeded: All done" in attempt["log"]
    )
    run = (await client.get(f"/api/workflow-runs/{attempt['workflow_run_id']}")).json()
    assert run["status"] == "succeeded" and run["trigger"] == "task" and run["workflow_id"] == wid
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "done"
    assert [s.title for s in cells.specs] == ["Inner"]  # the playing task itself ran no cell


async def test_a_failing_workflow_fails_the_task_that_plays_it(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    await save(
        client,
        wid,
        [node("s", "start"), node("t", "task", title="will fail", status="ready")],
        [edge("s", "t")],
    )
    task = await play_task(client, pid, wid)
    attempt = await attempt_of(client, task["id"])
    assert attempt["status"] == "failed" and "failed" in attempt["log"]
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "failed"


async def test_playing_a_workflow_never_starves_the_cells_it_needs(client, runner, cells):
    """With a single cell slot, the task that plays a workflow must not hold it while waiting for the inner task."""
    _, pid = await setup(client)
    settings = (await client.get("/api/settings")).json()
    await client.put("/api/settings", json={**settings, "budget": {"cpus": 1, "memory_mb": 1024}})
    wid = await make_workflow(client, pid)
    await save(
        client, wid, [node("s", "start"), node("t", "task", title="Inner", status="ready")], [edge("s", "t")]
    )
    first, second = await play_task(client, pid, wid, "P1"), await play_task(client, pid, wid, "P2")
    assert (await attempt_of(client, first["id"]))["status"] == "succeeded"
    assert (await attempt_of(client, second["id"]))["status"] == "succeeded"


async def test_a_workflow_that_plays_itself_through_a_task_is_stopped(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    player = await play_task(client, pid, wid, "Player", status="backlog")
    await save(
        client, wid, [node("s", "start"), node("t", "task", action="run", title="Player")], [edge("s", "t")]
    )
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("t", "task", action="run", title="Player")],
        [edge("s", "t")],
        wid=wid,
    )
    assert detail["status"] == "failed"
    attempt = await attempt_of(client, player["id"])
    assert attempt["status"] == "failed" and "would loop" in attempt["log"]


async def test_a_task_whose_workflow_was_deleted_fails_clearly(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    task = await play_task(client, pid, wid, status="backlog")
    await client.delete(f"/api/workflows/{wid}")
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["workflow_id"] is None
    await client.post(f"/api/tasks/{task['id']}/run")
    attempt = await attempt_of(client, task["id"])
    assert attempt["status"] == "failed" and "no longer exists" in attempt["log"]


# ----- triggers: a task moves into a status -----


async def save_auth_for_agent(maker) -> None:
    async with maker() as s:
        await save_auth(s, 1, fake_auth(), fresh=True)


def status_trigger(status: str) -> dict:
    return node("t", "trigger", type="task_status", status=status)


async def runs_of(client, wid: int) -> list[dict]:
    return (await client.get(f"/api/workflows/{wid}/runs")).json()


async def wait_for_runs(client, wid: int, count: int) -> list[dict]:
    async with asyncio.timeout(10):
        while len(runs := await runs_of(client, wid)) < count:
            await asyncio.sleep(0.02)
    return runs


async def test_a_task_moving_into_the_status_starts_the_workflow_and_it_can_move_that_task(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    await save(
        client,
        wid,
        [status_trigger("review"), node("m", "task", action="move_trigger", status="done")],
        [edge("t", "m")],
    )
    task = await make_task(client, pid, title="Ship it", status="backlog")
    other = await make_task(client, pid, title="Elsewhere", status="backlog")
    assert await runs_of(client, wid) == []  # creating them in Backlog is not a move into Review

    await client.patch(f"/api/tasks/{task['id']}", json={"status": "review"})
    (started,) = await wait_for_runs(client, wid, 1)
    detail = await wait_for_run(client, started["id"])
    assert detail["trigger"] == "status" and detail["status"] == RunStatus.SUCCEEDED
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "done"
    assert (await client.get(f"/api/tasks/{other['id']}")).json()["status"] == "backlog"


async def test_a_task_created_in_the_status_also_starts_the_workflow(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    await save(client, wid, [status_trigger("review"), node("e", "end")], [edge("t", "e")])
    await make_task(client, pid, status="review")
    assert len(await wait_for_runs(client, wid, 1)) == 1


async def test_moving_the_task_back_into_its_own_trigger_status_does_not_run_away(client, runner):
    """A workflow that puts the task back into the status that starts it: one run, not an endless chain."""
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    await save(
        client,
        wid,
        [status_trigger("review"), node("m", "task", action="move_trigger", status="review")],
        [edge("t", "m")],
    )
    await client.put("/api/settings", json={"start_cooldown_seconds": 60})
    task = await make_task(client, pid, status="backlog")
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "review"})
    await wait_for_runs(client, wid, 1)
    await asyncio.sleep(0.3)
    assert len(await runs_of(client, wid)) == 1


async def test_the_task_of_an_agent_node_does_not_start_workflows(client, runner, maker):
    _, pid = await setup(client)
    await save_auth_for_agent(maker)
    watcher = await make_workflow(client, pid, "Watcher")
    await save(client, watcher, [status_trigger("ready"), node("e", "end")], [edge("t", "e")])
    detail = await run(
        client, pid, [node("s", "start"), node("a", "agent", instructions="Say hi")], [edge("s", "a")]
    )
    assert detail["status"] == RunStatus.SUCCEEDED
    await asyncio.sleep(0.2)
    assert await runs_of(client, watcher) == []


async def test_moving_the_task_that_started_the_run_needs_a_status_trigger(client, runner):
    _, pid = await setup(client)
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("m", "task", action="move_trigger", status="done")],
        [edge("s", "m")],
    )
    assert detail["status"] == RunStatus.FAILED
    assert "No task started this run" in by_id(detail)["m"]["error"]


# ----- seeing the automation from the board -----


async def test_the_board_can_see_what_watches_a_status_and_which_run_a_task_started(client, runner, maker):
    _, pid = await setup(client)
    await save_auth_for_agent(maker)
    wid = await make_workflow(client, pid)
    await save(
        client,
        wid,
        [
            status_trigger("review"),
            node("a", "agent", instructions="Say hi"),
            node("m", "task", action="move_trigger", status="done"),
        ],
        [edge("t", "a"), edge("a", "m")],
    )
    manual = await make_workflow(client, pid, "By hand")
    summaries = {w["id"]: w for w in (await client.get(f"/api/projects/{pid}/workflows")).json()}
    assert summaries[wid]["watches"] == ["review"] and summaries[manual]["watches"] == []

    task = await make_task(client, pid, title="Ticket", status="backlog")
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "review"})
    (started,) = await wait_for_runs(client, wid, 1)
    await wait_for_run(client, started["id"])

    history = (await client.get(f"/api/tasks/{task['id']}/workflow-runs")).json()
    assert [(h["id"], h["workflow_name"], h["status"]) for h in history] == [
        (started["id"], "Flow", RunStatus.SUCCEEDED)
    ]
    assert (await client.get(f"/api/tasks/{task['id']}")).json()[
        "workflow_run"
    ] is None  # nothing going any more


async def test_a_task_shows_the_run_it_started_while_it_is_going(client, runner, maker):
    _, pid = await setup(client)
    await save_auth_for_agent(maker)
    wid = await make_workflow(client, pid)
    await save(
        client,
        wid,
        [status_trigger("review"), node("a", "agent", "Thinker", instructions="Say hi")],
        [edge("t", "a")],
    )
    task = await make_task(client, pid, status="review")
    async with asyncio.timeout(10):
        while not (current := (await client.get(f"/api/tasks/{task['id']}")).json()["workflow_run"]):
            await asyncio.sleep(0.01)
    assert current["workflow_id"] == wid and current["workflow_name"] == "Flow"
