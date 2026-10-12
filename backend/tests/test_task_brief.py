"""The task behind a run is its brief: its description reaches the agents of every stage, so a ticket steers a workflow."""

from tests.test_harness import connect
from tests.test_workflows import attempt_of, edge, make_workflow, node, play_task, save, setup


def agent(id_: str, label: str, **config) -> dict:
    return node(id_, "agent", label, harness="codex", instructions=f"Do {label}", **config)


def prompt_of(cells, title: str) -> str:
    return next(s for s in cells.specs if s.title == title).prompt


async def test_a_stage_is_given_the_task_it_belongs_to(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    wid = await make_workflow(client, pid, "Flow")
    await save(
        client,
        wid,
        [node("s", "start"), agent("a", "Research"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )
    task = await play_task(
        client, pid, wid, title="Improve the game", description="Focus on gameplay depth, not housekeeping."
    )
    assert (await attempt_of(client, task["id"]))["status"] == "succeeded"
    prompt = prompt_of(cells, "Research")
    assert 'This is a stage of the task "Improve the game"' in prompt
    assert "Focus on gameplay depth, not housekeeping." in prompt
    assert prompt.index("Do Research") < prompt.index("Focus on gameplay depth")  # the method, then the focus


async def test_the_focus_comes_before_what_the_step_before_it_produced(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    wid = await make_workflow(client, pid, "Flow")
    await save(
        client, wid,
        [node("s", "start"), node("t", "task", "Gather", title="Gathered", status="ready"), agent("a", "Write"), node("e", "end")],
        [edge("s", "t"), edge("t", "a"), edge("a", "e")],
    )  # fmt: skip
    task = await play_task(client, pid, wid, title="Brief", description="Mind the roadmap.")
    assert (await attempt_of(client, task["id"]))["status"] == "succeeded"
    prompt = prompt_of(cells, "Write")
    assert prompt.index("Mind the roadmap.") < prompt.index("Result of the previous step (Gather)")


async def test_a_task_without_a_description_still_names_itself(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    wid = await make_workflow(client, pid, "Flow")
    await save(
        client,
        wid,
        [node("s", "start"), agent("a", "Do it"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )
    task = await play_task(client, pid, wid, title="Just a title")
    assert (await attempt_of(client, task["id"]))["status"] == "succeeded"
    prompt = prompt_of(cells, "Do it")
    assert 'This is a stage of the task "Just a title".' in prompt and "(no description)" not in prompt


async def test_a_test_run_has_no_task_so_nothing_is_added(client, runner, cells, maker):
    from tests.test_workflows import run

    me, pid = await setup(client)
    await connect(maker, me["id"])
    detail = await run(
        client,
        pid,
        [node("s", "start"), agent("a", "Solo"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )
    assert detail["status"] == "succeeded"
    assert "stage of the task" not in prompt_of(cells, "Solo") and "started by the task" not in prompt_of(
        cells, "Solo"
    )


async def test_a_step_can_opt_out_of_the_brief(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    wid = await make_workflow(client, pid, "Flow")
    await save(
        client,
        wid,
        [node("s", "start"), agent("a", "Sync", brief="off"), agent("b", "Build"), node("e", "end")],
        [edge("s", "a"), edge("a", "b"), edge("b", "e")],
    )
    task = await play_task(client, pid, wid, title="Improve it", description="Focus on the village.")
    assert (await attempt_of(client, task["id"]))["status"] == "succeeded"
    assert "Focus on the village." not in prompt_of(cells, "Sync")  # housekeeping stays housekeeping
    assert "This is a stage" not in prompt_of(cells, "Sync")
    assert "Focus on the village." in prompt_of(cells, "Build")  # the other steps are unaffected
