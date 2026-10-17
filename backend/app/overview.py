"""A project at a glance: what an agent (or a person) reads first to know what is going on.

Built from the same handlers the web interface uses, so it says what the interface says: the counts, what is running
now, what waits for a person, what happened lately and what is coming. Nothing here is stored.
"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TaskStatus, User
from .routers import agents, projects, workflows, workspaces
from .routers.workflows import ApprovalOut
from .schemas import ProjectEventOut, ProjectSummary, ScheduledRun, UsageRow

LIST_LIMIT = 15  # per list: an overview is a summary, the list tools give the rest


class BoardLine(BaseModel):
    id: int
    workspace: str
    name: str
    task_counts: dict[str, int]  # tasks per status key ("backlog", "ready", ..., "custom:3")
    halted: bool


class TaskLine(BaseModel):
    task_id: int
    title: str
    status: str
    board_id: int
    # why it failed, when it did; empty otherwise
    reason: str = ""


class ProjectOverview(BaseModel):
    project: ProjectSummary  # with the number of tasks per status and when the next one starts
    halted: bool  # nothing starts while the project is halted
    boards: list[BoardLine]
    running: list[TaskLine]
    # what needs a person: failed and blocked tasks, tasks in review, and workflow approvals
    needs_attention: list[TaskLine]
    approvals: list[ApprovalOut]
    upcoming: list[ScheduledRun]  # the next day
    recent_events: list[ProjectEventOut]
    usage_last_7_days: list[UsageRow]
    agents: int
    workflows: int
    # lists above are cut to this many entries; the task counts in `project` are always complete
    list_limit: int = LIST_LIMIT


async def project_overview(session: AsyncSession, owner: User, project_id: int) -> ProjectOverview:
    summary = next((p for p in await projects.list_projects(session, owner) if p.id == project_id), None)
    if summary is None:  # not the owner's, or gone: say what the REST route says
        await projects.get_project(project_id, session, owner)
        raise LookupError(project_id)
    tasks = await projects.list_tasks(project_id, session, owner, board_id=None, include_steps=False)
    boards = [
        BoardLine(
            id=b.id,
            workspace=w.name,
            name=b.name,
            task_counts=b.task_counts,
            halted=b.halted_at is not None,
        )
        for w in await workspaces.list_workspaces(project_id, session, owner)
        for b in w.boards
    ]

    def line(t) -> TaskLine:
        return TaskLine(
            task_id=t.id, title=t.title, status=t.status, board_id=t.board_id, reason=t.last_failure_reason
        )

    waiting = (TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.REVIEW)
    open_approvals = [a for a in await workflows.list_approvals(session, owner) if a.project_id == project_id]
    return ProjectOverview(
        project=summary,
        halted=summary.halted_at is not None,
        boards=boards,
        running=[line(t) for t in tasks if t.status == TaskStatus.RUNNING][:LIST_LIMIT],
        needs_attention=[line(t) for t in tasks if t.status in waiting][:LIST_LIMIT],
        approvals=open_approvals[:LIST_LIMIT],
        upcoming=(await projects.upcoming_runs(project_id, session, owner, hours=24))[:LIST_LIMIT],
        recent_events=[
            ProjectEventOut.model_validate(e)
            for e in await projects.project_history(project_id, session, owner, limit=10)
        ],
        usage_last_7_days=await projects.project_usage(project_id, session, owner, days=7),
        agents=len(await agents.list_agents(project_id, session, owner)),
        workflows=len(await workflows.list_workflows(project_id, session, owner)),
    )
