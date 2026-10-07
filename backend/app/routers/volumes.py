"""Shared folders (volumes) of a project: what cells can mount at /workspace/NAME. See app/volumes.py."""

import asyncio
import contextlib
import hashlib
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import project_config
from ..app_settings import load_settings
from ..deps import CurrentUser, SessionDep
from ..models import Agent, Project, Volume
from ..volumes import (
    NAME,
    FileError,
    MountError,
    ensure_config_volume,
    ensure_default_volume,
    host_target,
    is_default,
    list_dir,
    managed_dir,
    resolve_volume,
    safe_path,
)
from .projects import _bad, _project

router = APIRouter(tags=["volumes"])


def _clean_name(v: str) -> str:
    v = v.strip().lower()
    if not NAME.match(v):
        raise ValueError("Use lowercase letters, digits and dashes, starting with a letter or digit")
    return v


class VolumeIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    kind: Literal["managed", "host"] = "managed"
    host_path: str = Field(default="", max_length=1000)
    mode: Literal["ro", "rw"] = "rw"
    # None: writers take turns on a host folder that cells may write to, and not on a managed one
    exclusive_write: bool | None = None

    _valid_name = field_validator("name")(_clean_name)


class VolumePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    mode: Literal["ro", "rw"] | None = None
    exclusive_write: bool | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str | None) -> str | None:
        return None if v is None else _clean_name(v)


class VolumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    kind: str
    host_path: str
    mode: str
    exclusive_write: bool
    created_at: datetime
    is_default: bool = False  # the `shared` folder every project has: it cannot be removed
    problem: str | None = None  # a host folder that can no longer be mounted, and why
    can_write: bool = True  # False when a host folder's approved root only allows reading


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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
    return volume, await _project(session, volume.project_id, user)


@router.get("/projects/{project_id}/volumes", response_model=list[VolumeOut])
async def list_volumes(
    project_id: int, session: SessionDep, user: CurrentUser, include_config: bool = False
) -> list[VolumeOut]:
    """The project's shared folders. Its config folder is not one (it can never be mounted), so only the Files page,
    which shows it too, asks for it."""
    await _project(session, project_id, user)
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


@router.get("/projects/{project_id}/config", response_model=VolumeOut)
async def get_config_folder(project_id: int, session: SessionDep, user: CurrentUser) -> VolumeOut:
    """The folder where the project's agents, skills and tools are kept (see app/project_config.py)."""
    await _project(session, project_id, user)
    project_config.ensure_layout(project_id)
    return await _out(await ensure_config_volume(session, project_id), await load_settings(session))


@router.post("/projects/{project_id}/volumes", response_model=VolumeOut, status_code=status.HTTP_201_CREATED)
async def create_volume(project_id: int, body: VolumeIn, session: SessionDep, user: CurrentUser) -> VolumeOut:
    await _project(session, project_id, user)
    cfg = await load_settings(session)
    host_path, exclusive = "", body.exclusive_write
    if body.kind == "host":
        try:
            real, allowed = host_target(body.host_path.strip(), cfg.mount_roots)
        except MountError as e:
            raise _bad(str(e)) from None
        if body.mode == "rw" and not allowed:
            raise _bad("Cells may only read in that folder. An administrator can allow writing in Settings.")
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
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This project already has a folder with that name"
        ) from None
    if volume.kind == "managed":
        managed_dir(project_id, volume.name).mkdir(parents=True, exist_ok=True)
    return await _out(volume, cfg)


def _check_rename(volume: Volume, new: str, siblings: list[str], request: Request) -> None:
    """Why this folder cannot be renamed right now, as a message. Everything that points at a folder (agent mounts,
    workflow Folder nodes) uses its id, so a rename never breaks those; the name is only what cells see at
    /workspace/NAME and, for a managed folder, where it lives on disk."""
    if is_default(volume):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The shared folder keeps its name: every cell expects it"
        )
    if new in siblings:
        raise HTTPException(status.HTTP_409_CONFLICT, "This project already has a folder with that name")
    if runs := request.app.state.scheduler.runs_using(volume.id):
        # a running cell was told the old name in its prompt, and a starting one has already chosen its mounts
        raise HTTPException(status.HTTP_409_CONFLICT, _in_use(runs, "Rename it"))


