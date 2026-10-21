from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.features.system.settings import Budget


class SecretIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="custom", min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=10_000)


class SecretOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    hint: str
    created_at: datetime


class SchedulerStatus(BaseModel):
    running: bool
    active_cells: int
    max_cells: int


class Resources(BaseModel):
    """What the machine behind the cells has, and a budget that leaves it room to breathe."""

    ok: bool  # False when Docker could not be asked (see error and hint)
    error: str | None = None
    hint: str | None = None
    host_cpus: int | None = None
    host_memory_mb: int | None = None
    disk_total_mb: int  # the drive that holds ThemisForge's data (workspaces, results)
    disk_free_mb: int
    recommended: Budget | None = None


class CellDefaults(BaseModel):
    """The global cell defaults, which anyone who sets up a project's cell needs to see (Settings is admin only)."""

    image: str
    cpus: float
    memory_mb: int
    timeout_seconds: int


class SystemStatus(BaseModel):
    scheduler: SchedulerStatus
    cell_defaults: CellDefaults
    timezone: str
    pending_access_requests: int  # only filled in for administrators
    insecure_secret_key: bool
    cell_backend: str
    version: str
    platform: str  # "windows" | "linux" | "mac": what a folder path looks like here
    cells_ready: bool  # False while Docker cannot run cells: tasks wait instead of failing
    problems: list[
        dict[str, str]
    ]  # what the startup and background checks found; only filled in for administrators
    update: (
        dict | None
    )  # is there a newer release (see app/features/system/updates.py); only for administrators, who can act on it


class CellPackageDefaults(BaseModel):
    rules: str
    skill: str


class CellPackageInUse(BaseModel):
    """What every Codex agent is given right now, for the agent editor: edits and switches in Settings are applied."""

    skill_name: str
    skill_enabled: bool
    skill: str
    description: str
    rules_enabled: bool
    rules: str
