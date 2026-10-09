"""Workspaces, boards and their statuses: the one home for the rules about where a task lives.

A project holds workspaces, a workspace holds boards, a task lives on exactly one board. Workspaces and boards are
organisation only: tasks, attempts, the scheduler and the cell budget stay project-wide, and a board never changes how a
task runs. Every project always has at least one board (the first one is the "default board" that new tasks, and tasks
made by workflows, land on).

Every board has the seven built-in statuses (TaskStatus), locked and in a fixed order, and may add custom ones
(BoardStatus) around them. `Board.columns` is the list of keys left to right and is the single source of truth for
which statuses a board accepts. A custom status is a parking column: the scheduler only acts on Ready and Running, so a
task there waits until someone, or a workflow, moves it on.

The routers and the workflow runner go through here instead of querying boards themselves.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Board, BoardStatus, ProjectEvent, Task, TaskStatus, Workspace

DEFAULT_WORKSPACE_NAME = "Main"
DEFAULT_BOARD_NAME = "Tasks"
DEFAULT_STATUS_ICON = "box"  # what a new custom status shows until its owner picks another
MAX_CUSTOM_STATUSES = 20  # per board: a board with more columns than that stops being readable
CUSTOM_PREFIX = "custom:"


# The built-in statuses are the same on every board and cannot be changed. Their names live here so the API can hand a
# board's columns to the interface in one list.
BUILTIN_NAMES = {s.value: s.value.capitalize() for s in TaskStatus}


def custom_key(status_id: int) -> str:
    return f"{CUSTOM_PREFIX}{status_id}"


def custom_id(key: str) -> int | None:
    """The id behind a "custom:<id>" key; None for anything else."""
    prefix, _, rest = key.partition(":")
    return int(rest) if prefix + ":" == CUSTOM_PREFIX and rest.isdigit() else None


@dataclass(frozen=True)
class Column:
    key: str  # a built-in value ("ready") or "custom:<id>"
    name: str
    builtin: bool
    color: str | None = None
    icon: str = ""  # a custom status's Lucide icon; the built-in ones have theirs in the interface
    description: str = ""  # a custom status's own words about what it is for


def record(
    session: AsyncSession,
    kind: str,
    project_id: int,
    title: str,
    actor: str,
    *,
    workspace_id: int | None = None,
    board_id: int | None = None,
    task_id: int | None = None,
    data: dict | None = None,
    cause: str = "",
) -> None:
    """Add a line to the project's history. It keeps its own copy of the names it mentions: the history outlives the
    tasks, boards and workspaces it is about, so it stores plain numbers and names, never relations."""
    session.add(
        ProjectEvent(
            project_id=project_id,
            kind=kind,
            title=title,
            actor=actor,
            workspace_id=workspace_id,
            board_id=board_id,
            task_id=task_id,
            data=data or {},
            cause=cause,
        )
    )


def record_task(
    session: AsyncSession,
    kind: str,
    task: Task,
    actor: str,
    board: Board | None = None,
    data: dict | None = None,
    cause: str = "",
) -> None:
    record(
        session,
        kind,
        task.project_id,
        task.title,
        actor,
        workspace_id=board.workspace_id if board else None,
        board_id=board.id if board else None,
        task_id=task.id,
        data=data,
        cause=cause,
    )


def place(board: Board, status: str | None = None) -> dict:
    """Where a task is, as stored in an event: the board with its workspace, and the status."""
    return {"workspace_id": board.workspace_id, "board_id": board.id, "board": board.name, "status": status}


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
    session: AsyncSession,
    project_id: int,
    name: str,
    purpose: str = "",
    description: str = "",
    actor: str | None = None,
    icon: str = "",
) -> Workspace:
    """`actor`: who is doing it, for the history. Left out for the workspace a new project starts with."""
    workspace = Workspace(
        project_id=project_id,
        name=name,
        purpose=purpose,
        description=description,
        icon=icon,
        position=await _next_workspace_position(session, project_id),
    )
    session.add(workspace)
    await session.flush()
    if actor:
        record(session, "workspace_created", project_id, name, actor, workspace_id=workspace.id)
    return workspace


async def add_board(
    session: AsyncSession,
    workspace: Workspace,
    name: str,
    purpose: str = "",
    actor: str | None = None,
    data: dict | None = None,
) -> Board:
    board = Board(
        project_id=workspace.project_id,
        workspace_id=workspace.id,
        name=name,
        purpose=purpose,
        position=await next_board_position(session, workspace.id),
    )
    session.add(board)
    await session.flush()
    if actor:
        record(
            session, "board_created", board.project_id, name, actor,
            workspace_id=workspace.id, board_id=board.id, data={"workspace": workspace.name, **(data or {})},
        )  # fmt: skip
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


async def board_for_status(session: AsyncSession, project_id: int, status: str) -> Board:
    """Where a new task with this status goes: a custom status names its board, a built-in one the default board."""
    if (status_id := custom_id(status)) is None:
        return await default_board(session, project_id)
    row = await session.get(BoardStatus, status_id)
    board = await session.get(Board, row.board_id) if row else None
    if board is None or board.project_id != project_id:
        raise BoardError(f"'{status}' is not a status of this project (was it deleted?)")
    return board


async def project_board(session: AsyncSession, project_id: int, board_id: int) -> Board:
    """A board of this project; one of another project is reported as not found, never revealed."""
    board = await session.get(Board, board_id)
    if board is None or board.project_id != project_id:
        raise BoardError("That board does not exist in this project")
    return board


async def columns_for(session: AsyncSession, boards: list[Board]) -> dict[int, list[Column]]:
    """The columns of each board, left to right."""
    custom = {
        custom_key(row.id): row
        for row in await session.scalars(
            select(BoardStatus).where(BoardStatus.board_id.in_([b.id for b in boards]))
        )
    }
    out: dict[int, list[Column]] = {}
    for board in boards:
        out[board.id] = [
            Column(key, BUILTIN_NAMES[key], builtin=True)
            if key in BUILTIN_NAMES
            else Column(
                key,
                custom[key].name,
                builtin=False,
                color=custom[key].color,
                icon=custom[key].icon,
                description=custom[key].description,
            )
            for key in board.columns
            if key in BUILTIN_NAMES or key in custom
        ]
    return out


async def task_counts(session: AsyncSession, boards: list[Board]) -> dict[int, dict[str, int]]:
    """How many tasks each board has per status (a status without tasks is left out)."""
    counts: dict[int, dict[str, int]] = {b.id: {} for b in boards}
    rows = await session.execute(
        select(Task.board_id, Task.status, func.count())
        .where(Task.board_id.in_([b.id for b in boards]))
        .group_by(Task.board_id, Task.status)
    )
    for board_id, status, n in rows:
        counts[board_id][status] = n
    return counts


def check_status(board: Board, status: str) -> None:
    """Refuse a status the board does not have (a custom one of another board, or one that was deleted)."""
    if status not in board.columns:
        raise BoardError(f"'{status}' is not a status of the board '{board.name}'")


async def duplicate_board(session: AsyncSession, board: Board, actor: str) -> Board:
    """A new board in the same workspace with the same purpose and the same custom statuses, in the same places.
    Tasks are not copied: a task is one piece of work, and copying it would make two."""
    copy = await add_board(
        session,
        await session.get_one(Workspace, board.workspace_id),
        f"{board.name} copy",
        board.purpose,
        actor,
        {"copy_of": board.name},
    )
    renamed: dict[str, str] = {}
    for row in await _customs(session, board):
        fresh = BoardStatus(
            board_id=copy.id, name=row.name, color=row.color, icon=row.icon, description=row.description
        )
        session.add(fresh)
        await session.flush()
        renamed[custom_key(row.id)] = custom_key(fresh.id)
    copy.columns = [renamed.get(key, key) for key in board.columns]
    return copy


# where tasks sit inside a board


async def next_position(session: AsyncSession, board_id: int, status: str) -> float:
    """Below the last card of a column; a card dropped on a column lands there."""
    top = await session.scalar(
        select(func.max(Task.position)).where(Task.board_id == board_id, Task.status == status)
    )
    return (top or 0.0) + 1.0


async def _move_tasks(session: AsyncSession, tasks: list[Task], destination: Board) -> None:
    """Put tasks on another board, each column's cards below what is already there in the same order as before. A
    custom status belongs to its own board, so a task that was in one lands in the destination's Backlog."""
    for task in sorted(tasks, key=lambda t: (t.status, t.position, t.id)):
        if task.status not in destination.columns:
            task.status = TaskStatus.BACKLOG
        task.position = await next_position(session, destination.id, task.status)
        task.board_id = destination.id
        await session.flush()  # the next card of this column must see this one


