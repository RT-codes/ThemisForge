import os
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.budget import Cost
from app.features.agents.skills import SkillError, parse_frontmatter
from app.persistence.models import AppSetting

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


class McpAuthPolicy(BaseModel):
    """How Themis signs in to the tool servers that ask for it (see app/mcp_auth). Every number that sign in depends on
    lives here, never in the code: a service that changes how long its tokens last needs a setting changed, not a
    release. What one service does differently from the rest goes in app/mcp_auth/servers.yaml instead."""

    # A token must still be good for this long, on top of the run's own time limit, when a run starts: otherwise it is
    # renewed first. Lowering it renews less often, raising it protects longer runs from a token that ends mid-way.
    refresh_margin_seconds: int = Field(default=600, ge=0, le=86_400)
    # How long a token is assumed to last when the service does not say (it normally does: its answer wins).
    default_token_seconds: int = Field(default=3600, ge=60, le=2_592_000)
    # A sign in nobody used for this many days is renewed anyway, because services let a sign in lapse when it sits
    # unused (Notion after 30 days). 0 switches this off.
    keepalive_days: int = Field(default=7, ge=0, le=365)
    sign_in_minutes: int = Field(default=10, ge=1, le=60)  # how long a started sign in waits for the person
    request_timeout_seconds: int = Field(default=15, ge=3, le=120)  # for each call to a service
    # Where a browser reaches Themis, when that is not the address the page was opened on (behind a reverse proxy).
    # The service sends the person back here, so it must be an address their browser can open.
    public_url: str = ""
    client_name: str = Field(
        default="Themis", min_length=1, max_length=60
    )  # shown on the service's consent screen

    @field_validator("public_url")
    @classmethod
    def valid_public_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if v and not re.match(r"^https?://[^/\s?#]+$", v):
            raise ValueError("Use the address without a path, like https://themis.example.com")
        return v


class CellPackage(BaseModel):
    """What Themis itself puts into every Codex cell (see app/cell_package.py). Empty text means the built-in text, so
    only an edit is stored and a better built-in text still reaches everyone else."""

    rules_enabled: bool = True
    rules: str = Field(default="", max_length=4000)
    skill_enabled: bool = True
    skill: str = Field(
        default="", max_length=20_000
    )  # the whole SKILL.md of themis-cell, front matter included
    # Seconds to wait before each new try when the model provider could not serve a run for a moment. The number of
    # entries is the number of tries; empty means never.
    retry_waits: list[int] = [30, 90, 180]

    @field_validator("skill")
    @classmethod
    def skill_is_the_themis_cell_skill(cls, v: str) -> str:
        if not v.strip():
            return ""
        try:
            meta = parse_frontmatter(v)
        except SkillError as e:
            raise ValueError(str(e)) from None
        if meta.get("name") != "themis-cell" or not meta.get("description", "").strip():
            raise ValueError(
                "The skill needs the name themis-cell and a description, or Codex will not list it"
            )
        return v

    @field_validator("retry_waits")
    @classmethod
    def sane_waits(cls, v: list[int]) -> list[int]:
        if len(v) > 10 or any(not 0 <= wait <= 3600 for wait in v):
            raise ValueError("At most 10 retries, each waiting between 0 and 3600 seconds")
        return v


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
    # How many times automation (workflows) may move or make the same task in a row before it is stopped. A project
    # and a single task can set their own limit (see app/features/projects/automation.py).
    max_automation_hops: int = Field(default=10, ge=1, le=100)
    mount_roots: list[MountRoot] = []  # folders cells may be given, see app/features/storage/volumes.py
    codex_image: str = "themisforge/cell-codex:latest"  # built with ./themis build-images
    codex_model: str = "gpt-6-luna"
    codex_reasoning_effort: Literal["low", "medium", "high"] = "high"
    # How many Codex runs of one person may use their ChatGPT login at once (parallel workflow branches, several
    # tasks). Every run draws on the same plan's usage limits, so this is also how fast a plan gets used up.
    codex_max_parallel: int = Field(default=3, ge=1, le=16)
    claude_image: str = "themisforge/cell-claude:latest"  # built with ./themis build-images
    claude_model: str = "claude-sonnet-5-5"
    claude_reasoning_effort: Literal["low", "medium", "high"] = "high"
    cell_package: CellPackage = (
        CellPackage()
    )  # what Themis adds to every agent cell, see app/execution/cell_package.py
    # The client id of the GitHub OAuth App (device flow switched on) that "Sign in with GitHub" uses. It is public by
    # design, and empty until an administrator adds it: only the token way of connecting works until then.
    github_client_id: str = ""
    mcp_auth: McpAuthPolicy = McpAuthPolicy()  # signing in to tool servers, see app/mcp_auth
    check_for_updates: bool = (
        True  # ask GitHub once a day whether a newer release exists (see app/features/system/updates.py)
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

    @field_validator("github_client_id")
    @classmethod
    def valid_client_id(cls, v: str) -> str:
        v = v.strip()
        if v and not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", v):
            raise ValueError("A client id has only letters, digits, dots, dashes and underscores")
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
