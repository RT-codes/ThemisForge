"""Approval gates: a workflow step that parks the run until a person approves or rejects, and keeps it parked across a
restart. The walker's own state is memory-only, so the restart tests are the ones that matter most here."""

import asyncio

from sqlalchemy import select

from app.features.workflows.runner import WorkflowRunner
from app.main import app
from app.persistence.models import NodeStatus, RunStatus, Workflow, WorkflowNodeRun, WorkflowRun, utcnow
from tests.conftest import login, register
from tests.test_workflow_branches import branches, task
from tests.test_workflows import by_id, edge, make_workflow, node, save, setup, wait_for_run


def gated(prompt: str = "Publish this listing?") -> tuple[list[dict], list[dict]]:
    """start -> a Condition (it answers "yes", so there is a result to approve) -> the gate -> end"""
    return (
        [
            node("s", "start"),
            node("c", "condition", "Draft", source="result", operator="empty"),
            node("g", "approval", "Approve listing", prompt=prompt),
            node("e", "end"),
        ],
        [edge("s", "c"), edge("c", "g"), edge("g", "e")],
    )


async def start(client, pid: int, nodes: list[dict], edges: list[dict]) -> int:
    wid = await make_workflow(client, pid)
    await save(client, wid, nodes, edges)
    r = await client.post(f"/api/workflows/{wid}/runs")
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def open_approvals(client, count: int = 1) -> list[dict]:
    async with asyncio.timeout(10):
        while len(found := (await client.get("/api/approvals")).json()) < count:
            await asyncio.sleep(0.02)
    return found


async def answer(client, approval_id: int, approved: bool, note: str = ""):
    return await client.post(
        f"/api/approvals/{approval_id}/decision", json={"approved": approved, "note": note}
    )


async def restart(maker, runner, scheduler) -> WorkflowRunner:
    """What a restart does to the engine: the old one stops (its gates stay parked), a new one reconciles and resumes."""
    runner._stopping = True  # as in shutdown(), which the fixture still calls to remove the listeners
    live = list(runner._live.values())
    for run_task in live:
        run_task.cancel()
    await asyncio.gather(*live, return_exceptions=True)
    fresh = WorkflowRunner(maker, lambda: app.state.scheduler)
    fresh.POLL_SECONDS = 0.02
    app.state.workflows = fresh
    scheduler.workflows = fresh
    await fresh.reconcile()
    await fresh.resume_parked()
    return fresh


async def test_a_gate_parks_the_run_until_it_is_approved(client, runner):
    _, pid = await setup(client)
    run_id = await start(client, pid, *gated())
    [approval] = await open_approvals(client)
    assert approval["run_id"] == run_id and approval["label"] == "Approve listing"
    assert approval["prompt"] == "Publish this listing?"
    assert approval["previous_label"] == "Draft" and approval["previous"] == "yes"  # what there is to approve
    assert approval["project_id"] == pid and approval["workflow_name"] == "Flow"
    parked = (await client.get(f"/api/workflow-runs/{run_id}")).json()
    assert parked["status"] == "running" and by_id(parked)["g"]["status"] == "waiting"

    assert (await answer(client, approval["id"], True, "looks good")).status_code == 204
    detail = await wait_for_run(client, run_id)
    n = by_id(detail)
    assert detail["status"] == "succeeded" and n["e"]["status"] == "succeeded"
    assert (
        n["g"]["status"] == "succeeded" and n["g"]["result"] == "yes"
    )  # the previous result passes on unchanged
    assert "Approved by Ada: looks good" in n["g"]["log"]
    assert (n["g"]["decision"], n["g"]["decided_by"]) == ("approved", "Ada")
    assert (await client.get("/api/approvals")).json() == []


