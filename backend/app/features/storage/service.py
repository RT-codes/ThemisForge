import asyncio
import contextlib
import os
import shutil
import uuid
from collections.abc import AsyncIterable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

import app.features.project_config.common as config_types
import app.features.project_config.store as project_config
from app.errors import ApplicationError, invalid
from app.features.projects.access import require_project
from app.features.storage.schemas import (
    FolderIn,
    MoveIn,
    VolumeIn,
    VolumeOut,
    VolumePatch,
)
from app.features.storage.volumes import (
    FileError,
    MountError,
    ensure_config_volume,
    ensure_default_volume,
    host_target,
    is_default,
    managed_dir,
    resolve_volume,
    safe_path,
)
from app.features.system.settings import load_settings
from app.persistence.models import Agent, Project, User, Volume
from app.runtime import Runtime

MAX_UPLOAD = 512 * 1024 * 1024  # bytes: a ceiling so one upload cannot fill the disk


async def _out(volume: Volume, cfg) -> VolumeOut:
    out = VolumeOut.model_validate(volume)
    out.is_default = is_default(volume)
    if volume.kind == "host":
        try:
            _, allowed = resolve_volume(volume, cfg)
            out.can_write = allowed
        except MountError as e:
            out.problem, out.can_write = str(e), False
    return out


async def _volume(session, volume_id: int, user) -> tuple[Volume, Project]:
    volume = await session.get(Volume, volume_id)
    if volume is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Folder not found")
    return volume, await require_project(session, volume.project_id, user)


async def list_volumes(
    project_id: int, session: AsyncSession, user: User, include_config: bool = False
) -> list[VolumeOut]:
    """The project's shared folders. Its config folder is not one (it can never be mounted), so only the Files page,
    which shows it too, asks for it."""
    await require_project(session, project_id, user)
    await ensure_default_volume(session, project_id)
    if include_config:
        await ensure_config_volume(session, project_id)
    volumes = (
        await session.scalars(
            select(Volume).where(Volume.project_id == project_id, Volume.kind != "config")
            if not include_config
            else select(Volume).where(Volume.project_id == project_id)
        )
    ).all()
    cfg = await load_settings(session)
    out = [await _out(v, cfg) for v in volumes]
    return sorted(out, key=lambda v: (v.kind == "config", not v.is_default, v.name))


async def get_config_folder(project_id: int, session: AsyncSession, user: User) -> VolumeOut:
    """The folder where the project's agents, skills and tools are kept (see app/project_config.py)."""
    await require_project(session, project_id, user)
    project_config.ensure_layout(project_id)
    return await _out(await ensure_config_volume(session, project_id), await load_settings(session))


async def create_volume(project_id: int, body: VolumeIn, session: AsyncSession, user: User) -> VolumeOut:
    await require_project(session, project_id, user)
    cfg = await load_settings(session)
    host_path, exclusive = "", body.exclusive_write
    if body.kind == "host":
        try:
            real, allowed = host_target(body.host_path.strip(), cfg.mount_roots)
        except MountError as e:
            raise invalid(str(e)) from None
        if body.mode == "rw" and not allowed:
            raise invalid(
                "Cells may only read in that folder. An administrator can allow writing in Settings."
            )
        host_path = str(real)
        if exclusive is None:
            exclusive = body.mode == "rw"
    volume = Volume(
        project_id=project_id,
        name=body.name,
        kind=body.kind,
        host_path=host_path,
        mode=body.mode,
        exclusive_write=bool(exclusive),
    )
    session.add(volume)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ApplicationError(
            status.HTTP_409_CONFLICT, "This project already has a folder with that name"
        ) from None
    if volume.kind == "managed":
        managed_dir(project_id, volume.name).mkdir(parents=True, exist_ok=True)
    return await _out(volume, cfg)


def _check_rename(volume: Volume, new: str, siblings: list[str], runtime: Runtime) -> None:
    """Why this folder cannot be renamed right now, as a message. Everything that points at a folder (agent mounts,
    workflow Folder nodes) uses its id, so a rename never breaks those; the name is only what cells see at
    /workspace/NAME and, for a managed folder, where it lives on disk."""
    if is_default(volume):
        raise ApplicationError(
            status.HTTP_409_CONFLICT, "The shared folder keeps its name: every cell expects it"
        )
    if new in siblings:
        raise ApplicationError(status.HTTP_409_CONFLICT, "This project already has a folder with that name")
    if runs := runtime.scheduler.runs_using(volume.id):
        # a running cell was told the old name in its prompt, and a starting one has already chosen its mounts
        raise ApplicationError(status.HTTP_409_CONFLICT, _in_use(runs, "Rename it"))


