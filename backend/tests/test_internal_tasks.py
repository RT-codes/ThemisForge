"""The tasks workflow Agent nodes make to run their steps: kept off the boards, quick to start, and what a task that
plays workflows reports."""

from tests.test_harness import connect
from tests.test_workflows import attempt_of, edge, make_workflow, node, play_task, run, save, setup


def agent(id_: str, label: str, **config) -> dict:
    return node(id_, "agent", label, harness="codex", instructions=f"Do {label}", **config)


async def titles(client, pid: int, **params) -> set[str]:
    return {t["title"] for t in (await client.get(f"/api/projects/{pid}/tasks", params=params)).json()}


async def test_an_agent_nodes_task_stays_off_the_board_unless_asked_for(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    detail = await run(
        client, pid,
        [node("s", "start"), agent("a", "Step"), node("t", "task", title="Real work", status="backlog"), node("e", "end")],
        [edge("s", "a"), edge("a", "t"), edge("t", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded", detail
    assert await titles(client, pid) == {"Real work"}  # a Task node's task is board work
    assert await titles(client, pid, include_steps=True) == {"Real work", "Step"}
    step = next(
        t for t in (await client.get(f"/api/projects/{pid}/tasks", params={"include_steps": True})).json()
        if t["title"] == "Step"
    )  # fmt: skip
    assert step["internal"] is True and step["status"] == "done"
    # and it is not counted as work on the project
    summary = next(p for p in (await client.get("/api/projects")).json() if p["id"] == pid)
    assert summary["task_counts"] == {"backlog": 1}


async def test_a_step_does_not_wait_out_the_start_delay(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    # a delay an ordinary ready task would sit through for an hour
    r = await client.patch(f"/api/projects/{pid}", json={"automation": {"start_cooldown_seconds": 3600}})
    assert r.status_code == 200, r.text
    detail = await run(
        client, pid,
        [node("s", "start"), agent("a", "Quick step"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded", detail  # wait_for_run gives up after 10 seconds
    assert [s.title for s in cells.specs] == ["Quick step"]


async def test_a_step_moved_by_hand_starts_no_workflow(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    listener = await make_workflow(client, pid, "Listener")
    await save(
        client, listener,
        [node("t", "trigger", type="task_status", status="done"), node("e", "end")],
        [edge("t", "e")],
    )  # fmt: skip
    detail = await run(
        client,
        pid,
        [node("s", "start"), agent("a", "Step"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )
    assert detail["status"] == "succeeded"
    runs = (await client.get(f"/api/workflows/{listener}/runs")).json()
    assert runs == []  # the step reached Done, which the listener watches, and it did not start


# ----- what a task that plays workflows reports -----


async def test_a_task_reports_what_its_stages_produced(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    first = await make_workflow(client, pid, "Research")
    await save(client, first, [node("s", "start"), agent("a", "Look around"), node("e", "end", note="Done")],
               [edge("s", "a"), edge("a", "e")])  # fmt: skip
    second = await make_workflow(client, pid, "Ship it")
    await save(client, second, [node("s", "start"), agent("b", "Publish"), node("e", "end", note="Shipped")],
               [edge("s", "b"), edge("b", "e")])  # fmt: skip
    task = await play_task(client, pid, [first, second])
    result = (await attempt_of(client, task["id"]))["result"]
    assert result.startswith("## Research\n") and "(Look around) finished" in result
    assert "## Ship it\n" in result and "(Publish) finished" in result
    assert "Done" not in result and "Shipped" not in result  # the End notes are not the output


async def test_a_stage_with_nothing_to_report_falls_back_to_its_end_note(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid, "Quiet")
    await save(client, wid, [node("s", "start"), node("e", "end", note="All quiet")], [edge("s", "e")])
    task = await play_task(client, pid, wid)
    assert (await attempt_of(client, task["id"]))["result"] == "All quiet"