async def test_rejecting_fails_the_node_with_the_note_and_the_run_with_it(client, runner):
    _, pid = await setup(client)
    run_id = await start(client, pid, *gated())
    [approval] = await open_approvals(client)
    assert (await answer(client, approval["id"], False, "wrong photo")).status_code == 204
    detail = await wait_for_run(client, run_id)
    n = by_id(detail)
    assert detail["status"] == "failed" and "Rejected by Ada: wrong photo" in detail["outcome"]
    assert n["g"]["status"] == "failed" and n["g"]["error"] == "Rejected by Ada: wrong photo"
    assert n["e"]["status"] == "skipped" and "failed before this node" in n["e"]["error"]


async def test_the_first_answer_stands(client, runner):
    _, pid = await setup(client)
    run_id = await start(client, pid, *gated())
    [approval] = await open_approvals(client)
    assert (await answer(client, approval["id"], True)).status_code == 204
    assert (await answer(client, approval["id"], False)).status_code == 409
    assert (await wait_for_run(client, run_id))["status"] == "succeeded"
    assert (await answer(client, approval["id"], True)).status_code == 409  # the run is over


async def test_only_the_owner_sees_and_answers_an_approval(client, runner):
    _, pid = await setup(client)
    await start(client, pid, *gated())
    [approval] = await open_approvals(client)
    await register(client, "other@b.co", "Other")
    assert (await client.get("/api/approvals")).json() == []
    assert (await answer(client, approval["id"], True)).status_code == 404
    await login(client, "a@b.co")
    assert len((await client.get("/api/approvals")).json()) == 1  # still open: the stranger changed nothing


async def test_a_decision_needs_an_approval_gate(client, runner):
    _, pid = await setup(client)
    run_id = await start(
        client, pid, [node("s", "start"), node("c", "condition", operator="empty")], [edge("s", "c")]
    )
    detail = await wait_for_run(client, run_id)
    assert (await answer(client, by_id(detail)["c"]["id"], True)).status_code == 404
    assert (await answer(client, 9999, True)).status_code == 404


