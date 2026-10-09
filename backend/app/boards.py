"""Workspaces and boards: the one home for the rules about where a task lives.

A project holds workspaces, a workspace holds boards, a task lives on exactly one board. Workspaces and boards are
organisation only: tasks, attempts, the scheduler and the cell budget stay project-wide, and a board never changes how a
task runs. Every project always has at least one board (the first one is the "default board" that new tasks, and tasks
made by workflows, land on).

The routers and the workflow runner go through here instead of querying boards themselves.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Board, Task, TaskStatus, Workspace

DEFAULT_WORKSPACE_NAME = "Main"
DEFAULT_BOARD_NAME = "Tasks"


# The built-in statuses are the same on every board and cannot be changed. Their names live here so the API can hand a
# board's columns to the interface in one list.
BUILTIN_NAMES = {s.value: s.value.capitalize() for s in TaskStatus}


@dataclass(frozen=True)
class Column:
    key: str  # a built-in value ("ready") or "custom:<id>"
    name: str
    builtin: bool
    color: str | None = None


class BoardError(Exception):
    """A rule about boards was broken. `conflict` means "the request is fine but the state forbids it" (409), as
    opposed to a request that cannot be right (422)."""

    def __init__(self, message: str, conflict: bool = False) -> None:
        super().__init__(message)
        self.conflict = conflict


# creating and finding


async def _next_workspace_position(session: AsyncSession, project_id: int) -> float:
    top = await session.scalar(select(func.max(Workspace.position)).where(Workspace.project_id == project_id))
    return (top or 0.0) + 1.0


async def next_board_position(session: AsyncSession, workspace_id: int) -> float:
    top = await session.scalar(select(func.max(Board.position)).where(Board.workspace_id == workspace_id))
    return (top or 0.0) + 1.0


async def add_workspace(
    session: AsyncSession, project_id: int, name: str, purpose: str = "", description: str = ""
) -> Workspace:
    workspace = Workspace(
        project_id=project_id,
        name=name,
        purpose=purpose,
        description=description,
        position=await _next_workspace_position(session, project_id),
    )
    session.add(workspace)
    await session.flush()
    return workspace


async def add_board(session: AsyncSession, workspace: Workspace, name: str, purpose: str = "") -> Board:
    board = Board(
        project_id=workspace.project_id,
        workspace_id=workspace.id,
        name=name,
        purpose=purpose,
        position=await next_board_position(session, workspace.id),
    )
    session.add(board)
    await session.flush()
    return board


async def create_defaults(session: AsyncSession, project_id: int) -> Board:
    """The workspace and board every new project starts with (existing projects got theirs from a migration)."""
    workspace = await add_workspace(session, project_id, DEFAULT_WORKSPACE_NAME)
    return await add_board(session, workspace, DEFAULT_BOARD_NAME)


async def default_board(session: AsyncSession, project_id: int) -> Board:
    """The project's first board: first workspace, first board in it."""
    board = await session.scalar(
        select(Board)
        .join(Workspace, Workspace.id == Board.workspace_id)
        .where(Board.project_id == project_id)
        .order_by(Workspace.position, Workspace.id, Board.position, Board.id)
        .limit(1)
    )
    if board is None:  # cannot happen: a project always keeps a board
        raise BoardError("This project has no board", conflict=True)
    return board


async def project_board(session: AsyncSession, project_id: int, board_id: int) -> Board:
    """A board of this project; one of another project is reported as not found, never revealed."""
    board = await session.get(Board, board_id)
    if board is None or board.project_id != project_id:
        raise BoardError("That board does not exist in this project")
    return board


async def columns_for(session: AsyncSession, boards: list[Board]) -> dict[int, list[Column]]:
    """The columns of each board, left to right."""
    return {b.id: [Column(key, BUILTIN_NAMES[key], builtin=True) for key in b.columns] for b in boards}


# where tasks sit inside a board


async def next_position(session: AsyncSession, board_id: int, status: str) -> float:
    """Below the last card of a column; a card dropped on a column lands there."""
    top = await session.scalar(
        select(func.max(Task.position)).where(Task.board_id == board_id, Task.status == status)
    )
    return (top or 0.0) + 1.0


async def _move_tasks(session: AsyncSession, tasks: list[Task], destination: Board) -> None:
    """Put tasks on another board, each column's cards below what is already there in the same order as before."""
    for task in sorted(tasks, key=lambda t: (t.status, t.position, t.id)):
        task.position = await next_position(session, destination.id, task.status)
        task.board_id = destination.id
        await session.flush()  # the next card of this column must see this one


async def _tasks_of(session: AsyncSession, *board_ids: int) -> list[Task]:
    return list(await session.scalars(select(Task).where(Task.board_id.in_(board_ids))))


# deleting


async def _hand_over(
    session: AsyncSession, leaving: list[int], project_id: int, move_to: Board | None
) -> None:
    """Make deleting these boards safe: the project keeps a board, nothing running is lost, other tasks move on."""
    others = await session.scalar(
        select(func.count()).where(Board.project_id == project_id, Board.id.not_in(leaving))
    )
    if not others:
        raise BoardError("A project needs at least one board", conflict=True)
    tasks = await _tasks_of(session, *leaving)
    if any(t.status == TaskStatus.RUNNING for t in tasks):
        raise BoardError("A task here is running. Cancel it first.", conflict=True)
    if not tasks:
        return
    if move_to is None or move_to.id in leaving:
        raise BoardError(f"Choose a board for the {len(tasks)} task(s) on it", conflict=True)
    await _move_tasks(session, tasks, move_to)


async def delete_board(session: AsyncSession, board: Board, move_to: Board | None) -> None:
    await _hand_over(session, [board.id], board.project_id, move_to)
    await session.delete(board)


async def delete_workspace(session: AsyncSession, workspace: Workspace, move_to: Board | None) -> None:
    board_ids = list(await session.scalars(select(Board.id).where(Board.workspace_id == workspace.id)))
    if board_ids:
        await _hand_over(session, board_ids, workspace.project_id, move_to)
    else:
        others = await session.scalar(
            select(func.count()).where(
                Workspace.project_id == workspace.project_id, Workspace.id != workspace.id
            )
        )
        if not others:
            raise BoardError("A project needs at least one workspace", conflict=True)
    await session.delete(workspace)