@router.patch("/volumes/{volume_id}", response_model=VolumeOut)
async def update_volume(
    volume_id: int, body: VolumePatch, request: Request, session: SessionDep, user: CurrentUser
) -> VolumeOut:
    volume, _ = await _volume(session, volume_id, user)
    if volume.kind == "config":
        raise HTTPException(status.HTTP_409_CONFLICT, "The config folder keeps its settings")
    cfg = await load_settings(session)
    if body.mode is not None and body.mode != volume.mode:
        if body.mode == "rw" and volume.kind == "host":
            try:
                _, allowed = resolve_volume(volume, cfg)
            except MountError as e:
                raise _bad(str(e)) from None
            if not allowed:
                raise _bad(
                    "Cells may only read in that folder. An administrator can allow writing in Settings."
                )
        volume.mode = body.mode
    if body.exclusive_write is not None:
        volume.exclusive_write = body.exclusive_write

    renaming = body.name is not None and body.name != volume.name
    # the directory moves and the database follows: no run may start on this folder in between (see Scheduler.renaming)
    with request.app.state.scheduler.renaming(volume.id) if renaming else contextlib.nullcontext():
        old_dir = new_dir = None
        if renaming:
            siblings = list(
                await session.scalars(
                    select(Volume.name).where(Volume.project_id == volume.project_id, Volume.id != volume.id)
                )
            )
            _check_rename(volume, body.name, siblings, request)
            if volume.kind == "managed":
                old_dir, new_dir = (
                    managed_dir(volume.project_id, volume.name),
                    managed_dir(volume.project_id, body.name),
                )
                if new_dir.exists():
                    # removing a folder from a project keeps its files, so an old folder of that name may still be there
                    raise HTTPException(
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
            raise HTTPException(
                status.HTTP_409_CONFLICT, "This project already has a folder with that name"
            ) from None
        except Exception:
            if old_dir is not None and new_dir is not None:
                new_dir.rename(old_dir)
            raise
    return await _out(volume, cfg)


@router.delete("/volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_volume(volume_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Removes the folder from the project. Its files stay on disk; nothing is deleted."""
    volume, project = await _volume(session, volume_id, user)
    if is_default(volume) or volume.kind == "config":
        raise HTTPException(status.HTTP_409_CONFLICT, "Every project keeps its shared and config folders")
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


# ----- the files inside a folder (the project's Files page) -----

MAX_UPLOAD = 512 * 1024 * 1024  # bytes: a ceiling so one upload cannot fill the disk
# Shown inline in the browser by extension; everything else is served as plain text (to preview) or as a download.
# Never HTML: a file an agent wrote must not be able to run script on this site's origin. SVG can carry script, so it
# is only allowed together with the sandbox policy below.
INLINE_IMAGES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "avif": "image/avif",
    "bmp": "image/bmp",
    "ico": "image/vnd.microsoft.icon",
    "svg": "image/svg+xml",
}
# Sent with every inline file. In an <img> an SVG never runs script anyway; this covers someone opening the file's
# address directly: the sandbox gives the document an empty origin and blocks scripts.
INLINE_POLICY = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"


class FileEntry(BaseModel):
    name: str
    is_dir: bool
    size: int
    modified: datetime


class RunRef(BaseModel):
    task_id: int
    title: str


class FolderListing(BaseModel):
    path: str  # relative to the volume's root; "" is the root
    entries: list[FileEntry]
    writable: bool  # the folder allows changes: read and write, and the host root allows it
    # The runs that have the folder mounted. While there are any it is locked: nothing can be changed from the page,
    # because an upload, edit, move or delete could break what an agent is in the middle of.
    runs: list[RunRef]


class FolderIn(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


class MoveIn(BaseModel):
    source: str = Field(min_length=1, max_length=1000)
    destination: str = Field(min_length=1, max_length=1000)


def _in_use(runs: list[tuple[int, str]], what: str) -> str:
    who = ", ".join(f"task {task_id} ({title})" for task_id, title in runs[:2]) + (
        " and more" if len(runs) > 2 else ""
    )
    return f"A run is using this folder right now: {who}. {what} when it finishes"


async def _root(request: Request, session, volume_id: int, user, *, write: bool = False):
    """The volume's real folder, after checking the person owns the project and (for changes) that the folder
    can be written to and no run is using it. Problems come back as plain messages."""
    volume, _ = await _volume(session, volume_id, user)
    cfg = await load_settings(session)
    try:
        root, allowed = resolve_volume(volume, cfg)
    except MountError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    if volume.kind == "managed":
        root.mkdir(
            parents=True, exist_ok=True
        )  # `shared` exists in the database before any cell made its folder
    if volume.kind == "config":
        project_config.ensure_layout(volume.project_id)
    runs = request.app.state.scheduler.runs_using(
        volume.id
    )  # never any for the config folder: it is not mounted
    writable = volume.mode == "rw" and allowed
    if write:
        if not writable:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This folder is read only")
        if runs:
            raise HTTPException(status.HTTP_409_CONFLICT, _in_use(runs, "Changes wait"))
    return root, writable, runs, volume


def _rel(root: Path, target: Path) -> str:
    return target.relative_to(root.resolve()).as_posix()


async def _check_config(session, volume: Volume, rel: str, file: Path, user) -> None:
    """A file in the config folder is checked before it is saved: one that could not work is refused with a reason."""
    if volume.kind == "config" and project_config.is_validated(rel):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            await project_config.validate_write(session, volume.project_id, rel, text, user)
        except project_config.ConfigError as e:
            raise _bad(str(e)) from None


async def _config_changed(session, volume: Volume) -> None:
    """After a change in the config folder the agent and tool rows follow their files."""
    if volume.kind == "config":
        await project_config.sync_project(session, volume.project_id)


def _safe(root: Path, rel: str, *, follow_leaf: bool = True) -> Path:
    try:
        return safe_path(root, rel, follow_leaf=follow_leaf)
    except FileError as e:
        raise _bad(str(e)) from None


@router.get("/volumes/{volume_id}/files", response_model=FolderListing)
async def list_files(
    volume_id: int,
    request: Request,
    response: Response,
    session: SessionDep,
    user: CurrentUser,
    path: str = "",
):
    """A folder's contents. The page asks again every few seconds while it is open, so the answer carries an ETag and
    an unchanged folder costs a bodyless 304 (the listing is the cheap part; sending it again is not needed)."""
    root, writable, runs, _ = await _root(request, session, volume_id, user)
    folder = _safe(root, path)
    if not folder.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
    entries = await asyncio.to_thread(list_dir, folder)
    listing = FolderListing(
        path="/".join(p for p in path.split("/") if p),
        entries=[FileEntry(**vars(e)) for e in entries],
        writable=writable,
        runs=[RunRef(task_id=task_id, title=title) for task_id, title in runs],
    )
    etag = f'"{hashlib.sha1(listing.model_dump_json().encode()).hexdigest()[:20]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return listing


@router.get("/volumes/{volume_id}/file")
async def read_file(
    volume_id: int,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    path: str,
    download: bool = False,
) -> FileResponse:
    root, *_ = await _root(request, session, volume_id, user)
    target = _safe(root, path)
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    headers = {"X-Content-Type-Options": "nosniff"}
    if download:
        return FileResponse(
            target, filename=target.name, media_type="application/octet-stream", headers=headers
        )
    image = INLINE_IMAGES.get(target.suffix.lower().lstrip("."))
    return FileResponse(
        target,
        media_type=image or "text/plain; charset=utf-8",
        content_disposition_type="inline",
        headers={**headers, "Content-Security-Policy": INLINE_POLICY},
    )


@router.put("/volumes/{volume_id}/file", status_code=status.HTTP_204_NO_CONTENT)
async def upload_file(
    volume_id: int,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    path: str,
    overwrite: bool = False,
    base: datetime | None = None,
) -> None:
    """Saves the request body as the file at `path`. It is the raw body, not a form, so no extra dependency.

    `base` is the modified time the editor saw when it opened the file: if the file has changed since, the save is
    refused (412) instead of silently replacing someone else's version."""
    root, _, _, volume = await _root(request, session, volume_id, user, write=True)
    target = _safe(root, path, follow_leaf=False)
    if target == root or target.is_dir():
        raise _bad("Choose a file name")
    if target.exists() and not overwrite:
        raise HTTPException(status.HTTP_409_CONFLICT, "A file with that name already exists")
    if base is not None and target.is_file():
        seen = base if base.tzinfo else base.replace(tzinfo=UTC)
        if abs((datetime.fromtimestamp(target.stat().st_mtime, UTC) - seen).total_seconds()) > 0.001:
            raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "This file changed since you opened it")
    if not target.parent.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
    # written beside the target and renamed into place, so a cell never reads a half written file
    partial = target.parent / f".{target.name}.{uuid.uuid4().hex}.part"
    size = 0
    try:
        with partial.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise _bad(f"Files up to {MAX_UPLOAD // 2**20} MB can be uploaded")
                f.write(chunk)
        await _check_config(session, volume, _rel(root, target), partial, user)
        if target.is_file():
            shutil.copymode(target, partial)  # editing a script must not take its executable bit away
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    await _config_changed(session, volume)


@router.post("/volumes/{volume_id}/folder", status_code=status.HTTP_201_CREATED)
async def create_folder(
    volume_id: int, body: FolderIn, request: Request, session: SessionDep, user: CurrentUser
) -> None:
    root, _, _, volume = await _root(request, session, volume_id, user, write=True)
    target = _safe(root, body.path, follow_leaf=False)
    if target.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "Something with that name already exists")
    if not target.parent.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
    target.mkdir()
    await _config_changed(session, volume)