async def _tasks_of(session: AsyncSession, *board_ids: int) -> list[Task]:
    return list(await session.scalars(select(Task).where(Task.board_id.in_(board_ids))))


# deleting


async def _hand_over(
    session: AsyncSession, leaving: list[int], project_id: int, move_to: Board | None
) -> int:
    """Make deleting these boards safe: the project keeps a board, nothing running is lost, other tasks move on.
    Returns how many tasks moved."""
    others = await session.scalar(
        select(func.count()).where(Board.project_id == project_id, Board.id.not_in(leaving))
    )
    if not others:
        raise BoardError("A project needs at least one board", conflict=True)
    tasks = await _tasks_of(session, *leaving)
    if any(t.status == TaskStatus.RUNNING for t in tasks):
        raise BoardError("A task here is running. Cancel it first.", conflict=True)
    if not tasks:
        return 0
    if move_to is None or move_to.id in leaving:
        raise BoardError(f"Choose a board for the {len(tasks)} task(s) on it", conflict=True)
    await _move_tasks(session, tasks, move_to)
    return len(tasks)


async def delete_board(session: AsyncSession, board: Board, move_to: Board | None, actor: str) -> None:
    moved = await _hand_over(session, [board.id], board.project_id, move_to)
    record(
        session, "board_deleted", board.project_id, board.name, actor,
        workspace_id=board.workspace_id, board_id=board.id,
        data={"moved": moved, "to": move_to.name if moved and move_to else None},
    )  # fmt: skip
    await session.delete(board)


