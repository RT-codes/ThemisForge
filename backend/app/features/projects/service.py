from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.errors import ApplicationError, invalid
from app.features.projects import boards, halt
from app.features.projects.access import require_project
from app.features.projects.properties import validate_definitions
from app.features.projects.schemas import HaltIn, ProjectIn, ProjectPatch
from app.persistence.models import (
    Project,
    Task,
    TaskStatus,
    User,
)
from app.runtime import Runtime


async def create_project(body: ProjectIn, session: AsyncSession, user: User) -> Project:
    project = Project(
        owner_id=user.id,
        name=body.name,
        purpose=body.purpose,
        description=body.description,
        icon=body.icon,
        properties=[],
        cell_profile=body.cell_profile.clean() if body.cell_profile else None,
        automation=body.automation.clean() if body.automation else None,
    )
    session.add(project)
    await session.flush()
    await boards.create_defaults(session, project.id)  # every project has a board to put tasks on
    await session.commit()
    return project


async def halt_project(
    project_id: int, body: HaltIn, runtime: Runtime, session: AsyncSession, user: User
) -> Project:
    """Nothing in the project starts until it is resumed; by default what is running is stopped too."""
    project = await require_project(session, project_id, user)
    await halt.halt(
        session, runtime.scheduler, project, None, stop_running=body.stop_running, actor=user.name
    )
    await session.refresh(project)
    return project


async def resume_project(project_id: int, runtime: Runtime, session: AsyncSession, user: User) -> Project:
    project = await require_project(session, project_id, user)
    await halt.resume(session, runtime.scheduler, project, None, user.name)
    await session.refresh(project)
    return project


async def get_project(project_id: int, session: AsyncSession, user: User) -> Project:
    return await require_project(session, project_id, user)


async def update_project(project_id: int, body: ProjectPatch, session: AsyncSession, user: User) -> Project:
    project = await require_project(session, project_id, user)
    if body.name is not None:
        project.name = body.name.strip() or project.name
    if body.purpose is not None:
        project.purpose = body.purpose
    if body.description is not None:
        project.description = body.description
    if body.icon is not None:
        project.icon = body.icon
    if "cell_profile" in body.model_fields_set:
        project.cell_profile = body.cell_profile.clean() if body.cell_profile else None
    if "automation" in body.model_fields_set:
        project.automation = body.automation.clean() if body.automation else None
    if body.properties is not None:
        try:
            project.properties = validate_definitions(body.properties)
        except ValueError as e:
            raise invalid(str(e)) from None
    await session.commit()
    return project


async def delete_project(project_id: int, session: AsyncSession, user: User) -> None:
    project = await require_project(session, project_id, user)
    running = await session.scalar(
        select(func.count()).where(Task.project_id == project.id, Task.status == TaskStatus.RUNNING)
    )
    if running:
        raise ApplicationError(
            status.HTTP_409_CONFLICT, "Cancel the running tasks before deleting the project"
        )
    await session.delete(project)
    await session.commit()
