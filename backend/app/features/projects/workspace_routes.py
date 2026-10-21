from typing import Annotated

from fastapi import APIRouter, Query, Request, status

import app.features.projects.workspaces as operations
from app.api.dependencies import CurrentUser, SessionDep
from app.features.projects.schemas import (
    BoardIn,
    BoardOut,
    BoardPatch,
    HaltIn,
    StatusIn,
    StatusPatch,
    WorkspaceIn,
    WorkspaceOut,
    WorkspacePatch,
)
from app.features.tasks.schemas import MoveIn, SpawnIn, TaskOut

router = APIRouter(tags=["workspaces"])


@router.get("/projects/{project_id}/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(project_id: int, session: SessionDep, user: CurrentUser) -> list[WorkspaceOut]:
    return await operations.list_workspaces(project_id, session, user)


@router.post(
    "/projects/{project_id}/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED
)
async def create_workspace(
    project_id: int, body: WorkspaceIn, session: SessionDep, user: CurrentUser
) -> WorkspaceOut:
    return await operations.create_workspace(project_id, body, session, user)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: int, body: WorkspacePatch, session: SessionDep, user: CurrentUser
) -> WorkspaceOut:
    return await operations.update_workspace(workspace_id, body, session, user)


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: int,
    session: SessionDep,
    user: CurrentUser,
    move_to: Annotated[int | None, Query(description="The board that takes over the tasks")] = None,
) -> None:
    return await operations.delete_workspace(workspace_id, session, user, move_to)


@router.post(
    "/workspaces/{workspace_id}/boards", response_model=BoardOut, status_code=status.HTTP_201_CREATED
)
async def create_board(workspace_id: int, body: BoardIn, session: SessionDep, user: CurrentUser) -> BoardOut:
    return await operations.create_board(workspace_id, body, session, user)


@router.patch("/boards/{board_id}", response_model=BoardOut)
async def update_board(board_id: int, body: BoardPatch, session: SessionDep, user: CurrentUser) -> BoardOut:
    return await operations.update_board(board_id, body, session, user)


@router.post("/boards/{board_id}/halt", response_model=BoardOut)
async def halt_board(
    board_id: int, body: HaltIn, request: Request, session: SessionDep, user: CurrentUser
) -> BoardOut:
    """Nothing on the board starts until it is resumed; by default what is running on it is stopped too."""

    return await operations.halt_board(board_id, body, request.app.state, session, user)


@router.post("/boards/{board_id}/resume", response_model=BoardOut)
async def resume_board(board_id: int, request: Request, session: SessionDep, user: CurrentUser) -> BoardOut:
    return await operations.resume_board(board_id, request.app.state, session, user)


@router.post("/boards/{board_id}/duplicate", response_model=BoardOut, status_code=status.HTTP_201_CREATED)
async def duplicate_board(board_id: int, session: SessionDep, user: CurrentUser) -> BoardOut:
    """The same board again (name, purpose and statuses); its tasks stay where they are."""

    return await operations.duplicate_board(board_id, session, user)


@router.delete("/boards/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(
    board_id: int,
    session: SessionDep,
    user: CurrentUser,
    move_to: Annotated[int | None, Query(description="The board that takes over the tasks")] = None,
) -> None:
    return await operations.delete_board(board_id, session, user, move_to)


@router.post("/boards/{board_id}/statuses", response_model=BoardOut, status_code=status.HTTP_201_CREATED)
async def add_status(board_id: int, body: StatusIn, session: SessionDep, user: CurrentUser) -> BoardOut:
    return await operations.add_status(board_id, body, session, user)


@router.patch("/boards/{board_id}/statuses/{status_id}", response_model=BoardOut)
async def update_status(
    board_id: int, status_id: int, body: StatusPatch, session: SessionDep, user: CurrentUser
) -> BoardOut:
    return await operations.update_status(board_id, status_id, body, session, user)


@router.delete("/boards/{board_id}/statuses/{status_id}", response_model=BoardOut)
async def remove_status(
    board_id: int,
    status_id: int,
    session: SessionDep,
    user: CurrentUser,
    move_to: Annotated[
        str | None, Query(description="The status that takes over its tasks (default Backlog)")
    ] = None,
) -> BoardOut:
    return await operations.remove_status(board_id, status_id, session, user, move_to)


@router.post("/tasks/{task_id}/move", response_model=TaskOut)
async def move_task(
    task_id: int, body: MoveIn, request: Request, session: SessionDep, user: CurrentUser
) -> TaskOut:
    """The same task continues on another board (or another status of this one)."""

    return await operations.move_task(task_id, body, request.app.state, session, user)


@router.post("/tasks/{task_id}/spawn", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def spawn_task(
    task_id: int, body: SpawnIn, request: Request, session: SessionDep, user: CurrentUser
) -> TaskOut:
    """A new task on another board, linked to this one. This task stays where it is."""

    return await operations.spawn_task(task_id, body, request.app.state, session, user)
