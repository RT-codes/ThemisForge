"""Working folders that later steps continue in: agent nodes, stages, tasks made by a workflow, and clean-up."""

from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.execution.cells.contract import CellSpec
from app.execution.cells.files import changes_between, snapshot_workdir
from app.execution.harnesses.prompts import EarlierStep, build_prompt, workdir_note
from app.features.workflows.folders import task_workdir
from app.persistence.models import Attempt, AttemptStatus, Task, utcnow
from tests.test_harness import connect
from tests.test_workflows import attempt_of, edge, make_workflow, node, play_task, run, save, setup

FRESH = "is private to this run"
CONTINUED = "continued from earlier steps"


def agent(id_: str, label: str, **config) -> dict:
    return node(id_, "agent", label, harness="codex", instructions=f"Do {label}", **config)


def spec_of(cells, title: str) -> CellSpec:
    return next(s for s in cells.specs if s.title == title)


async def attempt(client, spec: CellSpec) -> dict:
    return (await client.get(f"/api/attempts/{spec.attempt_id}")).json()


# ----- the snapshot -----


def test_changes_are_what_was_added_changed_and_removed():
    before = {"a.md": (1, 10), "b.md": (1, 10), "c.md": (1, 10)}
    after = {"a.md": (1, 10), "b.md": (2, 20), "d/e.md": (3, 30)}
    assert changes_between(before, after) == {
        "added": ["d/e.md"], "changed": ["b.md"], "removed": ["c.md"], "more": 0,
    }  # fmt: skip


def test_the_snapshot_skips_mountpoints_and_tool_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    spec = CellSpec(5, 1, 1, "t", "", {}, "img", 1, 256, 60)
    root = spec.workspace_dir
    for rel in ("notes.md", "src/a.py", ".git/HEAD", "node_modules/x/i.js", ".agents/skills/s.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x")
    assert set(snapshot_workdir(spec)) == {"notes.md", "src/a.py"}


def test_a_continued_folder_is_described_to_the_agent():
    note = workdir_note(
        [
            EarlierStep(
                "Research",
                "succeeded",
                {"added": ["notes.md"], "changed": [], "removed": []},
                "Found 3 sources",
            )
        ],
        ["notes.md", "data/"],
    )
    assert "Research" in note and "added notes.md" in note and "Found 3 sources" in note and "data/" in note
    prompt = build_prompt("T", "", {}, notes=[note], continuing=True)
    assert CONTINUED in prompt and "private to this run" not in prompt
    assert FRESH in build_prompt("T", "", {})


# ----- agent nodes -----


