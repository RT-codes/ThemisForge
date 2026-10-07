"""Volumes: folders that outlive a run and are mounted into cells under /workspace.

A cell's own /workspace is private and thrown away. A volume is mounted inside it at /workspace/NAME, so runs can
hand files to each other. Two kinds:

  managed   a folder ThemisForge makes under its data directory (nothing to set up)
  host      an existing folder on this machine, only inside a folder an administrator approved in Settings

The rules for host folders are the safety net, so they are checked when a volume is made and again every time a cell
starts (the folder, a symlink or the approved list may have changed since).
"""

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from .app_settings import AppSettings, MountRoot
from .cells import Mount
from .config import BACKEND_DIR, settings
from .models import Volume

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
DEFAULT_NAME = "shared"


class MountError(Exception):
    """A folder cannot be mounted. The message is shown to the person who runs the task."""


class FileError(Exception):
    """A path inside a folder cannot be used (it escapes the folder, is badly formed, or does not exist)."""


class MountRef(BaseModel):
    """A request to mount a volume, as stored on an agent or a run."""

    volume_id: int
    mode: Literal["ro", "rw"] = "rw"


def managed_dir(project_id: int, name: str) -> Path:
    return settings.data_dir / "projects" / str(project_id) / "volumes" / name


def _protected() -> list[Path]:
    """What a mounted folder may never be, or contain: ThemisForge's own data, database and configuration."""
    paths = [settings.data_dir, BACKEND_DIR]
    if db := make_url(settings.database_url).database:
        paths.append(Path(db))
    return [p.resolve() for p in paths]


def _overlaps(a: Path, b: Path) -> bool:
    return a == b or b in a.parents or a in b.parents


def host_target(path: str, roots: list[MountRoot]) -> tuple[Path, bool]:
    """The real folder behind a host path and whether cells may write to it.

    Symlinks are followed before the check, so a link inside an approved folder that points outside it is refused."""
    raw = Path(path)
    if not raw.is_absolute():
        raise MountError("The folder must be an absolute path, like /home/you/notes")
    if ":" in path:
        raise MountError("A colon in the folder path is not supported")
    try:
        real = raw.resolve(strict=True)
    except OSError:
        raise MountError(f"The folder {path} does not exist") from None
    if not real.is_dir():
        raise MountError(f"{path} is not a folder")
    if any(_overlaps(real, p) for p in _protected()):
        raise MountError("That folder is, or contains, Themis's own data or configuration")
    for root in roots:
        base = Path(root.path).resolve()
        if real == base or base in real.parents:
            return real, root.allow_write
    raise MountError(
        f"{path} is not inside an approved folder. An administrator can approve one in Settings."
    )


def resolve_volume(volume: Volume, cfg: AppSettings) -> tuple[Path, bool]:
    """The real folder on this machine behind a volume, and whether its approved root lets cells write there.

    Host folders are validated again on every call, for the same reason they are on every cell start."""
    if volume.kind == "host":
        return host_target(volume.host_path, cfg.mount_roots)
    return managed_dir(volume.project_id, volume.name), True


def safe_path(root: Path, rel: str, *, follow_leaf: bool = True) -> Path:
    """The real path of `rel` (a slash separated path relative to a volume's root), refusing anything outside it.

    This is the one gate between the Files page and the disk: every read or change goes through it. The folder
    part is always resolved, so a symlink in the middle cannot lead out. The last part is resolved too unless
    `follow_leaf` is False, which lets a symlink itself be renamed or removed without touching its target."""
    parts = [p for p in rel.split("/") if p]
    if any(p in (".", "..") or "\0" in p for p in parts):
        raise FileError("That path is not valid")
    root = root.resolve()
    target = root.joinpath(*parts)
    real = target.resolve() if follow_leaf else target.parent.resolve() / target.name
    if real != root and root not in real.parents:
        raise FileError("That path is outside the folder")
    return real


@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int
    modified: datetime


def list_dir(folder: Path) -> list[Entry]:
    """The contents of a folder, folders first. A symlink is listed as a plain file and never followed."""
    entries = []
    with os.scandir(folder) as it:
        for e in it:
            st = e.stat(follow_symlinks=False)
            is_dir = e.is_dir(follow_symlinks=False)
            entries.append(
                Entry(e.name, is_dir, 0 if is_dir else st.st_size, datetime.fromtimestamp(st.st_mtime, UTC))
            )
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


async def ensure_default_volume(session: AsyncSession, project_id: int) -> Volume:
    """Every project has a `shared` folder from the start, created the first time it is needed."""
    volume = await session.scalar(
        select(Volume).where(Volume.project_id == project_id, Volume.name == DEFAULT_NAME)
    )
    if volume is None:
        volume = Volume(project_id=project_id, name=DEFAULT_NAME, kind="managed", mode="rw")
        session.add(volume)
        await session.commit()
    return volume


def is_default(volume: Volume) -> bool:
    return volume.kind == "managed" and volume.name == DEFAULT_NAME


async def plan_mounts(
    session: AsyncSession, project_id: int, refs: list[dict], cfg: AppSettings
) -> list[Mount]:
    """What a cell mounts: the project's `shared` folder always, plus the volumes asked for (later asks win).

    Raises MountError when something cannot be mounted right now, so the run fails with a reason."""
    wanted: dict[int, str] = {}
    default = await ensure_default_volume(session, project_id)
    wanted[default.id] = "rw"
    for ref in refs:
        parsed = MountRef.model_validate(ref)
        wanted[parsed.volume_id] = parsed.mode
    volumes = {v.id: v for v in await session.scalars(select(Volume).where(Volume.id.in_(list(wanted))))}
    mounts: list[Mount] = []
    for volume_id, mode in wanted.items():
        volume = volumes.get(volume_id)
        if volume is None or volume.project_id != project_id:
            raise MountError("A shared folder this run uses no longer exists")
        source, allowed = resolve_volume(volume, cfg)
        writable = volume.mode == "rw" and allowed
        if mode == "rw" and volume.mode == "rw" and not allowed:
            raise MountError(
                f"'{volume.name}' is no longer approved for writing. Check Settings, Mount roots."
            )
        read_only = mode == "ro" or not writable
        mounts.append(
            Mount(
                name=volume.name,
                source=source,
                read_only=read_only,
                volume_id=volume.id,
                lock=volume.exclusive_write and not read_only,
            )
        )
    return sorted(mounts, key=lambda m: m.name)
