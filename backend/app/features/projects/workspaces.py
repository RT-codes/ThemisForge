from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

import app.features.projects.boards as rules
from app.errors import ApplicationError
from app.features.projects import halt
from app.features.projects.access import require_project
from app.features.projects.schemas import (
    BoardIn,
    BoardOut,
    BoardPatch,
    ColumnOut,
    HaltIn,
    StatusIn,
    StatusPatch,
    WorkspaceIn,
    WorkspaceOut,
    WorkspacePatch,
)
from app.features.system.settings import load_settings
from app.features.tasks.access import require_task
from app.features.tasks.queries import _task_out
from app.features.tasks.scheduling import refresh_next_run
from app.features.tasks.schemas import MoveIn, SpawnIn, TaskOut
from app.persistence.models import Board, BoardStatus, Project, TaskStatus, User, Workspace, utcnow
from app.runtime import Runtime


def _refused(e: rules.BoardError) -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT if e.conflict else status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)
    )


async def _workspace(session: AsyncSession, workspace_id: int, user: User) -> Workspace:
    workspace = await session.get(Workspace, workspace_id)
    project = await session.get(Project, workspace.project_id) if workspace else None
    if workspace is None or project is None or project.owner_id != user.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


async def _board(session: AsyncSession, board_id: int, user: User) -> Board:
    board = await session.get(Board, board_id)
    project = await session.get(Project, board.project_id) if board else None
    if board is None or project is None or project.owner_id != user.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Board not found")
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


async def list_workspaces(project_id: int, session: AsyncSession, user: User) -> list[WorkspaceOut]:
    await require_project(session, project_id, user)
    workspaces = (
        await session.scalars(
            select(Workspace)
            .where(Workspace.project_id == project_id)
            .order_by(Workspace.position, Workspace.id)
        )
    ).all()
    return await _workspaces_out(session, list(workspaces))


async def create_workspace(
    project_id: int, body: WorkspaceIn, session: AsyncSession, user: User
) -> WorkspaceOut:
    await require_project(session, project_id, user)
    workspace = await rules.add_workspace(
        session, project_id, body.name, body.purpose, body.description, user.name, body.icon
    )
    await session.commit()
    return (await _workspaces_out(session, [workspace]))[0]


async def update_workspace(
    workspace_id: int, body: WorkspacePatch, session: AsyncSession, user: User
) -> WorkspaceOut:
    workspace = await _workspace(session, workspace_id, user)
    if body.name is not None and body.name != workspace.name:
        rules.record(
            session, "workspace_renamed", workspace.project_id, body.name, user.name,
            workspace_id=workspace.id, data={"was": workspace.name},
        )  # fmt: skip
    for field in body.model_fields_set:
        if (value := getattr(body, field)) is not None:
            setattr(workspace, field, value)
    await session.commit()
    return (await _workspaces_out(session, [workspace]))[0]


async def delete_workspace(
    workspace_id: int,
    session: AsyncSession,
    user: User,
    move_to: int | None = None,
) -> None:
    workspace = await _workspace(session, workspace_id, user)
    destination = await _destination(session, workspace.project_id, move_to)
    try:
        await rules.delete_workspace(session, workspace, destination, user.name)
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()


async def create_board(workspace_id: int, body: BoardIn, session: AsyncSession, user: User) -> BoardOut:
    workspace = await _workspace(session, workspace_id, user)
    board = await rules.add_board(session, workspace, body.name, body.purpose, user.name)
    await session.commit()
    return (await _boards_out(session, [board]))[0]


async def update_board(board_id: int, body: BoardPatch, session: AsyncSession, user: User) -> BoardOut:
    board = await _board(session, board_id, user)
    fields = body.model_fields_set
    if "name" in fields and body.name is not None:
        if body.name != board.name:
            rules.record(
                session, "board_renamed", board.project_id, body.name, user.name,
                workspace_id=board.workspace_id, board_id=board.id, data={"was": board.name},
            )  # fmt: skip
        board.name = body.name
    if "purpose" in fields and body.purpose is not None:
        board.purpose = body.purpose
    if "workspace_id" in fields and body.workspace_id not in (None, board.workspace_id):
        target = await _workspace(session, body.workspace_id, user)
        if target.project_id != board.project_id:
            raise ApplicationError(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "That workspace is in another project"
            )
        board.workspace_id = target.id
        board.position = await rules.next_board_position(session, target.id)  # last, unless told otherwise
    if "position" in fields and body.position is not None:
        board.position = body.position
    await session.commit()
    return (await _boards_out(session, [board]))[0]


