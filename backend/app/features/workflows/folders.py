import asyncio
import os
import re
import shutil
from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.execution.cells.contract import workdir_path
from app.features.agents.skills import MOUNTPOINT_DIRS
from app.features.projects import boards
from app.features.workflows.context import _Ctx
from app.features.workflows.graph import (
    GraphNode,
    NodeError,
)
from app.features.workflows.walk import MergeIn, Outcome, Prev
from app.persistence.models import (
    Attempt,
    AttemptStatus,
    NodeStatus,
    Task,
    TaskStatus,
    utcnow,
)


def _slug(text: str, fallback: str) -> str:
    """A name that is safe and easy to read as a folder name: "Research A" becomes "research-a"."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", text.casefold()).strip("-._")
    return slug[:40] or fallback


def _copy_folder(source: Path, target: Path, only: tuple[str, ...] = ()) -> None:
    """Copy a working folder (or the paths of it that match `only`) to a new place. Blocking: call it from a thread.
    `.agents` and `.claude` are left out: they are only the mountpoint of the agent's skills."""
    target.mkdir(parents=True, exist_ok=True)
    patterns = [p + "/**" if not any(c in p for c in "*?[") and (source / p).is_dir() else p for p in only]
    for base, dirs, files in os.walk(source):
        rel_base = Path(base).relative_to(source)
        dirs[:] = [d for d in dirs if not (rel_base == Path(".") and d in MOUNTPOINT_DIRS)]
        if not patterns:
            (target / rel_base).mkdir(parents=True, exist_ok=True)
        for name in files:
            rel = (rel_base / name).as_posix()
            if patterns and not any(PurePosixPath(rel).full_match(p) for p in patterns):
                continue
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if (source / rel).is_symlink():
                os.symlink(os.readlink(source / rel), dest)
            else:
                shutil.copy2(source / rel, dest)


async def task_workdir(s: AsyncSession, task: Task) -> int | None:
    """The working folder a task worked in last (its latest attempt's), or the one it was made to continue in. A
    workflow started by the task begins there, so steps that ask to continue pick up its files."""
    latest = await s.scalar(
        select(Attempt.workdir_id)
        .where(Attempt.task_id == task.id, Attempt.workdir_id.is_not(None))
        .order_by(Attempt.id.desc())
        .limit(1)
    )
    return latest or (task.run_options or {}).get("workdir") or None


class WorkflowFolders:
    """Branch copies and merges, with the hidden attempts that own their folders."""

    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self.maker = maker

    async def merge(self, ctx: _Ctx, node: GraphNode, inputs: list[MergeIn]) -> Outcome:
        """Waits for its branches (the run only gets here once every one is settled) and carries on with all of them:
        their results in one text, and their working folders side by side, each in a folder named after its branch."""
        c = node.config
        good = [i for i in inputs if i.mark.state == "delivered"]
        bad = [i for i in inputs if i.mark.state == "failed"]
        if bad and (c.get("onFailure") != "continue" or not good):
            names = ", ".join(f"'{i.mark.source}'" for i in bad)
            raise NodeError(
                f"{'Branch' if len(bad) == 1 else 'Branches'} {names} failed, so there is nothing to merge. "
                f"{bad[0].mark.error}".strip()
            )
        taken: set[str] = set()
        sections, folders, lines = [], [], []
        for i in good:
            prev = i.mark.prev
            folder = ""
            if prev and prev.workdir_id:
                base = _slug(i.name, f"branch-{i.number}")
                folder, n = base, 2
                while folder in taken:
                    folder, n = f"{base}-{n}", n + 1
                taken.add(folder)
                folders.append((i, folder))
            text = (prev.result if prev else "").strip()
            heading = f"## {i.name}" + (f" (files in {folder}/)" if folder else "")
            sections.append(f"{heading}\n{text}".rstrip() if text else heading)
            how = "failed, carried on" if prev and prev.status == NodeStatus.FAILED else "arrived"
            lines.append(f"{i.name}: {how}" + (f", files in {folder}/" if folder else ""))
        for i in bad:
            lines.append(f"{i.name}: failed ({i.mark.error}), left out")
        workdir_id = None
        if folders:
            summary = "Combined the work of " + ", ".join(f"{i.name} (in {f}/)" for i, f in folders) + "."
            workdir_id = await self._folder_record(
                ctx, f"{node.label or 'Merger'}: combined folder", summary, [f"{f}/" for _, f in folders]
            )
            target = workdir_path(ctx.project_id, workdir_id)
            try:
                for i, f in folders:
                    source = workdir_path(ctx.project_id, i.mark.prev.workdir_id)
                    if await asyncio.to_thread(source.is_dir):
                        await asyncio.to_thread(_copy_folder, source, target / f, i.mark.prev.only)
            except OSError as e:
                raise NodeError(f"Could not combine the working folders: {e}") from None
        return Outcome(
            NodeStatus.SUCCEEDED,
            result="\n\n".join(sections),
            log="\n".join(lines) + "\n",
            workdir_id=workdir_id,
        )

    async def _folder_record(self, ctx: _Ctx, title: str, result: str, added: list[str] | None = None) -> int:
        """A working folder made by the workflow itself (a branch's copy, a merged folder) has to be named by an
        attempt, like every other one: that is how the scheduler finds it, tells the next agent what is in it, and
        removes it after the retention period. This makes the finished, hidden step that owns it."""
        now = utcnow()
        async with self.maker() as s:
            board = await boards.default_board(s, ctx.project_id)
            task = Task(
                project_id=ctx.project_id, board_id=board.id, title=title[:200], status=TaskStatus.DONE,
                internal=True, position=await boards.next_position(s, board.id, TaskStatus.DONE),
            )  # fmt: skip
            s.add(task)
            await s.flush()
            attempt = Attempt(
                task_id=task.id, status=AttemptStatus.SUCCEEDED, started_at=now, finished_at=now, exit_code=0,
                result=result, changes={"added": added or [], "changed": [], "removed": [], "more": 0},
            )  # fmt: skip
            s.add(attempt)
            await s.flush()
            attempt.workdir_id = attempt.id
            await s.commit()
            return attempt.id

    async def continue_in(self, ctx: _Ctx, node: GraphNode, prev: Prev | None) -> int | None:
        """The working folder a step that asked to continue starts in: the one the step before left, or the run's own.
        When that folder is shared with the sibling branches of a Splitter, the step gets a copy of its own (or just
        the paths its branch was given), so parallel branches never write into the same files."""
        source = prev.workdir_id if prev else ctx.workdir_id
        if not source or prev is None or not prev.fork:
            return source
        folder = workdir_path(ctx.project_id, source)
        if not await asyncio.to_thread(folder.is_dir):
            return source  # gone: the scheduler tells the agent so, as for any folder that was removed
        name = node.label or node.kind.capitalize()
        note = f"A copy of the working folder as it was after '{prev.label}', made for the branch that leads to '{name}'."
        if prev.only:
            note += f" Only {', '.join(prev.only)} was copied."
        copy = await self._folder_record(ctx, f"{name}: copy of the folder", note)
        try:
            await asyncio.to_thread(_copy_folder, folder, workdir_path(ctx.project_id, copy), prev.only)
        except OSError as e:
            raise NodeError(f"Could not copy the working folder for this branch: {e}") from None
        return copy
