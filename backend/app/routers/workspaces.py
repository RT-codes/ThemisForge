"""A project's workspaces and boards. The rules live in app/boards.py; this only checks access and speaks HTTP."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import boards as rules
from ..app_settings import load_settings
from ..deps import CurrentUser, SessionDep
from ..models import Board, BoardStatus, Project, TaskStatus, Workspace, utcnow
from ..scheduling import refresh_next_run
from ..schemas import (
    BoardIn,
    BoardOut,
    BoardPatch,
    ColumnOut,
    MoveIn,
    SpawnIn,
    StatusIn,
    StatusPatch,
    TaskOut,
    WorkspaceIn,
    WorkspaceOut,
    WorkspacePatch,
)
from .projects import _project, _task, _task_out

router = APIRouter(tags=["workspaces"])


def _refused(e: rules.BoardError) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT if e.conflict else status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)
    )


async def _workspace(session: AsyncSession, workspace_id: int, user: CurrentUser) -> Workspace:
    workspace = await session.get(Workspace, workspace_id)
    project = await session.get(Project, workspace.project_id) if workspace else None
    if workspace is None or project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


async def _board(session: AsyncSession, board_id: int, user: CurrentUser) -> Board:
    board = await session.get(Board, board_id)
    project = await session.get(Project, board.project_id) if board else None
    if board is None or project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Board not found")
    return board


async def _boards_out(session: AsyncSession, boards: list[Board]) -> list[BoardOut]:
    columns = await rules.columns_for(session, boards)
    counts = await rules.task_counts(session, boards)
    return [
        BoardOut(
            **{f: getattr(b, f) for f in BoardOut.model_fields if f not in ("columns", "task_counts")},
            columns=[ColumnOut(**asdict(c)) for c in columns[b.id]],
            task_counts=counts[b.id],
        )
        for b in boards
    ]


async def _workspaces_out(session: AsyncSession, workspaces: list[Workspace]) -> list[WorkspaceOut]:
    if not workspaces:
        return []
    boards = (
        await session.scalars(
            select(Board)
            .where(Board.workspace_id.in_([w.id for w in workspaces]))
            .order_by(Board.position, Board.id)
        )
    ).all()
    out_by_workspace: dict[int, list[BoardOut]] = {w.id: [] for w in workspaces}
    for board in await _boards_out(session, list(boards)):
        out_by_workspace[board.workspace_id].append(board)
    return [
        WorkspaceOut(
            **{f: getattr(w, f) for f in WorkspaceOut.model_fields if f != "boards"},
            boards=out_by_workspace[w.id],
        )
        for w in workspaces
    ]


async def _destination(session: AsyncSession, project_id: int, move_to: int | None) -> Board | None:
    if move_to is None:
        return None
    try:
        return await rules.project_board(session, project_id, move_to)
    except rules.BoardError as e:
        raise _refused(e) from None


# workspaces


@router.get("/projects/{project_id}/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(project_id: int, session: SessionDep, user: CurrentUser) -> list[WorkspaceOut]:
    await _project(session, project_id, user)
    workspaces = (
        await session.scalars(
            select(Workspace)
            .where(Workspace.project_id == project_id)
            .order_by(Workspace.position, Workspace.id)
        )
    ).all()
    return await _workspaces_out(session, list(workspaces))


@router.post(
    "/projects/{project_id}/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED
)
async def create_workspace(
    project_id: int, body: WorkspaceIn, session: SessionDep, user: CurrentUser
) -> WorkspaceOut:
    await _project(session, project_id, user)
    workspace = await rules.add_workspace(session, project_id, body.name, body.purpose, body.description)
    await session.commit()
    return (await _workspaces_out(session, [workspace]))[0]


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: int, body: WorkspacePatch, session: SessionDep, user: CurrentUser
) -> WorkspaceOut:
    workspace = await _workspace(session, workspace_id, user)
    for field in body.model_fields_set:
        if (value := getattr(body, field)) is not None:
            setattr(workspace, field, value)
    await session.commit()
    return (await _workspaces_out(session, [workspace]))[0]


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: int,
    session: SessionDep,
    user: CurrentUser,
    move_to: Annotated[int | None, Query(description="The board that takes over the tasks")] = None,
) -> None:
    workspace = await _workspace(session, workspace_id, user)
    destination = await _destination(session, workspace.project_id, move_to)
    try:
        await rules.delete_workspace(session, workspace, destination)
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()


# boards


@router.post(
    "/workspaces/{workspace_id}/boards", response_model=BoardOut, status_code=status.HTTP_201_CREATED
)
async def create_board(workspace_id: int, body: BoardIn, session: SessionDep, user: CurrentUser) -> BoardOut:
    workspace = await _workspace(session, workspace_id, user)
    board = await rules.add_board(session, workspace, body.name, body.purpose)
    await session.commit()
    return (await _boards_out(session, [board]))[0]


@router.patch("/boards/{board_id}", response_model=BoardOut)
async def update_board(board_id: int, body: BoardPatch, session: SessionDep, user: CurrentUser) -> BoardOut:
    board = await _board(session, board_id, user)
    fields = body.model_fields_set
    if "name" in fields and body.name is not None:
        board.name = body.name
    if "purpose" in fields and body.purpose is not None:
        board.purpose = body.purpose
    if "workspace_id" in fields and body.workspace_id not in (None, board.workspace_id):
        target = await _workspace(session, body.workspace_id, user)
        if target.project_id != board.project_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That workspace is in another project")
        board.workspace_id = target.id
        board.position = await rules.next_board_position(session, target.id)  # last, unless told otherwise
    if "position" in fields and body.position is not None:
        board.position = body.position
    await session.commit()
    return (await _boards_out(session, [board]))[0]


@router.post("/boards/{board_id}/duplicate", response_model=BoardOut, status_code=status.HTTP_201_CREATED)
async def duplicate_board(board_id: int, session: SessionDep, user: CurrentUser) -> BoardOut:
    """The same board again (name, purpose and statuses); its tasks stay where they are."""
    board = await _board(session, board_id, user)
    copy = await rules.duplicate_board(session, board)
    await session.commit()
    return (await _boards_out(session, [copy]))[0]


@router.delete("/boards/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(
    board_id: int,
    session: SessionDep,
    user: CurrentUser,
    move_to: Annotated[int | None, Query(description="The board that takes over the tasks")] = None,
) -> None:
    board = await _board(session, board_id, user)
    destination = await _destination(session, board.project_id, move_to)
    try:
        await rules.delete_board(session, board, destination)
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()


# custom statuses. They answer with the whole board so the interface can swap in its new columns.


async def _status(session: AsyncSession, board: Board, status_id: int) -> BoardStatus:
    status_row = await session.get(BoardStatus, status_id)
    if status_row is None or status_row.board_id != board.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Status not found")
    return status_row


@router.post("/boards/{board_id}/statuses", response_model=BoardOut, status_code=status.HTTP_201_CREATED)
async def add_status(board_id: int, body: StatusIn, session: SessionDep, user: CurrentUser) -> BoardOut:
    board = await _board(session, board_id, user)
    try:
        await rules.add_status(session, board, body.name, body.color, body.index)
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()
    return (await _boards_out(session, [board]))[0]


@router.patch("/boards/{board_id}/statuses/{status_id}", response_model=BoardOut)
async def update_status(
    board_id: int, status_id: int, body: StatusPatch, session: SessionDep, user: CurrentUser
) -> BoardOut:
    board = await _board(session, board_id, user)
    row = await _status(session, board, status_id)
    try:
        await rules.update_status(
            session,
            board,
            row,
            name=body.name,
            color=body.color,
            set_color="color" in body.model_fields_set,
            index=body.index,
        )
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()
    return (await _boards_out(session, [board]))[0]


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
    board = await _board(session, board_id, user)
    row = await _status(session, board, status_id)
    try:
        await rules.remove_status(session, board, row, move_to)
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()
    return (await _boards_out(session, [board]))[0]


# moving and spawning tasks between boards


@router.post("/tasks/{task_id}/move", response_model=TaskOut)
async def move_task(
    task_id: int, body: MoveIn, request: Request, session: SessionDep, user: CurrentUser
) -> TaskOut:
    """The same task continues on another board (or another status of this one)."""
    task = await _task(session, task_id, user)
    try:
        destination = await rules.project_board(session, task.project_id, body.board_id)
        await rules.move_task(session, task, destination, user.name, body.status, body.position)
    except rules.BoardError as e:
        raise _refused(e) from None
    refresh_next_run(task, (await load_settings(session)).timezone, utcnow())
    await session.commit()
    if task.status == TaskStatus.READY:
        request.app.state.scheduler.wake()
    return (await _task_out(session, [task]))[0]


@router.post("/tasks/{task_id}/spawn", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def spawn_task(
    task_id: int, body: SpawnIn, request: Request, session: SessionDep, user: CurrentUser
) -> TaskOut:
    """A new task on another board, linked to this one. This task stays where it is."""
    origin = await _task(session, task_id, user)
    try:
        destination = await rules.project_board(session, origin.project_id, body.board_id)
        task = await rules.spawn_task(
            session,
            origin,
            destination,
            user.name,
            body.title or f"Follow-up: {origin.title}"[:200],
            body.description,
            body.status,
        )
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()
    return (await _task_out(session, [task]))[0]
