import os
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from .budget import Cost
from .models import AppSetting

_KEY = "app"

MAX_BUDGET_CPUS = 4096
MAX_BUDGET_MEMORY_MB = 16_777_216
DEFAULT_START_COOLDOWN_SECONDS = 5  # read when settings are created (not at import), so tests can lower it


class MountRoot(BaseModel):
    """A folder on this machine whose contents cells may be given (see app/volumes.py)."""

    path: str
    allow_write: bool = False  # cells may change what is in it, not only read it

    @field_validator("path")
    @classmethod
    def absolute(cls, v: str) -> str:
        v = v.strip()
        if os.name == "nt":
            # Windows: C:\Users\you\notes or C:/Users/you/notes, kept with forward slashes. The only colon is the drive's.
            v = v.replace("\\", "/")
            if v.startswith("//"):
                raise ValueError(
                    "A network share (\\\\server\\share) cannot be approved. Use a folder on a drive."
                )
            drive = re.match(r"^[A-Za-z]:(/.*)?$", v)
            if not drive:
                raise ValueError("The folder must be an absolute path, like C:\\Users\\you\\notes")
            v = v.rstrip("/") if len(v) > 3 else v
            if ":" in v[2:] or "\0" in v:
                raise ValueError("A colon in the folder path is not supported")
            if len(v) <= 3:
                raise ValueError("Approving a whole drive is not allowed. Pick a folder.")
            return v
        v = v.rstrip("/") or "/"
        if not v.startswith("/"):
            raise ValueError("The folder must be an absolute path, like /home/you/notes")
        if ":" in v or "\0" in v:
            raise ValueError("A colon in the folder path is not supported")
        if v == "/":
            raise ValueError("Approving the whole disk is not allowed. Pick a folder.")
        return v


class Budget(BaseModel):
    """What all running cells together may use. Kept as an object so other kinds of budget (API cost, for example)
    can be added next to the hardware ones."""

    cpus: float = Field(default=2.0, gt=0, le=MAX_BUDGET_CPUS)
    memory_mb: int = Field(default=2048, ge=64, le=MAX_BUDGET_MEMORY_MB)

    def as_cost(self) -> Cost:
        return Cost(self.cpus, self.memory_mb)


class AppSettings(BaseModel):
    """Operator settings edited from the Settings page (stored as one JSON row)."""

    timezone: str = "UTC"  # cron schedules are evaluated in this zone
    docker_host: str = ""  # empty = the local Docker socket; e.g. ssh://user@host or tcp://host:2376
    cell_image: str = "alpine:3"
    cell_cpus: float = Field(default=1.0, gt=0, le=64)
    cell_memory_mb: int = Field(default=1024, ge=64, le=1_048_576)
    cell_timeout_seconds: int = Field(default=3600, ge=10, le=86_400)
    budget: Budget = Budget()
    # A Ready task starts only this long after it last changed (was moved to Ready, or its previous run ended). It
    # keeps a task that keeps putting itself back, or a workflow that keeps creating tasks, from hammering the machine.
    start_cooldown_seconds: int = Field(default_factory=lambda: DEFAULT_START_COOLDOWN_SECONDS, ge=0, le=3600)
    mount_roots: list[MountRoot] = []  # folders cells may be given, see app/volumes.py
    codex_image: str = "themisforge/cell-codex:latest"  # built with ./themis build-images
    codex_model: str = "gpt-6-luna"
    codex_reasoning_effort: Literal["low", "medium", "high"] = "high"
    check_for_updates: bool = (
        True  # ask GitHub once a day whether a newer release exists (see app/updates.py)
    )
    update_channel: Literal["stable", "beta"] = "stable"  # beta also offers pre-releases
    keep_workspaces_days: int = Field(
        default=7, ge=0, le=3650
    )  # attempt working folders; 0 = delete right away

    @model_validator(mode="before")
    @classmethod
    def from_cell_count(cls, data):
        """Settings saved before the budget existed limited the number of cells. The same limit as a budget is that
        many cells of the configured size, so nothing changes for an existing installation."""
        if isinstance(data, dict) and "budget" not in data and "max_concurrent_cells" in data:
            try:
                count = int(data["max_concurrent_cells"])
                cpus = float(data.get("cell_cpus", 1.0))
                memory = int(data.get("cell_memory_mb", 1024))
            except (TypeError, ValueError):
                return data
            data = {
                **data,
                "budget": {
                    "cpus": min(count * cpus, MAX_BUDGET_CPUS),
                    "memory_mb": min(count * memory, MAX_BUDGET_MEMORY_MB),
                },
            }
        return data

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Unknown timezone: {v}") from None
        return v

    @field_validator("docker_host")
    @classmethod
    def valid_docker_host(cls, v: str) -> str:
        v = v.strip()
        if v and not v.startswith(("unix://", "tcp://", "ssh://")):
            raise ValueError("Docker host must start with unix://, tcp:// or ssh://")
        return v

    @field_validator("codex_model")
    @classmethod
    def valid_model(cls, v: str) -> str:
        v = v.strip()
        if not v or v.startswith("-") or any(c.isspace() or c in "'\"$`\\;&|<>" for c in v):
            raise ValueError("Invalid model name")
        return v

    @field_validator("cell_image", "codex_image")
    @classmethod
    def valid_image(cls, v: str) -> str:
        v = v.strip()
        if not v or v.startswith("-") or any(c.isspace() for c in v):
            raise ValueError("Invalid image name")
        return v


async def load_settings(session: AsyncSession) -> AppSettings:
    row = await session.get(AppSetting, _KEY)
    return AppSettings.model_validate(row.value) if row else AppSettings()


async def save_settings(session: AsyncSession, value: AppSettings) -> AppSettings:
    row = await session.get(AppSetting, _KEY)
    if row is None:
        session.add(AppSetting(key=_KEY, value=value.model_dump()))
    else:
        row.value = value.model_dump()
    await session.commit()
    return value