async def test_every_agent_gets_a_fresh_folder_unless_it_asks_to_continue(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    cells.files = {"Research": {"notes.md": "n", "data/src.csv": "s"}}
    detail = await run(
        client, pid,
        [node("s", "start"), agent("a", "Research"), agent("b", "Write", workdir="inherit"), agent("c", "Review"), node("e", "end")],
        [edge("s", "a"), edge("a", "b"), edge("b", "c"), edge("c", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded", detail
    research, write, review = (spec_of(cells, t) for t in ("Research", "Write", "Review"))
    assert research.workdir_id == research.attempt_id  # its own
    assert write.workdir_id == research.attempt_id and write.workspace_dir == research.workspace_dir
    assert review.workdir_id == review.attempt_id and review.workspace_dir != write.workspace_dir

    # the continuing agent is told what the step before it did; the others are not
    assert CONTINUED in write.prompt and "notes.md" in write.prompt and "data/src.csv" in write.prompt
    assert FRESH in review.prompt and CONTINUED not in review.prompt and FRESH in research.prompt
    # and the run records it
    first = await attempt(client, research)
    assert first["workdir_id"] == research.attempt_id
    assert first["changes"]["added"] == ["data/src.csv", "notes.md"]
    assert (await attempt(client, write))["workdir_id"] == research.attempt_id


async def test_continuing_with_nothing_before_it_is_just_a_fresh_folder(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    detail = await run(
        client, pid,
        [node("s", "start"), agent("a", "Alone", workdir="inherit"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded"
    spec = spec_of(cells, "Alone")
    assert spec.workdir_id == spec.attempt_id and FRESH in spec.prompt


async def test_a_condition_passes_the_folder_on(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    detail = await run(
        client, pid,
        [node("s", "start"), agent("a", "First"), node("c", "condition", source="status", operator="equals", value="succeeded"),
         agent("b", "Second", workdir="inherit"), node("e", "end")],
        [edge("s", "a"), edge("a", "c"), edge("c", "b", "yes"), edge("b", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded", detail
    assert spec_of(cells, "Second").workdir_id == spec_of(cells, "First").attempt_id


async def test_a_step_that_failed_still_leaves_its_files_for_the_next(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    cells.files = {"Try to fail": {"partial.md": "half"}}
    detail = await run(
        client, pid,
        [node("s", "start"), agent("a", "Try to fail", onFailure="continue"), agent("b", "Fix it", workdir="inherit"), node("e", "end")],
        [edge("s", "a"), edge("a", "b"), edge("b", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded", detail
    assert "partial.md" in spec_of(cells, "Fix it").prompt and "failed" in spec_of(cells, "Fix it").prompt


# ----- stages -----


async def test_a_stage_starts_in_the_folder_the_stage_before_it_ended_in(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    first = await make_workflow(client, pid, "Research flow")
    await save(
        client,
        first,
        [node("s", "start"), agent("a", "Research"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )
    second = await make_workflow(client, pid, "Writing flow")
    await save(
        client, second,
        [node("s", "start"), agent("b", "Write", workdir="inherit"), agent("c", "Own space"), node("e", "end")],
        [edge("s", "b"), edge("b", "c"), edge("c", "e")],
    )  # fmt: skip
    task = await play_task(client, pid, [first, second])
    done = await attempt_of(client, task["id"])
    assert done["status"] == "succeeded", done
    research, write, own = (spec_of(cells, t) for t in ("Research", "Write", "Own space"))
    assert write.workdir_id == research.attempt_id
    assert own.workdir_id == own.attempt_id  # a node that did not ask to continue keeps its own folder
    # the task's own attempt ends up pointing at the last folder its stages worked in
    assert done["workdir_id"] == own.attempt_id


async def test_a_stage_that_does_not_continue_is_unaffected_by_the_stage_before(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    one = await make_workflow(client, pid, "One")
    await save(
        client,
        one,
        [node("s", "start"), agent("a", "Alpha"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )
    two = await make_workflow(client, pid, "Two")
    await save(
        client,
        two,
        [node("s", "start"), agent("b", "Beta"), node("e", "end")],
        [edge("s", "b"), edge("b", "e")],
    )
    task = await play_task(client, pid, [one, two])
    assert (await attempt_of(client, task["id"]))["status"] == "succeeded"
    beta = spec_of(cells, "Beta")
    assert beta.workdir_id == beta.attempt_id and FRESH in beta.prompt


# ----- tasks made by a workflow -----


async def test_a_task_made_by_a_workflow_can_continue_in_the_folder_it_was_made_from(
    client, runner, cells, maker
):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    detail = await run(
        client, pid,
        [node("s", "start"), agent("a", "Research"), node("t", "task", title="Follow up", status="ready", workdir="inherit"),
         node("u", "task", title="Separate", status="ready"), node("e", "end")],
        [edge("s", "a"), edge("a", "t"), edge("t", "u"), edge("u", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded", detail
    research = spec_of(cells, "Research")
    async with maker() as s:
        follow = await s.scalar(select(Task).where(Task.title == "Follow up"))
        separate = await s.scalar(select(Task).where(Task.title == "Separate"))
    assert follow is not None and follow.run_options == {"workdir": research.attempt_id}
    assert separate is not None and not separate.run_options
    assert spec_of(cells, "Follow up").workdir_id == research.attempt_id
    assert spec_of(cells, "Separate").workdir_id == spec_of(cells, "Separate").attempt_id


async def test_a_folder_that_is_gone_starts_empty_and_says_so(client, runner, cells, maker):
    me, pid = await setup(client)
    await connect(maker, me["id"])
    async with maker() as s:
        task = Task(project_id=pid, board_id=await _board(s, pid), title="Orphan", harness="codex",
                    status="ready", run_options={"workdir": 424242})  # fmt: skip
        s.add(task)
        await s.commit()
    done = await attempt_of(client, task.id)
    assert done["status"] == "succeeded"
    spec = spec_of(cells, "Orphan")
    assert spec.workdir_id == spec.attempt_id and "is gone" in spec.prompt and FRESH in spec.prompt


async def _board(s, pid: int) -> int:
    from app.features.projects import boards

    return (await boards.default_board(s, pid)).id


async def test_a_workflow_started_by_a_task_begins_in_that_tasks_folder(client, maker):
    _, pid = await setup(client)
    async with maker() as s:
        task = Task(project_id=pid, board_id=await _board(s, pid), title="Worker", status="review")
        s.add(task)
        await s.flush()
        s.add_all(
            [
                Attempt(task_id=task.id, status=AttemptStatus.SUCCEEDED, workdir_id=11),
                Attempt(task_id=task.id, status=AttemptStatus.SUCCEEDED, workdir_id=17),
            ]
        )
        await s.commit()
        assert await task_workdir(s, task) == 17  # the latest
        task.run_options = {"workdir": 5}
        assert await task_workdir(s, task) == 17
        other = Task(project_id=pid, board_id=task.board_id, title="Made", run_options={"workdir": 5})
        s.add(other)
        await s.flush()
        assert await task_workdir(s, other) == 5  # not run yet: where it was made to continue


# ----- clean-up -----


async def test_a_folder_lives_as_long_as_the_last_step_that_continued_in_it(client, scheduler, maker):
    _, pid = await setup(client)
    root = settings.data_dir / "projects" / str(pid) / "workspaces"
    async with maker() as s:
        board = await _board(s, pid)
        task = Task(project_id=pid, board_id=board, title="T")
        s.add(task)
        await s.flush()
        old = Attempt(
            task_id=task.id, status=AttemptStatus.SUCCEEDED, finished_at=utcnow() - timedelta(days=30)
        )
        s.add(old)
        await s.flush()
        s.add(
            Attempt(task_id=task.id, status=AttemptStatus.SUCCEEDED, workdir_id=old.id, finished_at=utcnow()),
        )
        lone = Attempt(
            task_id=task.id, status=AttemptStatus.SUCCEEDED, finished_at=utcnow() - timedelta(days=30)
        )
        s.add(lone)
        await s.commit()
    for attempt_id in (old.id, lone.id):
        (root / str(attempt_id)).mkdir(parents=True)
    assert await scheduler.prune_workspaces() == 1
    assert (root / str(old.id)).exists()  # a recent step continued in it
    assert not (root / str(lone.id)).exists()
