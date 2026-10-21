import asyncio
import hashlib
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

import app.features.storage.service as operations
from app.api.dependencies import CurrentUser, SessionDep
from app.features.storage.schemas import (
    FileEntry,
    FolderIn,
    FolderListing,
    MoveIn,
    RunRef,
    VolumeIn,
    VolumeOut,
    VolumePatch,
)
from app.features.storage.service import (
    _root,
    _safe,
    save_file,
)
from app.features.storage.volumes import (
    list_dir,
)

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

INLINE_POLICY = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"

router = APIRouter(tags=["volumes"])


@router.get("/projects/{project_id}/volumes", response_model=list[VolumeOut])
async def list_volumes(
    project_id: int, session: SessionDep, user: CurrentUser, include_config: bool = False
) -> list[VolumeOut]:
    """The project's shared folders. Its config folder is not one (it can never be mounted), so only the Files page,
    which shows it too, asks for it."""

    return await operations.list_volumes(project_id, session, user, include_config)


@router.get("/projects/{project_id}/config", response_model=VolumeOut)
async def get_config_folder(project_id: int, session: SessionDep, user: CurrentUser) -> VolumeOut:
    """The folder where the project's agents, skills and tools are kept (see app/project_config.py)."""

    return await operations.get_config_folder(project_id, session, user)


@router.post("/projects/{project_id}/volumes", response_model=VolumeOut, status_code=status.HTTP_201_CREATED)
async def create_volume(project_id: int, body: VolumeIn, session: SessionDep, user: CurrentUser) -> VolumeOut:
    return await operations.create_volume(project_id, body, session, user)


@router.patch("/volumes/{volume_id}", response_model=VolumeOut)
async def update_volume(
    volume_id: int, body: VolumePatch, request: Request, session: SessionDep, user: CurrentUser
) -> VolumeOut:
    return await operations.update_volume(volume_id, body, request.app.state, session, user)


@router.delete("/volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_volume(volume_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Removes the folder from the project. Its files stay on disk; nothing is deleted."""

    return await operations.delete_volume(volume_id, session, user)


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
    root, writable, runs, _ = await _root(request.app.state, session, volume_id, user)
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
    root, *_ = await _root(request.app.state, session, volume_id, user)
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
    await save_file(request.app.state, session, volume_id, user, path, request.stream(), overwrite, base)


@router.post("/volumes/{volume_id}/folder", status_code=status.HTTP_201_CREATED)
async def create_folder(
    volume_id: int, body: FolderIn, request: Request, session: SessionDep, user: CurrentUser
) -> None:
    return await operations.create_folder(volume_id, body, request.app.state, session, user)


@router.post("/volumes/{volume_id}/move", status_code=status.HTTP_204_NO_CONTENT)
async def move_file(
    volume_id: int, body: MoveIn, request: Request, session: SessionDep, user: CurrentUser
) -> None:
    """Renames or moves a file or folder within the same volume."""

    return await operations.move_file(volume_id, body, request.app.state, session, user)


@router.delete("/volumes/{volume_id}/file", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    volume_id: int, request: Request, session: SessionDep, user: CurrentUser, path: str
) -> None:
    """Deletes a file, or a folder with everything in it. There is no undo."""

    return await operations.delete_file(volume_id, request.app.state, session, user, path)
