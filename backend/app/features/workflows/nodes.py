import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import get_args

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.execution.harnesses.catalog import clean_model_name
from app.execution.harnesses.types import Effort
from app.execution.profiles import ProfileOverrides
from app.features.projects import boards
from app.features.storage.volumes import MountRef
from app.features.system.settings import load_settings
from app.features.workflows.approvals import ApprovalGates
from app.features.workflows.conditions import evaluate_condition
from app.features.workflows.context import _Ctx, _Step
from app.features.workflows.folders import WorkflowFolders
from app.features.workflows.graph import (
    START_KINDS,
    GraphNode,
    NodeError,
    branch_count,
    branch_name,
)
from app.features.workflows.walk import MergeIn, Outcome, Prev
from app.persistence.models import (
    Agent,
    Attempt,
    AttemptStatus,
    Board,
    NodeStatus,
    Task,
    TaskStatus,
    WorkflowNodeRun,
)

QUEUE_PATIENCE_SECONDS = 6 * 3600


def _failed_message(exit_code: int | None) -> str:
    how = f"with exit code {exit_code}" if exit_code is not None else "before it could finish"
    return f"The task failed {how}. The log shows what happened."


class NodeHandlers:
    """Node behavior; the runner owns traversal, cancellation and node records."""

    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        scheduler: Callable[[], object],
        folders: WorkflowFolders,
        approvals: ApprovalGates,
        update_node: Callable[..., Awaitable[None]],
        poll_seconds: Callable[[], float],
    ) -> None:
        self.maker, self._scheduler = maker, scheduler
        self.folders, self.approvals = folders, approvals
        self._update_node, self.poll_seconds = update_node, poll_seconds

    async def dispatch(
        self, ctx: _Ctx, nr_id: int, node: GraphNode, prev: Prev | None, inputs: list[MergeIn] | None = None
    ) -> Outcome:
        c = node.config
        if node.kind in START_KINDS:
            return Outcome(NodeStatus.SUCCEEDED, log="Run started.\n")
        if node.kind == "end":
            return Outcome(
                NodeStatus.SUCCEEDED,
                log=f"Workflow ended: {c.get('outcome', 'success')}.\n{c.get('note', '')}".strip() + "\n",
            )
        if node.kind == "condition":
            answer, text = evaluate_condition(c, prev)
            return Outcome(
                NodeStatus.SUCCEEDED,
                log=text + "\n",
                result="yes" if answer else "no",
                branch="yes" if answer else "no",
            )
        if node.kind == "approval":
            return await self.approvals.wait(nr_id, node, prev)
        if node.kind == "split":
            return self._split(node, prev)
        if node.kind == "merge":
            return await self.folders.merge(ctx, node, inputs or [])
        if node.kind == "agent":
            return await self._agent(ctx, nr_id, node, prev)
        return await self._task(ctx, nr_id, node, prev)

    @staticmethod
    def _split(node: GraphNode, prev: Prev | None) -> Outcome:
        """Sends the run down its branches. Every branch gets the result of the step before; a branch whose rule is
        not met (the result must contain some text) is not sent anything, so a Splitter can also pick between ways."""
        c = node.config
        result = prev.result if prev else ""
        taken: set[str] = set()
        lines = []
        for number in range(1, branch_count(c) + 1):
            name, need, files = (
                branch_name(c, number),
                c.get(f"contains{number}", "").strip(),
                c.get(f"files{number}", "").strip(),
            )
            if not need or need.casefold() in result.casefold():
                taken.add(f"o{number}")
                lines.append(f"{name}: sent" + (f", only {files}" if files else ""))
            else:
                lines.append(f"{name}: not sent, the result does not contain {need!r}")
        if not taken:
            lines.append("No branch was sent anything.")
        return Outcome(
            NodeStatus.SUCCEEDED, result=result, log="\n".join(lines) + "\n", taken=frozenset(taken)
        )

    async def _agent(self, ctx: _Ctx, nr_id: int, node: GraphNode, prev: Prev | None) -> Outcome:
        c = node.config
        instructions = c.get("instructions", "").strip()
        if not instructions:
            raise NodeError("This agent has no instructions. Open the node and tell it what to do.")
        # a step opts out of the brief when the task's focus is not its business: a step that only does housekeeping
        # (syncing a clone, publishing) would otherwise take the focus as its own job and go and do the whole task
        brief = ""
        if c.get("brief") != "off":
            async with self.maker() as s:
                brief = await self._brief(s, ctx)
        # the order is the method (the node), the focus (the task), then what the step before it produced
        if brief:
            instructions += f"\n\n{brief}"
        if prev and prev.result.strip():
            instructions += f"\n\nResult of the previous step ({prev.label}):\n{prev.result.strip()}"
        title = node.label or "Agent"
        # "Continue" works in the folder the step before left (or the one the run started in); with none yet, or by
        # default, the agent gets a fresh folder like any other run
        workdir = await self.folders.continue_in(ctx, node, prev) if c.get("workdir") == "inherit" else None
        run_options = self._run_options(c, ctx.graph.mounts_for(node.id), workdir)
        async with self.maker() as s:
            agent = None
            if agent_id := c.get("agentId", "").strip():
                agent = await s.get(Agent, int(agent_id)) if agent_id.isdigit() else None
                if agent is None or agent.project_id != ctx.project_id:
                    raise NodeError(
                        "The agent of this node no longer exists. Open the node and choose another."
                    )
            board = await boards.default_board(
                s, ctx.project_id
            )  # a task needs a board, but this one is internal: it only shows when asked for
            task = Task(
                project_id=ctx.project_id, board_id=board.id, title=title, description=instructions,
                status=TaskStatus.READY, harness=agent.harness if agent else c.get("harness", "codex"),
                agent_id=agent.id if agent else None, run_options=run_options, internal=True,
                position=await boards.next_position(s, board.id, TaskStatus.READY),
            )  # fmt: skip
            s.add(task)
            await s.flush()
            # linked before the task can be picked up, so a workflow it plays can tell which run is waiting for it
            await s.execute(
                update(WorkflowNodeRun).where(WorkflowNodeRun.id == nr_id).values(task_id=task.id)
            )
            await s.commit()
            task_id = task.id
        return await self._wait_for_task(nr_id, task_id, before=0)

    @staticmethod
    async def _brief(s: AsyncSession, ctx: _Ctx) -> str:
        """What a step is told about the task behind its run. This is the steering wheel: a workflow says how to do
        the work, and the task's own description says what this run should focus on, so the same workflow can be
        pointed somewhere else by editing the ticket. A task that moved into a status started the run, or the run is
        a stage of the task; a test run has no task."""
        if ctx.trigger_task_id and (task := await s.get(Task, ctx.trigger_task_id)):
            return (
                f'This workflow was started by the task "{task.title}":\n'
                f"{task.description.strip() or '(no description)'}"
            )
        if ctx.stage_task_id and (task := await s.get(Task, ctx.stage_task_id)):
            if text := task.description.strip():
                return f'This is a stage of the task "{task.title}". What the task asks for:\n{text}'
            return f'This is a stage of the task "{task.title}".'
        return ""

    @staticmethod
    def _run_options(c: dict, attached: list[dict] | None = None, workdir: int | None = None) -> dict | None:
        """The model, cell size and shared folders set on an Agent node, for this run only. Node settings are plain
        text: the model and effort are `model` and `reasoningEffort` (empty: the agent's own, or Settings), the cell
        fields are separate keys, the folders one string like "3:rw,5:ro" (volume id and mode). Folders handed
        over by lines from Folder nodes (`attached`) come first; one named in the node's own list wins for that folder.
        `workdir` is the earlier attempt whose working folder this step continues in (see Attempt.workdir_id)."""
        try:
            fields = {
                "cellImage": "image",
                "cellCpus": "cpus",
                "cellMemory": "memory_mb",
                "cellTimeout": "timeout_seconds",
            }
            asked = {name: c[key].strip() for key, name in fields.items() if c.get(key, "").strip()}
            profile = ProfileOverrides.model_validate(asked).clean() if asked else None
            model = clean_model_name(c.get("model", ""))
            effort = c.get("reasoningEffort", "").strip()
            if effort and effort not in get_args(Effort):
                raise ValueError(effort)
            mounts = [MountRef.model_validate(m).model_dump() for m in attached or []]
            for part in filter(None, (p.strip() for p in c.get("mounts", "").split(","))):
                volume_id, _, mode = part.partition(":")
                mounts.append(MountRef(volume_id=int(volume_id), mode=mode or "rw").model_dump())
        except (ValidationError, ValueError):
            raise NodeError("The model, cell or folder settings of this agent node are not valid") from None
        extras = {"profile": profile, "mounts": mounts, "workdir": workdir, "model": model, "effort": effort}
        return {k: v for k, v in extras.items() if v} or None

    async def _task(self, ctx: _Ctx, nr_id: int, node: GraphNode, prev: Prev | None = None) -> Outcome:
        c = node.config
        action = c.get("action", "create")
        title = c.get("title", "").strip()
        if action != "move_trigger" and not title:
            raise NodeError("The task title is empty. Open the node and fill it in.")
        if action == "move_trigger" and ctx.trigger_task_id is None:
            raise NodeError(
                "No task started this run, so there is nothing to move. Use a Trigger set to "
                "'A task moves into a status' to start the workflow."
            )
        link = action == "create" and c.get("link") == "1"
        if link and ctx.trigger_task_id is None:
            raise NodeError(
                "No task started this run, so there is nothing to follow up. Use a Trigger set to "
                "'A task moves into a status', or turn off 'Follow up the task that started this run'."
            )
        target = c.get("status", "backlog")
        if target == TaskStatus.RUNNING or (
            target not in {s.value for s in TaskStatus} and boards.custom_id(target) is None
        ):
            raise NodeError(f"'{target}' is not a status a workflow can move a task to")
        async with self.maker() as s:
            step = await _Step.open(s, ctx, node)
            before = 0
            if action == "create":
                workdir = (
                    await self.folders.continue_in(ctx, node, prev) if c.get("workdir") == "inherit" else None
                )
                task = await self._create(s, step, c, title, target, link, workdir)
                note = (
                    f'Created task "{title}" on {(await s.get_one(Board, task.board_id)).name} in {target}.'
                )
            else:
                if action == "move_trigger":
                    task = await s.get(Task, ctx.trigger_task_id)
                    if task is None:
                        raise NodeError("The task that started this run was deleted.")
                    title = task.title
                else:
                    task = await s.scalar(
                        select(Task)
                        .where(Task.project_id == ctx.project_id, Task.title == title)
                        .order_by(Task.id.desc())
                        .limit(1)
                    )
                if task is None:
                    raise NodeError(f'There is no task titled "{title}" in this project.')
                if task.status == TaskStatus.RUNNING:
                    raise NodeError(f'The task "{title}" is already running.')
                before = (
                    await s.scalar(
                        select(func.coalesce(func.max(Attempt.id), 0)).where(Attempt.task_id == task.id)
                    )
                    or 0
                )
                if action == "run":
                    task.status, task.next_run_at = TaskStatus.READY, None
                    note = f'Started task "{title}".'
                else:
                    note = await self._relocate(s, step, task, c, target)
            await s.flush()
            await s.execute(
                update(WorkflowNodeRun).where(WorkflowNodeRun.id == nr_id).values(task_id=task.id)
            )
            await s.commit()
            task_id, becomes_ready = task.id, task.status == TaskStatus.READY
        if becomes_ready:
            return await self._wait_for_task(nr_id, task_id, before)
        return Outcome(NodeStatus.SUCCEEDED, log=note + "\n", result=note)

    async def _create(
        self,
        s: AsyncSession,
        step: "_Step",
        c: dict[str, str],
        title: str,
        target: str,
        link: bool,
        workdir: int | None = None,
    ) -> Task:
        """Make the task of a Create step: on the chosen board, linked to the task that started the run when asked.
        A step makes its task once, whatever happens: running it again finds the one it made. `workdir` is the working
        folder the task continues in; the task (or its first stage) starts there instead of in a fresh one."""
        key = f"run:{step.ctx.run_id}:{step.node.id}"
        if made := await s.scalar(select(Task).where(Task.origin_key == key)):
            return made
        await step.guard_hops()
        try:
            board = step.chosen_board or await boards.board_for_status(s, step.ctx.project_id, target)
            if link:
                assert step.trigger is not None
                task = await boards.spawn_task(
                    s, step.trigger, board, step.actor, title, c.get("description", ""), target,
                    step.cause, key, step.hops,
                )  # fmt: skip
                if workdir:
                    task.run_options = {**(task.run_options or {}), "workdir": workdir}
                return task
            boards.check_status(board, target)
            task = Task(
                project_id=step.ctx.project_id, board_id=board.id, title=title,
                description=c.get("description", ""), status=target, origin_key=key, hops=step.hops,
                run_options={"workdir": workdir} if workdir else None,
                position=await boards.next_position(s, board.id, target),
            )  # fmt: skip
        except boards.BoardError as e:
            raise NodeError(str(e)) from None
        s.add(task)
        await s.flush()
        boards.record_new_task(s, task, board, step.actor, step.cause)
        return task

    async def _relocate(
        self, s: AsyncSession, step: "_Step", task: Task, c: dict[str, str], target: str
    ) -> str:
        """Move a task to a status, and to another board when the step names one."""
        await step.guard_hops()
        board = step.chosen_board or await s.get_one(Board, task.board_id)
        try:
            if (board.id, target) != (task.board_id, task.status):  # lands at the bottom of its new column
                await boards.move_task(s, task, board, step.actor, target, None, step.cause)
        except boards.BoardError as e:
            raise NodeError(str(e)) from None
        task.next_run_at = None
        task.hops = step.hops
        if c.get("description", "").strip():
            task.description = c["description"]
        return f'Updated task "{task.title}": now {target} on {board.name}.'

    async def _wait_for_task(self, nr_id: int, task_id: int, before: int) -> Outcome:
        """Let the scheduler run the task, mirror its log into the node, and report how the attempt ended."""
        self._scheduler().wake()  # type: ignore[attr-defined]
        async with self.maker() as s:
            cfg = await load_settings(s)
        # Two clocks. A task that no cell has picked up is queued behind the others (several branches may want cells at
        # once, and the resource budget lets them in turn), so it is waited for patiently. The time limit only starts
        # once its attempt does, so a branch is never failed for waiting its turn.
        queued_at = time.monotonic()
        started_at: float | None = None
        shown: tuple[int, str] = (0, "")
        while True:
            await asyncio.sleep(self.poll_seconds())
            async with self.maker() as s:
                # The task first, then its attempt: the scheduler writes the attempt no later than the status it
                # leaves the task in, so a task seen as finished always has its attempt to be found. The other way
                # round, a task could fail between the two reads and be reported as moved, without its reason.
                task = await s.get(Task, task_id)
                attempt = await s.scalar(
                    select(Attempt)
                    .where(Attempt.task_id == task_id, Attempt.id > before)
                    .order_by(Attempt.id.desc())
                    .limit(1)
                )
            if attempt is not None:
                started_at = started_at or time.monotonic()
                if (attempt.id, attempt.log) != shown:
                    shown = (attempt.id, attempt.log)
                    await self._update_node(
                        nr_id, attempt_id=attempt.id, log=attempt.log, result=attempt.result
                    )
                if attempt.status != AttemptStatus.RUNNING:
                    here = attempt.workdir_id
                    if attempt.status == AttemptStatus.SUCCEEDED:
                        return Outcome(
                            NodeStatus.SUCCEEDED, result=attempt.result, log=attempt.log, workdir_id=here
                        )
                    # the attempt knows why it failed (see Attempt.failure); the exit code is the fallback
                    why = (
                        "The task was cancelled."
                        if attempt.status == AttemptStatus.CANCELLED
                        else (attempt.failure or {}).get("reason") or _failed_message(attempt.exit_code)
                    )
                    return Outcome(
                        NodeStatus.FAILED, result=attempt.result, log=attempt.log, error=why, workdir_id=here
                    )
            elif task is None:
                raise NodeError("The task was deleted while the workflow was waiting for it.")
            elif task.status not in (TaskStatus.READY, TaskStatus.RUNNING):
                raise NodeError(f"The task was moved to {task.status} before it could run.")
            now = time.monotonic()
            if started_at is None and now - queued_at > QUEUE_PATIENCE_SECONDS:
                raise NodeError("Timed out waiting for a free cell to start the task.")
            if started_at is not None and now - started_at > cfg.cell_timeout_seconds + 600:
                raise NodeError("Timed out waiting for the task to run.")
