from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.config import settings

LogSink = Callable[[str], Awaitable[None]]


SECRETS_DIR = "/run/themis-secrets"


DEFAULT_CELL_SCRIPT = (
    'echo "Cell started for task $THEMIS_TASK_ID: $THEMIS_TASK_TITLE"; '
    "cat /cell/input.json; echo; "
    'printf "Task %s (%s) ran in a cell and finished.\\n" "$THEMIS_TASK_ID" "$THEMIS_TASK_TITLE" '
    "> /cell/result.md; "
    'echo "Cell finished"'
)


class CellError(Exception):
    """The cell could not run (Docker unavailable, image missing, timeout...)."""


class CellTimeout(CellError):
    """The cell ran past its time limit and was stopped."""


def workdir_path(project_id: int, workdir_id: int) -> Path:
    """A working folder on the host. Named by numbers only, so nothing a person types can reach another folder."""
    return settings.data_dir / "projects" / str(project_id) / "workspaces" / str(workdir_id)


@dataclass(frozen=True)
class Mount:
    """A volume as the cell sees it: the folder on the host, mounted at /workspace/NAME."""

    name: str
    source: Path
    read_only: bool
    volume_id: int
    lock: bool = False  # writers take turns: only one run holds it at a time


@dataclass
class CellSpec:
    attempt_id: int
    task_id: int
    project_id: int
    title: str
    description: str
    properties: dict
    image: str
    cpus: float
    memory_mb: int
    timeout_seconds: int
    docker_host: str = ""
    env: dict[str, str] = field(default_factory=dict)
    # Credentials to hand to the cell, as {path under SECRETS_DIR: content}. They are streamed in memory-only
    # (never an env var, argument, host file or log line) and live on a tmpfs that vanishes with the cell.
    secret_files: dict[str, str] = field(default_factory=dict, repr=False)
    # What the harness wants run instead of the placeholder (see app/execution/harnesses/service.py), and the secret files whose final
    # content it prints on exit so the host can store a refreshed login.
    script: str | None = None
    prompt: str = ""
    writeback: tuple[str, ...] = ()
    owner_id: int = 0  # the user whose connections the cell may use
    harness: str = ""
    mounts: list[Mount] = field(default_factory=list)  # shared folders, mounted at /workspace/NAME
    # The attempt whose working folder this one uses: its own id, or an earlier attempt's when the run continues in
    # that folder (0 = its own, for specs built without the scheduler)
    workdir_id: int = 0
    skills: list[str] = field(
        default_factory=list
    )  # the agent's skills, copied in and mounted read only (app/features/agents/skills.py)
    keys: dict[int, str] = field(
        default_factory=dict
    )  # key id -> the variable it is exported as (app/features/tools/keys.py)
    mcp: list = field(
        default_factory=list
    )  # tool servers (McpSpec, app/features/tools/mcp.py), written into the harness config
    connections: list = field(
        default_factory=list
    )  # connections the run uses (RunConnection, app/features/connections/service.py); their secrets are filled in at start
    # The text of the themis-cell skill every cell is given (app/execution/cell_package.py), "" for none. It is staged once for
    # the installation and mounted read only, so it is not in this run's /cell where the agent could change it.
    package_skill: str = ""

    @property
    def skills_bundle(self) -> bool:
        """Claude Code has no place for skills of the whole installation, so there the themis-cell skill goes in the
        same read only folder as the agent's own skills. Codex gets it from a folder of its own (cell_package)."""
        return self.harness == "claude"

    @property
    def mounts_skills(self) -> bool:
        return bool(self.skills) or (self.skills_bundle and bool(self.package_skill))

    @property
    def workspace_dir(self) -> Path:
        return workdir_path(self.project_id, self.workdir_id or self.attempt_id)

    @property
    def skills_dir(self) -> Path:
        return self.cell_dir / "skills"

    @property
    def cell_dir(self) -> Path:
        return settings.data_dir / "projects" / str(self.project_id) / "attempts" / str(self.attempt_id)


@dataclass
class CellResult:
    exit_code: int
    result: str = ""
    blocked: str = ""  # what the agent wrote to /cell/blocked.md: why it could not do the task
    writeback: dict[str, str] = field(default_factory=dict, repr=False)  # secret file path -> final content


class CellManager(Protocol):
    async def run(self, spec: CellSpec, on_log: LogSink) -> CellResult: ...

    async def kill(self, spec: CellSpec) -> None: ...

    async def cleanup_orphans(self, docker_host: str) -> int: ...
