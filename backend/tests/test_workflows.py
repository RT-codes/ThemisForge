import asyncio

import pytest
from sqlalchemy import select

from app.codex import save_auth
from app.main import app
from app.models import NodeStatus, RunStatus, WorkflowNodeRun, WorkflowRun, utcnow
from app.workflows import WorkflowRunner
from tests.conftest import login, make_project, make_task, register
from tests.test_harness import fake_auth


@pytest.fixture
async def runner(maker, scheduler):
    """The workflow engine, with a background pump standing in for the scheduler loop."""
    r = WorkflowRunner(maker, lambda: app.state.scheduler)
    r.POLL_SECONDS = 0.02
    app.state.workflows = r

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


async def run(client, pid: int, nodes: list[dict], edges: list[dict]) -> dict:
    assert (
        await client.put(f"/api/projects/{pid}/workflow", json={"nodes": nodes, "edges": edges})
    ).status_code == 200
    r = await client.post(f"/api/projects/{pid}/workflow/runs")
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    async with asyncio.timeout(10):
        while (detail := (await client.get(f"/api/workflow-runs/{run_id}")).json())[
            "status"
        ] == RunStatus.RUNNING:
            await asyncio.sleep(0.02)
    return detail


def by_id(detail: dict) -> dict[str, dict]:
    return {n["node_id"]: n for n in detail["nodes"]}


async def setup(client) -> tuple[dict, int]:
    me = await register(client)
    return me, (await make_project(client))["id"]


# ----- the saved graph -----


async def test_graph_round_trips_and_is_validated(client, runner):
    _, pid = await setup(client)
    assert (await client.get(f"/api/projects/{pid}/workflow")).json()["graph"] == {"nodes": [], "edges": []}
    nodes = [node("a", "start"), node("b", "end")]
    assert (
        await client.put(f"/api/projects/{pid}/workflow", json={"nodes": nodes, "edges": [edge("a", "b")]})
    ).status_code == 200
    saved = (await client.get(f"/api/projects/{pid}/workflow")).json()
    assert [n["id"] for n in saved["graph"]["nodes"]] == ["a", "b"] and saved["updated_at"]
    bad = await client.put(
        f"/api/projects/{pid}/workflow", json={"nodes": nodes, "edges": [edge("a", "ghost")]}
    )
    assert bad.status_code == 422
    dup = await client.put(
        f"/api/projects/{pid}/workflow", json={"nodes": [node("a", "start"), node("a", "end")], "edges": []}
    )
    assert dup.status_code == 422


async def test_only_the_owner_can_use_a_projects_workflow(client, runner):
    _, pid = await setup(client)
    detail = await run(client, pid, [node("s", "start")], [])
    await register(client, "other@b.co", "Other")
    assert (await client.get(f"/api/projects/{pid}/workflow")).status_code == 404
    assert (await client.post(f"/api/projects/{pid}/workflow/runs")).status_code == 404
    assert (await client.get(f"/api/workflow-runs/{detail['id']}")).status_code == 404
    await login(client, "a@b.co")
    assert (await client.get(f"/api/workflow-runs/{detail['id']}")).status_code == 200


async def test_a_run_needs_a_start_node(client, runner):
    _, pid = await setup(client)
    await client.put(
        f"/api/projects/{pid}/workflow", json={"nodes": [node("t", "task", title="x")], "edges": []}
    )
    r = await client.post(f"/api/projects/{pid}/workflow/runs")
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
        client, pid, [node("s", "start"), node("t", "task", title="Later", status="inbox")], [edge("s", "t")]
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
        [node("s", "start"), node("t", "task", title="loop", status="inbox")],
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
    await run(client, pid, [node("s", "start"), node("e", "end")], [edge("s", "e")])
    await run(
        client,
        pid,
        [node("s", "start"), node("t", "task", title="will fail", status="ready")],
        [edge("s", "t")],
    )
    runs = (await client.get(f"/api/projects/{pid}/workflow/runs")).json()
    assert [r["status"] for r in runs] == ["failed", "succeeded"]
    assert (runs[0]["nodes_total"], runs[0]["nodes_succeeded"], runs[0]["nodes_failed"]) == (2, 1, 1)


async def test_cancel_stops_the_run_and_its_cell(client, runner, cells, scheduler):
    _, pid = await setup(client)
    cells.duration = 30
    await client.put(
        f"/api/projects/{pid}/workflow",
        json={
            "nodes": [node("s", "start"), node("t", "task", title="slow", status="ready")],
            "edges": [edge("s", "t")],
        },
    )
    run_id = (await client.post(f"/api/projects/{pid}/workflow/runs")).json()["id"]
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
        wr = WorkflowRun(project_id=pid, graph={})
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