async def delete_workspace(
    session: AsyncSession, workspace: Workspace, move_to: Board | None, actor: str
) -> None:
    boards = list(await session.scalars(select(Board).where(Board.workspace_id == workspace.id)))
    moved = 0
    if boards:
        moved = await _hand_over(session, [b.id for b in boards], workspace.project_id, move_to)
    else:
        others = await session.scalar(
            select(func.count()).where(
                Workspace.project_id == workspace.project_id, Workspace.id != workspace.id
            )
        )
        if not others:
            raise BoardError("A project needs at least one workspace", conflict=True)
    record(
        session, "workspace_deleted", workspace.project_id, workspace.name, actor, workspace_id=workspace.id,
        data={"boards": [b.name for b in boards], "moved": moved, "to": move_to.name if moved and move_to else None},
    )  # fmt: skip
    await session.delete(workspace)


# custom statuses


def _status_name(board: Board, name: str, customs: list[BoardStatus], own_id: int | None = None) -> str:
    """A status name is unique on its board, built-in names included (two "Done" columns would be a trap)."""
    name = name.strip()
    if not name:
        raise BoardError("A status needs a name")
    taken = {n.lower() for n in BUILTIN_NAMES.values()} | {c.name.lower() for c in customs if c.id != own_id}
    if name.lower() in taken:
        raise BoardError(f"The board '{board.name}' already has a status called '{name}'")
    return name


async def _customs(session: AsyncSession, board: Board) -> list[BoardStatus]:
    return list(await session.scalars(select(BoardStatus).where(BoardStatus.board_id == board.id)))


def _place(columns: list[str], key: str, index: int | None) -> list[str]:
    """`columns` with `key` at `index` (counted without it; None: at the end). Built-ins keep their order because only
    the custom key moves."""
    rest = [k for k in columns if k != key]
    at = len(rest) if index is None else max(0, min(index, len(rest)))
    return [*rest[:at], key, *rest[at:]]


def _record_status(session: AsyncSession, kind: str, board: Board, name: str, actor: str, **data) -> None:
    record(
        session, kind, board.project_id, name, actor,
        workspace_id=board.workspace_id, board_id=board.id, data={"board": board.name, **data},
    )  # fmt: skip


async def add_status(
    session: AsyncSession,
    board: Board,
    name: str,
    color: str | None,
    index: int | None,
    actor: str,
    *,
    icon: str = DEFAULT_STATUS_ICON,
    description: str = "",
) -> BoardStatus:
    customs = await _customs(session, board)
    if len(customs) >= MAX_CUSTOM_STATUSES:
        raise BoardError(f"A board can have at most {MAX_CUSTOM_STATUSES} custom statuses", conflict=True)
    status = BoardStatus(
        board_id=board.id,
        name=_status_name(board, name, customs),
        color=color,
        icon=icon or DEFAULT_STATUS_ICON,
        description=description.strip(),
    )
    session.add(status)
    await session.flush()  # the id is the key
    board.columns = _place(board.columns, custom_key(status.id), index)
    _record_status(session, "status_added", board, status.name, actor)
    return status


async def update_status(
    session: AsyncSession,
    board: Board,
    status: BoardStatus,
    *,
    name: str | None = None,
    color: str | None = None,
    set_color: bool = False,
    index: int | None = None,
    icon: str | None = None,
    description: str | None = None,
    actor: str = "",
) -> BoardStatus:
    if name is not None:
        new_name = _status_name(board, name, await _customs(session, board), own_id=status.id)
        if new_name != status.name:
            _record_status(session, "status_renamed", board, new_name, actor, was=status.name)
        status.name = new_name
    if set_color:  # separate flag: None is a real value here ("no colour")
        status.color = color
    if icon is not None:
        status.icon = icon or DEFAULT_STATUS_ICON
    if description is not None:
        status.description = description.strip()
    if index is not None:
        board.columns = _place(board.columns, custom_key(status.id), index)
    return status


