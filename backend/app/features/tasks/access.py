from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.errors import ApplicationError
from app.persistence.models import (
    Project,
    Task,
    User,
)


async def require_task(session: AsyncSession, task_id: int, user: User) -> Task:
    task = await session.get(Task, task_id)
    project = await session.get(Project, task.project_id) if task else None
    if task is None or project is None or project.owner_id != user.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Task not found")
    return task
