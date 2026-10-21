from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects.access import require_project
from app.features.projects.schemas import ProjectOut, ProjectSummary
from app.persistence.models import (
    Project,
    ProjectEvent,
    Task,
    TaskStatus,
    User,
)


async def list_projects(session: AsyncSession, user: User) -> list[ProjectSummary]:
    projects = (
        await session.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.name))
    ).all()
    counts: dict[int, dict[str, int]] = {}
    rows = await session.execute(
        select(Task.project_id, Task.status, func.count())
        .where(Task.project_id.in_([p.id for p in projects]), Task.internal.is_(False))
        .group_by(Task.project_id, Task.status)
    )
    for project_id, task_status, n in rows:
        counts.setdefault(project_id, {})[task_status] = n
    next_rows = await session.execute(
        select(Task.project_id, func.min(Task.next_run_at))
        .where(Task.status == TaskStatus.READY, Task.next_run_at.is_not(None), Task.internal.is_(False))
        .group_by(Task.project_id)
    )
    nexts = dict(next_rows.all())
    return [
        ProjectSummary(
            **ProjectOut.model_validate(p).model_dump(),
            task_counts=counts.get(p.id, {}),
            next_run_at=nexts.get(p.id),
        )
        for p in projects
    ]


async def project_history(
    project_id: int,
    session: AsyncSession,
    user: User,
    limit: int = 50,
    before: int | None = None,
    workspace_id: int | None = None,
    board_id: int | None = None,
    task_id: int | None = None,
    kind: list[str] | None = None,
) -> list[ProjectEvent]:
    """What was done to the project, newest first, optionally only what concerns one workspace, board or task. A task
    that left a board is part of that board's history too, and a follow-up is part of the history of its origin."""
    await require_project(session, project_id, user)
    query = select(ProjectEvent).where(ProjectEvent.project_id == project_id)
    if before is not None:
        query = query.where(ProjectEvent.id < before)
    if kind:
        query = query.where(ProjectEvent.kind.in_(kind))
    if workspace_id is not None:
        query = query.where(
            (ProjectEvent.workspace_id == workspace_id)
            | (func.json_extract(ProjectEvent.data, "$.from.workspace_id") == workspace_id)
        )
    if board_id is not None:
        query = query.where(
            (ProjectEvent.board_id == board_id)
            | (func.json_extract(ProjectEvent.data, "$.from.board_id") == board_id)
        )
    if task_id is not None:
        query = query.where(
            (ProjectEvent.task_id == task_id)
            | (func.json_extract(ProjectEvent.data, "$.origin.task_id") == task_id)
        )
    return list(await session.scalars(query.order_by(ProjectEvent.id.desc()).limit(limit)))