@router.post("/volumes/{volume_id}/move", status_code=status.HTTP_204_NO_CONTENT)
async def move_file(
    volume_id: int, body: MoveIn, request: Request, session: SessionDep, user: CurrentUser
) -> None:
    """Renames or moves a file or folder within the same volume."""
    root, _, _, volume = await _root(request, session, volume_id, user, write=True)
    source = _safe(root, body.source, follow_leaf=False)
    destination = _safe(root, body.destination, follow_leaf=False)
    if source == root or not os.path.lexists(source):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    if destination == root or os.path.lexists(destination):
        raise HTTPException(status.HTTP_409_CONFLICT, "Something with that name already exists")
    if source in destination.parents:
        raise _bad("A folder cannot be moved into itself")
    if not destination.parent.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
    if volume.kind == "config" and (
        project_config.is_layout_folder(_rel(root, source))
        or project_config.is_layout_folder(_rel(root, destination))
    ):
        raise _bad("agents, skills and mcp are Themis's own folders: they keep their names")
    os.rename(source, destination)
    await _config_changed(session, volume)


@router.delete("/volumes/{volume_id}/file", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    volume_id: int, request: Request, session: SessionDep, user: CurrentUser, path: str
) -> None:
    """Deletes a file, or a folder with everything in it. There is no undo."""
    root, _, _, volume = await _root(request, session, volume_id, user, write=True)
    target = _safe(root, path, follow_leaf=False)
    if target == root:
        raise _bad("The folder itself cannot be deleted here")
    if not os.path.lexists(target):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    if volume.kind == "config" and project_config.is_layout_folder(_rel(root, target)):
        raise _bad("agents, skills and mcp are Themis's own folders: they cannot be deleted")
    if target.is_dir() and not target.is_symlink():
        await asyncio.to_thread(shutil.rmtree, target)
    else:
        target.unlink()
    await _config_changed(session, volume)
