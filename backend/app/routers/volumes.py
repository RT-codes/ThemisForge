"""Shared folders (volumes) of a project: what cells can mount at /workspace/NAME. See app/volumes.py."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..app_settings import load_settings
from ..deps import CurrentUser, SessionDep
from ..models import Agent, Project, Volume
from ..volumes import NAME, MountError, ensure_default_volume, host_target, is_default, managed_dir
from .projects import _bad, _project

router = APIRouter(tags=["volumes"])


class VolumeIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    kind: Literal["managed", "host"] = "managed"
    host_path: str = Field(default="", max_length=1000)
    mode: Literal["ro", "rw"] = "rw"
    # None: writers take turns on a host folder that cells may write to, and not on a managed one
    exclusive_write: bool | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str) -> str:
        v = v.strip().lower()
        if not NAME.match(v):
            raise ValueError("Use lowercase letters, digits and dashes, starting with a letter or digit")
        return v


class VolumePatch(BaseModel):
    mode: Literal["ro", "rw"] | None = None
    exclusive_write: bool | None = None


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
            _, allowed = host_target(volume.host_path, cfg.mount_roots)
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
async def list_volumes(project_id: int, session: SessionDep, user: CurrentUser) -> list[VolumeOut]:
    await _project(session, project_id, user)
    await ensure_default_volume(session, project_id)
    volumes = (await session.scalars(select(Volume).where(Volume.project_id == project_id))).all()
    cfg = await load_settings(session)
    out = [await _out(v, cfg) for v in volumes]
    return sorted(out, key=lambda v: (not v.is_default, v.name))


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


@router.patch("/volumes/{volume_id}", response_model=VolumeOut)
async def update_volume(
    volume_id: int, body: VolumePatch, session: SessionDep, user: CurrentUser
) -> VolumeOut:
    volume, _ = await _volume(session, volume_id, user)
    cfg = await load_settings(session)
    if body.mode is not None and body.mode != volume.mode:
        if body.mode == "rw" and volume.kind == "host":
            try:
                _, allowed = host_target(volume.host_path, cfg.mount_roots)
            except MountError as e:
                raise _bad(str(e)) from None
            if not allowed:
                raise _bad(
                    "Cells may only read in that folder. An administrator can allow writing in Settings."
                )
        volume.mode = body.mode
    if body.exclusive_write is not None:
        volume.exclusive_write = body.exclusive_write
    await session.commit()
    return await _out(volume, cfg)


@router.delete("/volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_volume(volume_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Removes the folder from the project. Its files stay on disk; nothing is deleted."""
    volume, project = await _volume(session, volume_id, user)
    if is_default(volume):
        raise HTTPException(status.HTTP_409_CONFLICT, "Every project keeps its shared folder")
    for agent in await session.scalars(select(Agent).where(Agent.project_id == project.id)):
        kept = [m for m in agent.mounts if m.get("volume_id") != volume.id]
        if len(kept) != len(agent.mounts):
            agent.mounts = kept
    await session.delete(volume)
    await session.commit()