async def halt_board(
    board_id: int, body: HaltIn, runtime: Runtime, session: AsyncSession, user: User
) -> BoardOut:
    """Nothing on the board starts until it is resumed; by default what is running on it is stopped too."""
    board = await _board(session, board_id, user)
    project = await session.get_one(Project, board.project_id)
    await halt.halt(
        session, runtime.scheduler, project, board, stop_running=body.stop_running, actor=user.name
    )
    await session.refresh(board)
    return (await _boards_out(session, [board]))[0]


async def resume_board(board_id: int, runtime: Runtime, session: AsyncSession, user: User) -> BoardOut:
    board = await _board(session, board_id, user)
    project = await session.get_one(Project, board.project_id)
    await halt.resume(session, runtime.scheduler, project, board, user.name)
    await session.refresh(board)
    return (await _boards_out(session, [board]))[0]


async def duplicate_board(board_id: int, session: AsyncSession, user: User) -> BoardOut:
    """The same board again (name, purpose and statuses); its tasks stay where they are."""
    board = await _board(session, board_id, user)
    copy = await rules.duplicate_board(session, board, user.name)
    await session.commit()
    return (await _boards_out(session, [copy]))[0]


async def delete_board(
    board_id: int,
    session: AsyncSession,
    user: User,
    move_to: int | None = None,
) -> None:
    board = await _board(session, board_id, user)
    destination = await _destination(session, board.project_id, move_to)
    try:
        await rules.delete_board(session, board, destination, user.name)
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()


async def _status(session: AsyncSession, board: Board, status_id: int) -> BoardStatus:
    status_row = await session.get(BoardStatus, status_id)
    if status_row is None or status_row.board_id != board.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Status not found")
    return status_row


async def add_status(board_id: int, body: StatusIn, session: AsyncSession, user: User) -> BoardOut:
    board = await _board(session, board_id, user)
    try:
        await rules.add_status(
            session,
            board,
            body.name,
            body.color,
            body.index,
            user.name,
            icon=body.icon,
            description=body.description,
        )
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()
    return (await _boards_out(session, [board]))[0]


async def update_status(
    board_id: int, status_id: int, body: StatusPatch, session: AsyncSession, user: User
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
            icon=body.icon,
            description=body.description,
            actor=user.name,
        )
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()
    return (await _boards_out(session, [board]))[0]


async def remove_status(
    board_id: int,
    status_id: int,
    session: AsyncSession,
    user: User,
    move_to: str | None = None,
) -> BoardOut:
    board = await _board(session, board_id, user)
    row = await _status(session, board, status_id)
    try:
        await rules.remove_status(session, board, row, move_to, user.name)
    except rules.BoardError as e:
        raise _refused(e) from None
    await session.commit()
    return (await _boards_out(session, [board]))[0]


async def move_task(
    task_id: int, body: MoveIn, runtime: Runtime, session: AsyncSession, user: User
) -> TaskOut:
    """The same task continues on another board (or another status of this one)."""
    task = await require_task(session, task_id, user)
    try:
        destination = await rules.project_board(session, task.project_id, body.board_id)
        await rules.move_task(session, task, destination, user.name, body.status, body.position)
    except rules.BoardError as e:
        raise _refused(e) from None
    task.hops = 0  # a person sent it: automation counts again from nothing
    refresh_next_run(task, (await load_settings(session)).timezone, utcnow())
    await session.commit()
    if task.status == TaskStatus.READY:
        runtime.scheduler.wake()
    return (await _task_out(session, [task]))[0]


async def spawn_task(
    task_id: int, body: SpawnIn, runtime: Runtime, session: AsyncSession, user: User
) -> TaskOut:
    """A new task on another board, linked to this one. This task stays where it is."""
    origin = await require_task(session, task_id, user)
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
