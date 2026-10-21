from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.errors import ApplicationError
from app.persistence.models import (
    Project,
    User,
)


async def require_project(session: AsyncSession, project_id: int, user: User) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Project not found")
    return project
