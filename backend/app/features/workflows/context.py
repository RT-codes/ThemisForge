from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects import automation, boards
from app.features.system.settings import load_settings
from app.features.workflows.graph import (
    Graph,
    GraphNode,
    NodeError,
)
from app.persistence.models import (
    Board,
    Project,
    Task,
    Workflow,
    WorkflowRun,
)


@dataclass
class _Ctx:
    run_id: int
    project_id: int
    graph: Graph
    trigger_task_id: int | None = None  # the task whose move into a status started this run
    # the task this run is a stage of: it is the brief for the run (what to focus on), see `_brief`
    stage_task_id: int | None = None
    # the working folder the run starts in (from the stage before it, or the task that started it): the first step
    # that asks to continue works there. Every step otherwise gets a fresh folder.
    workdir_id: int | None = None


class _Step:
    """What a Task step needs to know before it moves or makes a task: who it acts as, the board it was told to use,
    and how many times in a row automation has already handled the task that started this run (the loop guard)."""

    def __init__(
        self,
        s: AsyncSession,
        ctx: _Ctx,
        node: GraphNode,
        actor: str,
        trigger: Task | None,
        chosen_board: Board | None,
        limit: int,
    ) -> None:
        self.s, self.ctx, self.node, self.actor, self.trigger, self.chosen_board = (
            s, ctx, node, actor, trigger, chosen_board,
        )  # fmt: skip
        self.cause = f"run:{ctx.run_id}:{node.id}"
        self.hops = (
            trigger.hops if trigger else 0
        ) + 1  # this step would be one more handling of the same chain
        self.limit = limit

    @classmethod
    async def open(cls, s: AsyncSession, ctx: _Ctx, node: GraphNode) -> "_Step":
        run = await s.get(WorkflowRun, ctx.run_id)
        workflow = await s.get(Workflow, run.workflow_id) if run else None
        trigger = await s.get(Task, ctx.trigger_task_id) if ctx.trigger_task_id else None
        project = await s.get(Project, ctx.project_id)
        chosen: Board | None = None
        if wanted := node.config.get("boardId", "").strip():
            chosen = await s.get(Board, int(wanted)) if wanted.isdigit() else None
            if chosen is None or chosen.project_id != ctx.project_id:
                raise NodeError("The board of this step no longer exists. Open the step and choose another.")
        actor = f"Workflow {workflow.name}" if workflow else "A workflow"
        limit = automation.hop_limit(await load_settings(s), project, trigger)
        return cls(s, ctx, node, actor, trigger, chosen, limit)

    async def guard_hops(self) -> None:
        """Stop, with the reason in the run and in the project's history, when this would be one handling too many."""
        if self.hops <= self.limit:
            return
        reason = (
            f"Stopped to keep automation from looping: this task has been moved or made by workflows "
            f"{self.hops - 1} times in a row (the limit is {self.limit}). Move it by hand to carry on, or raise the "
            f"limit for the project or the task."
        )
        board = await self.s.get(Board, self.trigger.board_id) if self.trigger else None
        boards.record(
            self.s, "automation_stopped", self.ctx.project_id, self.trigger.title if self.trigger else self.actor,
            self.actor, workspace_id=board.workspace_id if board else None, board_id=board.id if board else None,
            task_id=self.trigger.id if self.trigger else None, cause=self.cause,
            data={"reason": reason, "limit": self.limit, "step": self.node.label or self.node.kind},
        )  # fmt: skip
        await self.s.commit()
        raise NodeError(reason)
