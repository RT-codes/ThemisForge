from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.storage.volumes import NAME


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
    # Published OpenAPI component identity predates the package organization.
    __module__ = "app.routers.volumes"

    source: str = Field(min_length=1, max_length=1000)
    destination: str = Field(min_length=1, max_length=1000)