async def update_volume(
    volume_id: int, body: VolumePatch, runtime: Runtime, session: AsyncSession, user: User
) -> VolumeOut:
    volume, _ = await _volume(session, volume_id, user)
    if volume.kind == "config":
        raise ApplicationError(status.HTTP_409_CONFLICT, "The config folder keeps its settings")
    cfg = await load_settings(session)
    if body.mode is not None and body.mode != volume.mode:
        if body.mode == "rw" and volume.kind == "host":
            try:
                _, allowed = resolve_volume(volume, cfg)
            except MountError as e:
                raise invalid(str(e)) from None
            if not allowed:
                raise invalid(
                    "Cells may only read in that folder. An administrator can allow writing in Settings."
                )
        volume.mode = body.mode
    if body.exclusive_write is not None:
        volume.exclusive_write = body.exclusive_write

    renaming = body.name is not None and body.name != volume.name
    # the directory moves and the database follows: no run may start on this folder in between (see Scheduler.renaming)
    with runtime.scheduler.renaming(volume.id) if renaming else contextlib.nullcontext():
        old_dir = new_dir = None
        if renaming:
            siblings = list(
                await session.scalars(
                    select(Volume.name).where(Volume.project_id == volume.project_id, Volume.id != volume.id)
                )
            )
            _check_rename(volume, body.name, siblings, runtime)
            if volume.kind == "managed":
                old_dir, new_dir = (
                    managed_dir(volume.project_id, volume.name),
                    managed_dir(volume.project_id, body.name),
                )
                if new_dir.exists():
                    # removing a folder from a project keeps its files, so an old folder of that name may still be there
                    raise ApplicationError(
                        status.HTTP_409_CONFLICT,
                        "A folder with that name still exists on disk from an earlier one",
                    )
                if old_dir.is_dir():
                    old_dir.rename(new_dir)
                else:
                    old_dir = None  # never made on disk yet: nothing to move
            volume.name = body.name
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if old_dir is not None and new_dir is not None:
                new_dir.rename(old_dir)  # the database refused, so the files go back where they were
            raise ApplicationError(
                status.HTTP_409_CONFLICT, "This project already has a folder with that name"
            ) from None
        # BaseException on purpose: a cancelled request must not leave the files renamed
        except BaseException:
            if old_dir is not None and new_dir is not None:
                new_dir.rename(old_dir)
            raise
    return await _out(volume, cfg)


async def delete_volume(volume_id: int, session: AsyncSession, user: User) -> None:
    """Removes the folder from the project. Its files stay on disk; nothing is deleted."""
    volume, project = await _volume(session, volume_id, user)
    if is_default(volume) or volume.kind == "config":
        raise ApplicationError(status.HTTP_409_CONFLICT, "Every project keeps its shared and config folders")
    async with project_config.lock:
        changed = []
        for agent in await session.scalars(select(Agent).where(Agent.project_id == project.id)):
            kept = [m for m in agent.mounts if m.get("volume_id") != volume.id]
            if len(kept) != len(agent.mounts):
                agent.mounts = kept
                changed.append(agent)
        await session.delete(volume)
        await session.flush()
        await project_config.rewrite_agents(session, changed)  # their files name the folders they mount
        await session.commit()


def _in_use(runs: list[tuple[int, str]], what: str) -> str:
    who = ", ".join(f"task {task_id} ({title})" for task_id, title in runs[:2]) + (
        " and more" if len(runs) > 2 else ""
    )
    return f"A run is using this folder right now: {who}. {what} when it finishes"


async def volume_root(session, volume_id: int, user) -> tuple[Path, bool, Volume]:
    """The volume's real folder and whether it can be written to, after checking the person owns the project. The Files
    page and the MCP control plane both read through this, so a folder is resolved the same way for each."""
    volume, _ = await _volume(session, volume_id, user)
    cfg = await load_settings(session)
    try:
        root, allowed = resolve_volume(volume, cfg)
    except MountError as e:
        raise ApplicationError(status.HTTP_409_CONFLICT, str(e)) from None
    if volume.kind == "managed":
        root.mkdir(
            parents=True, exist_ok=True
        )  # `shared` exists in the database before any cell made its folder
    if volume.kind == "config":
        project_config.ensure_layout(volume.project_id)
    return root, allowed, volume


async def _root(runtime: Runtime, session, volume_id: int, user, *, write: bool = False):
    """`volume_root`, plus (for changes) the check that the folder can be written to and no run is using it. Problems
    come back as plain messages."""
    root, allowed, volume = await volume_root(session, volume_id, user)
    runs = runtime.scheduler.runs_using(volume.id)  # never any for the config folder: it is not mounted
    writable = volume.mode == "rw" and allowed
    if write:
        if not writable:
            raise ApplicationError(status.HTTP_403_FORBIDDEN, "This folder is read only")
        if runs:
            raise ApplicationError(status.HTTP_409_CONFLICT, _in_use(runs, "Changes wait"))
    return root, writable, runs, volume


def _rel(root: Path, target: Path) -> str:
    return target.relative_to(root.resolve()).as_posix()