async def remove_status(
    session: AsyncSession, board: Board, status: BoardStatus, move_to: str | None, actor: str
) -> int:
    """Delete a custom status; its tasks go to `move_to` (a status of the same board, default Backlog). Returns how
    many tasks moved."""
    key = custom_key(status.id)
    destination = move_to or TaskStatus.BACKLOG.value
    if destination == key:
        raise BoardError("Choose another status for its tasks")
    if destination in (TaskStatus.READY, TaskStatus.RUNNING):  # they would start work without being scheduled
        raise BoardError("Its tasks cannot go to a status that starts work. Choose a parking status.")
    check_status(board, destination)
    tasks = list(
        await session.scalars(
            select(Task).where(Task.board_id == board.id, Task.status == key).order_by(Task.position, Task.id)
        )
    )
    for task in tasks:
        task.status = destination
        task.position = await next_position(session, board.id, destination)
        await session.flush()
    board.columns = [k for k in board.columns if k != key]
    _record_status(session, "status_removed", board, status.name, actor, moved=len(tasks), to=destination)
    await session.delete(status)
    return len(tasks)


# moving and spawning: the two ways work gets from one board to another


def _landing_status(destination: Board, status: str | None, current: str | None) -> str:
    """The status a task lands in: the one asked for, else the one it has when the destination also has it (the
    built-in statuses are on every board), else the Backlog."""
    wanted = status or (current if current in destination.columns else TaskStatus.BACKLOG.value)
    if wanted == TaskStatus.RUNNING:
        raise BoardError("Only the scheduler starts tasks. Use Run now.")
    check_status(destination, wanted)
    return wanted


async def move_task(
    session: AsyncSession,
    task: Task,
    destination: Board,
    actor: str,
    status: str | None = None,
    position: float | None = None,
    cause: str = "",
) -> None:
    """The same task continues on another board: same id, attempts, schedule and properties, new place. Callers
    refresh the schedule afterwards (a task that falls back to the Backlog is paused, like any task parked there)."""
    if task.status == TaskStatus.RUNNING:
        raise BoardError("This task is running. Cancel it first.", conflict=True)
    if destination.project_id != task.project_id:
        raise BoardError("That board does not exist in this project")
    source = await session.get_one(Board, task.board_id)
    landing = _landing_status(destination, status, task.status)
    came_from = place(source, task.status)
    was = task.status
    task.board_id = destination.id
    task.status = landing
    task.position = (
        position if position is not None else await next_position(session, destination.id, landing)
    )
    if source.id != destination.id:
        record_task(
            session,
            "task_moved",
            task,
            actor,
            destination,
            {"from": came_from, "to": place(destination, landing)},
            cause,
        )
    elif landing != was:
        record_status_change(session, task, destination, actor, was, cause)


async def spawn_task(
    session: AsyncSession,
    origin: Task,
    destination: Board,
    actor: str,
    title: str,
    description: str,
    status: str | None = None,
    cause: str = "",
    origin_key: str | None = None,
    hops: int = 0,
) -> Task:
    """A new task on another board, linked to the one it follows. It has its own identity and history; it takes the
    origin's property values (they are project wide) but not its schedule or what runs it, which the follow-up's own
    work decides."""
    if destination.project_id != origin.project_id:
        raise BoardError("That board does not exist in this project")
    landing = _landing_status(destination, status, None)
    task = Task(
        project_id=origin.project_id,
        board_id=destination.id,
        title=title,
        description=description,
        status=landing,
        position=await next_position(session, destination.id, landing),
        properties=dict(origin.properties),
        origin_task_id=origin.id,
        origin_key=origin_key,
        hops=hops,
    )
    session.add(task)
    await session.flush()
    origin_board = await session.get_one(Board, origin.board_id)
    record_task(
        session,
        "task_spawned",
        task,
        actor,
        destination,
        {
            "origin": {"task_id": origin.id, "title": origin.title, **place(origin_board)},
            "to": place(destination, landing),
        },
        cause,
    )
    return task


def record_new_task(session: AsyncSession, task: Task, board: Board, actor: str, cause: str = "") -> None:
    record_task(session, "task_created", task, actor, board, {"to": place(board, task.status)}, cause)


def record_status_change(
    session: AsyncSession, task: Task, board: Board, actor: str, was: str, cause: str = ""
) -> None:
    """A person moved a task to another column of its board. Changes the scheduler makes (Running, then the outcome)
    are not recorded: the attempts already say what happened."""
    record_task(
        session,
        "task_status",
        task,
        actor,
        board,
        {"from": {"status": was}, "to": {"status": task.status}},
        cause,
    )
