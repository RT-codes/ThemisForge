from typing import Annotated

from fastapi import APIRouter, Query, Request, status

import app.features.projects.queries as project_queries
import app.features.projects.service as operations
from app.api.dependencies import CurrentUser, SessionDep
from app.features.projects.schemas import (
    HaltIn,
    ProjectEventOut,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    ProjectSummary,
)
from app.persistence.models import (
    Project,
    ProjectEvent,
)

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectSummary])
async def list_projects(session: SessionDep, user: CurrentUser) -> list[ProjectSummary]:
    return await project_queries.list_projects(session, user)


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectIn, session: SessionDep, user: CurrentUser) -> Project:
    return await operations.create_project(body, session, user)


@router.post("/projects/{project_id}/halt", response_model=ProjectOut)
async def halt_project(
    project_id: int, body: HaltIn, request: Request, session: SessionDep, user: CurrentUser
) -> Project:
    """Nothing in the project starts until it is resumed; by default what is running is stopped too."""

    return await operations.halt_project(project_id, body, request.app.state, session, user)


@router.post("/projects/{project_id}/resume", response_model=ProjectOut)
async def resume_project(
    project_id: int, request: Request, session: SessionDep, user: CurrentUser
) -> Project:
    return await operations.resume_project(project_id, request.app.state, session, user)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, session: SessionDep, user: CurrentUser) -> Project:
    return await operations.get_project(project_id, session, user)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int, body: ProjectPatch, session: SessionDep, user: CurrentUser
) -> Project:
    return await operations.update_project(project_id, body, session, user)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: int, session: SessionDep, user: CurrentUser) -> None:
    return await operations.delete_project(project_id, session, user)


@router.get("/projects/{project_id}/history", response_model=list[ProjectEventOut])
async def project_history(
    project_id: int,
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    before: Annotated[int | None, Query(description="Only events older than this id (the next page)")] = None,
    workspace_id: int | None = None,
    board_id: int | None = None,
    task_id: int | None = None,
    kind: Annotated[list[str] | None, Query(description="Only these kinds of event")] = None,
) -> list[ProjectEvent]:
    """What was done to the project, newest first, optionally only what concerns one workspace, board or task. A task
    that left a board is part of that board's history too, and a follow-up is part of the history of its origin."""

    return await project_queries.project_history(
        project_id, session, user, limit, before, workspace_id, board_id, task_id, kind
    )