async def _check_config(session, volume: Volume, rel: str, file: Path, user) -> None:
    """A file in the config folder is checked before it is saved: one that could not work is refused with a reason."""
    if volume.kind == "config" and project_config.is_validated(rel):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            await project_config.validate_write(session, volume.project_id, rel, text, user)
        except config_types.ConfigError as e:
            raise invalid(str(e)) from None


async def _config_changed(session, volume: Volume) -> None:
    """After a change in the config folder the agent and tool rows follow their files."""
    if volume.kind == "config":
        await project_config.sync_project(session, volume.project_id)


def _safe(root: Path, rel: str, *, follow_leaf: bool = True) -> Path:
    try:
        return safe_path(root, rel, follow_leaf=follow_leaf)
    except FileError as e:
        raise invalid(str(e)) from None


async def save_file(
    runtime: Runtime,
    session,
    volume_id: int,
    user,
    path: str,
    chunks: AsyncIterable[bytes],
    overwrite: bool = False,
    base: datetime | None = None,
) -> None:
    """Writes `chunks` as the file at `path` of a folder, with every rule of a save in the Files page. The web upload
    streams its request body in; the MCP control plane gives the text an agent wrote."""
    root, _, _, volume = await _root(runtime, session, volume_id, user, write=True)
    target = _safe(root, path, follow_leaf=False)
    if target == root or target.is_dir():
        raise invalid("Choose a file name")
    if target.exists() and not overwrite:
        raise ApplicationError(status.HTTP_409_CONFLICT, "A file with that name already exists")
    if base is not None and target.is_file():
        seen = base if base.tzinfo else base.replace(tzinfo=UTC)
        if abs((datetime.fromtimestamp(target.stat().st_mtime, UTC) - seen).total_seconds()) > 0.001:
            raise ApplicationError(
                status.HTTP_412_PRECONDITION_FAILED, "This file changed since you opened it"
            )
    if not target.parent.is_dir():
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Folder not found")
    # written beside the target and renamed into place, so a cell never reads a half written file
    partial = target.parent / f".{target.name}.{uuid.uuid4().hex}.part"
    size = 0
    try:
        with partial.open("wb") as f:
            async for chunk in chunks:
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise invalid(f"Files up to {MAX_UPLOAD // 2**20} MB can be uploaded")
                f.write(chunk)
        await _check_config(session, volume, _rel(root, target), partial, user)
        if target.is_file():
            shutil.copymode(target, partial)  # editing a script must not take its executable bit away
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    await _config_changed(session, volume)


async def create_folder(
    volume_id: int, body: FolderIn, runtime: Runtime, session: AsyncSession, user: User
) -> None:
    root, _, _, volume = await _root(runtime, session, volume_id, user, write=True)
    target = _safe(root, body.path, follow_leaf=False)
    if target.exists():
        raise ApplicationError(status.HTTP_409_CONFLICT, "Something with that name already exists")
    if not target.parent.is_dir():
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Folder not found")
    target.mkdir()
    await _config_changed(session, volume)


async def move_file(
    volume_id: int, body: MoveIn, runtime: Runtime, session: AsyncSession, user: User
) -> None:
    """Renames or moves a file or folder within the same volume."""
    root, _, _, volume = await _root(runtime, session, volume_id, user, write=True)
    source = _safe(root, body.source, follow_leaf=False)
    destination = _safe(root, body.destination, follow_leaf=False)
    if source == root or not os.path.lexists(source):
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "File not found")
    if destination == root or os.path.lexists(destination):
        raise ApplicationError(status.HTTP_409_CONFLICT, "Something with that name already exists")
    if source in destination.parents:
        raise invalid("A folder cannot be moved into itself")
    if not destination.parent.is_dir():
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Folder not found")
    if volume.kind == "config" and (
        project_config.is_layout_folder(_rel(root, source))
        or project_config.is_layout_folder(_rel(root, destination))
    ):
        raise invalid("agents, skills and mcp are Themis's own folders: they keep their names")
    os.rename(source, destination)
    await _config_changed(session, volume)


async def delete_file(volume_id: int, runtime: Runtime, session: AsyncSession, user: User, path: str) -> None:
    """Deletes a file, or a folder with everything in it. There is no undo."""
    root, _, _, volume = await _root(runtime, session, volume_id, user, write=True)
    target = _safe(root, path, follow_leaf=False)
    if target == root:
        raise invalid("The folder itself cannot be deleted here")
    if not os.path.lexists(target):
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "File not found")
    if volume.kind == "config" and project_config.is_layout_folder(_rel(root, target)):
        raise invalid("agents, skills and mcp are Themis's own folders: they cannot be deleted")
    if target.is_dir() and not target.is_symlink():
        await asyncio.to_thread(shutil.rmtree, target)
    else:
        target.unlink()
    await _config_changed(session, volume)
