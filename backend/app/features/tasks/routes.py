from typing import Annotated

from fastapi import APIRouter, Query, Request, status

import app.features.tasks.queries as task_queries
import app.features.tasks.service as task_service
from app.api.dependencies import CurrentUser, SessionDep
from app.features.tasks.schemas import (
    AttemptDetail,
    AttemptOut,
    ScheduledRun,
    TaskIn,
    TaskOut,
    TaskPatch,
    UsageRow,
)
from app.persistence.models import (
    Attempt,
)

router = APIRouter(tags=["projects"])


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
async def list_tasks(
    project_id: int,
    session: SessionDep,
    user: CurrentUser,
    board_id: Annotated[int | None, Query(description="Only the tasks of this board")] = None,
    include_steps: Annotated[
        bool, Query(description="Also the tasks that workflow Agent nodes made to run their steps")
    ] = False,
) -> list[TaskOut]:
    return await task_queries.list_tasks(project_id, session, user, board_id, include_steps)


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    project_id: int, body: TaskIn, request: Request, session: SessionDep, user: CurrentUser
) -> TaskOut:
    return await task_service.create_task(project_id, body, request.app.state, session, user)


@router.post("/tasks/{task_id}/duplicate", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def duplicate_task(task_id: int, session: SessionDep, user: CurrentUser) -> TaskOut:
    """The same task again, parked in the Backlog of its board. It takes what the task asks for and how it runs
    (description, properties, schedule, agent or workflows, automation guard), and none of what happened to it: no
    attempts or history, no link to the task it follows, and not the working folder it carried on in (a copy starts
    fresh). The Backlog is where a task does not start by itself, so the copy runs when its owner moves it on."""

    return await task_service.duplicate_task(task_id, session, user)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, session: SessionDep, user: CurrentUser) -> TaskOut:
    return await task_queries.get_task(task_id, session, user)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int, body: TaskPatch, request: Request, session: SessionDep, user: CurrentUser
) -> TaskOut:
    return await task_service.update_task(task_id, body, request.app.state, session, user)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, session: SessionDep, user: CurrentUser) -> None:
    return await task_service.delete_task(task_id, session, user)


@router.post("/tasks/{task_id}/run", response_model=TaskOut)
async def run_task_now(task_id: int, request: Request, session: SessionDep, user: CurrentUser) -> TaskOut:
    return await task_service.run_task_now(task_id, request.app.state, session, user)


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(task_id: int, request: Request, session: SessionDep, user: CurrentUser) -> TaskOut:
    return await task_service.cancel_task(task_id, request.app.state, session, user)


@router.get("/tasks/{task_id}/attempts", response_model=list[AttemptOut])
async def list_attempts(
    task_id: int, session: SessionDep, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[Attempt]:
    return await task_queries.list_attempts(task_id, session, user, limit)


@router.get("/attempts/{attempt_id}", response_model=AttemptDetail)
async def get_attempt(attempt_id: int, session: SessionDep, user: CurrentUser) -> AttemptDetail:
    return await task_queries.get_attempt(attempt_id, session, user)


@router.get("/projects/{project_id}/usage", response_model=list[UsageRow])
async def project_usage(
    project_id: int,
    session: SessionDep,
    user: CurrentUser,
    days: Annotated[int, Query(ge=1, le=365, description="Only attempts of the last this many days")] = 7,
) -> list[UsageRow]:
    """What the project's attempts used, per harness and model."""

    return await task_queries.project_usage(project_id, session, user, days)


@router.get("/projects/{project_id}/schedule", response_model=list[ScheduledRun])
async def upcoming_runs(
    project_id: int,
    session: SessionDep,
    user: CurrentUser,
    hours: Annotated[int, Query(ge=1, le=24 * 14)] = 24,
    board_id: int | None = None,
) -> list[ScheduledRun]:
    """What is going to run in the next N hours (one-off and every occurrence of recurring tasks)."""

    return await task_queries.upcoming_runs(project_id, session, user, hours, board_id)