async def test_cancelling_a_run_closes_its_open_gate(client, runner):
    _, pid = await setup(client)
    run_id = await start(client, pid, *gated())
    await open_approvals(client)
    r = await client.post(f"/api/workflow-runs/{run_id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert by_id(r.json())["g"]["status"] == "cancelled"
    assert (await client.get("/api/approvals")).json() == []


async def test_a_run_parked_at_a_gate_survives_a_restart(client, runner, maker, scheduler):
    _, pid = await setup(client)
    run_id = await start(client, pid, *gated())
    [approval] = await open_approvals(client)
    fresh = await restart(maker, runner, scheduler)
    try:
        parked = (await client.get(f"/api/workflow-runs/{run_id}")).json()
        assert parked["status"] == "running" and by_id(parked)["g"]["status"] == "waiting"
        [again] = (await client.get("/api/approvals")).json()
        assert (
            again["id"] == approval["id"]
            and again["previous"] == "yes"
            and again["prompt"] == approval["prompt"]
        )

        assert (await answer(client, approval["id"], True, "after the restart")).status_code == 204
        detail = await wait_for_run(client, run_id)
        n = by_id(detail)
        assert detail["status"] == "succeeded" and n["e"]["status"] == "succeeded"
        assert n["g"]["result"] == "yes" and "after the restart" in n["g"]["log"]
        # nothing ran twice and nothing was recorded as not run: one record per node, in the order they happened
        assert [(x["node_id"], x["status"]) for x in detail["nodes"]] == [
            ("s", "succeeded"), ("c", "succeeded"), ("g", "succeeded"), ("e", "succeeded"),
        ]  # fmt: skip
    finally:
        await fresh.shutdown()


async def test_an_answer_given_while_the_server_was_down_is_taken_up_on_resume(
    client, runner, maker, scheduler
):
    _, pid = await setup(client)
    run_id = await start(client, pid, *gated())
    [approval] = await open_approvals(client)
    runner._stopping = True
    for run_task in list(runner._live.values()):
        run_task.cancel()
    await asyncio.sleep(0.05)
    assert await runner.decide(
        approval["id"], False, "no thanks", "Ada"
    )  # the answer is stored, nobody is listening
    fresh = WorkflowRunner(maker, lambda: app.state.scheduler)
    fresh.POLL_SECONDS = 0.02
    app.state.workflows = fresh
    await fresh.reconcile()
    await fresh.resume_parked()
    try:
        detail = await wait_for_run(client, run_id)
        assert detail["status"] == "failed" and "Rejected by Ada: no thanks" in detail["outcome"]
    finally:
        await fresh.shutdown()


async def test_a_merger_below_a_resumed_gate_does_not_wait_for_branches_that_are_gone(
    client, runner, maker, scheduler
):
    _, pid = await setup(client)
    nodes, edges = branches(
        node("g", "approval", "Approve", prompt="Ship it?"), node("c", "condition", "Check", operator="empty")
    )
    run_id = await start(client, pid, nodes, edges)
    [approval] = await open_approvals(client)
    async with asyncio.timeout(10):  # the other branch is done; the merger waits for the gate
        while (
            by_id((await client.get(f"/api/workflow-runs/{run_id}")).json()).get("c", {}).get("status")
            != "succeeded"
        ):
            await asyncio.sleep(0.02)
    fresh = await restart(maker, runner, scheduler)
    try:
        assert (await answer(client, approval["id"], True)).status_code == 204
        detail = await wait_for_run(client, run_id)
        n = by_id(detail)
        assert detail["status"] == "succeeded", detail["outcome"]
        assert n["m"]["status"] == "succeeded" and n["e"]["status"] == "succeeded"
        assert sum(x["node_id"] == "c" for x in detail["nodes"]) == 1  # the finished branch was not run again
    finally:
        await fresh.shutdown()


async def test_a_node_caught_running_by_the_restart_still_fails_the_run(
    client, runner, maker, scheduler, cells
):
    _, pid = await setup(client)
    cells.duration = 30  # the other branch is still in its cell when Themis stops
    nodes, edges = branches(node("g", "approval", "Approve"), task("t", "Slow"))
    run_id = await start(client, pid, nodes, edges)
    [approval] = await open_approvals(client)
    async with asyncio.timeout(10):
        while not scheduler.runs.live:
            await asyncio.sleep(0.02)
    fresh = await restart(maker, runner, scheduler)
    try:
        assert (await answer(client, approval["id"], True)).status_code == 204
        detail = await wait_for_run(client, run_id)
        assert detail["status"] == "failed" and "restarted" in detail["outcome"]
        assert by_id(detail)["t"]["status"] == "failed"
    finally:
        await fresh.shutdown()


async def test_a_gate_in_a_run_that_a_task_plays_does_not_survive_a_restart(client, runner, maker):
    """That run dies with the attempt of its task, which the scheduler closes on its own restart."""
    _, pid = await setup(client)
    async with maker() as s:
        wf = Workflow(project_id=pid)
        s.add(wf)
        await s.flush()
        wr = WorkflowRun(project_id=pid, workflow_id=wf.id, graph={}, trigger="task")
        s.add(wr)
        await s.flush()
        s.add(
            WorkflowNodeRun(
                run_id=wr.id, node_id="g", kind="approval", label="g", seq=1, started_at=utcnow(),
                status=NodeStatus.WAITING, gate={"prompt": "", "previous": None},
            )
        )  # fmt: skip
        await s.commit()
    await runner.reconcile()
    async with maker() as s:
        wr = (await s.scalars(select(WorkflowRun))).one()
        nr = (await s.scalars(select(WorkflowNodeRun))).one()
    assert wr.status == RunStatus.FAILED and nr.status == NodeStatus.FAILED and "restarted" in nr.error
    assert runner._parked == []
    assert (await client.get("/api/approvals")).json() == []


async def test_gates_are_shown_with_the_graph_validation_like_any_other_node(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    r = await client.patch(
        f"/api/workflows/{wid}",
        json={
            "graph": {
                "nodes": [node("s", "start"), node("g", "approval", prompt="ok?")],
                "edges": [edge("s", "g")],
            }
        },
    )
    assert r.status_code == 200 and r.json()["graph"]["nodes"][1]["kind"] == "approval"
