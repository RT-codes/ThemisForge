"""Cells: the throwaway containers tasks execute in.

CellManager is the only boundary around Docker. Everything else (scheduler, API) talks to this
interface, so Docker can later be swapped for Podman, a remote machine or another sandbox.

The cell contract (what runs inside a cell, whatever the harness):
  /workspace          the project's durable workspace (read/write, survives cells)
  /cell/input.json    the task, written before the cell starts
  /cell/result.md     optional: the cell writes its result here; it is stored with the attempt
  exit code 0         success, anything else is a failure
  /run/themis-secrets credentials for this attempt (see CellSpec.secret_files): in memory only, gone with the cell
"""

import asyncio
import contextlib
import io
import json
import os
import random
import tarfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .config import settings
from .docker_check import docker_env

LogSink = Callable[[str], Awaitable[None]]

SECRETS_DIR = "/run/themis-secrets"

# Placeholder cell program until agent harnesses exist: echoes the task and writes a result.
DEFAULT_CELL_SCRIPT = (
    'echo "Cell started for task $THEMIS_TASK_ID: $THEMIS_TASK_TITLE"; '
    "cat /cell/input.json; echo; "
    'printf "Task %s (%s) ran in a cell and finished.\\n" "$THEMIS_TASK_ID" "$THEMIS_TASK_TITLE" '
    "> /cell/result.md; "
    'echo "Cell finished"'
)


class CellError(Exception):
    """The cell could not run (Docker unavailable, image missing, timeout...)."""


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

    @property
    def workspace_dir(self) -> Path:
        return settings.data_dir / "projects" / str(self.project_id) / "workspace"

    @property
    def cell_dir(self) -> Path:
        return settings.data_dir / "projects" / str(self.project_id) / "attempts" / str(self.attempt_id)


@dataclass
class CellResult:
    exit_code: int
    result: str = ""


class CellManager(Protocol):
    async def run(self, spec: CellSpec, on_log: LogSink) -> CellResult: ...

    async def kill(self, spec: CellSpec) -> None: ...

    async def cleanup_orphans(self, docker_host: str) -> int: ...


def prepare_dirs(spec: CellSpec) -> None:
    spec.workspace_dir.mkdir(parents=True, exist_ok=True)
    spec.cell_dir.mkdir(parents=True, exist_ok=True)
    (spec.cell_dir / "input.json").write_text(
        json.dumps(
            {
                "task_id": spec.task_id,
                "title": spec.title,
                "description": spec.description,
                "properties": spec.properties,
            },
            indent=2,
        )
    )


def secrets_archive(files: dict[str, str], uid: int = 0, gid: int = 0) -> bytes:
    """A tar stream with the secret files, owner-only (0600), for `tar -x` inside the cell."""
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        for path, content in files.items():
            if not path.startswith(SECRETS_DIR + "/") or ".." in path.split("/"):
                raise CellError(f"Secret files must live under {SECRETS_DIR}")
            data = content.encode()
            info = tarfile.TarInfo(path.lstrip("/"))
            info.size, info.mode, info.uid, info.gid = len(data), 0o600, uid, gid
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


def read_result(spec: CellSpec) -> str:
    path = spec.cell_dir / "result.md"
    return path.read_text(errors="replace")[:100_000] if path.is_file() else ""


class FakeCellManager:
    """Simulates a cell without Docker. A title containing 'fail' makes the cell fail."""

    def __init__(self, duration: float = 0.0) -> None:
        self.duration = duration

    async def run(self, spec: CellSpec, on_log: LogSink) -> CellResult:
        prepare_dirs(spec)
        await on_log(f"[fake cell] started for task {spec.task_id}: {spec.title}\n")
        await asyncio.sleep(self.duration * (0.5 + random.random()))
        if "fail" in spec.title.lower():
            await on_log("[fake cell] simulated failure\n")
            return CellResult(exit_code=1)
        (spec.cell_dir / "result.md").write_text(f"Task {spec.task_id} ({spec.title}) finished.\n")
        await on_log("[fake cell] finished\n")
        return CellResult(exit_code=0, result=read_result(spec))

    async def kill(self, spec: CellSpec) -> None:
        return None

    async def cleanup_orphans(self, docker_host: str) -> int:
        return 0


class DockerCellManager:
    """Runs each cell with `docker run`, driven through the docker CLI (honours DOCKER_HOST)."""

    @staticmethod
    def _name(spec: CellSpec) -> str:
        return f"themis-cell-{spec.attempt_id}"

    @staticmethod
    def _owner() -> tuple[int, int] | None:
        """The uid/gid cells run as, so files written to the mounts stay ours. None on Windows."""
        return (os.getuid(), os.getgid()) if hasattr(os, "getuid") else None

    def build_args(self, spec: CellSpec) -> list[str]:
        owner = self._owner()
        script = DEFAULT_CELL_SCRIPT
        extra: list[str] = []
        if owner:
            extra += ["--user", f"{owner[0]}:{owner[1]}"]
        if spec.secret_files:
            owner_opts = f",uid={owner[0]},gid={owner[1]}" if owner else ""
            extra += ["-i", "--tmpfs", f"{SECRETS_DIR}:rw,noexec,nosuid,nodev,size=1m,mode=0700{owner_opts}"]
            script = f"tar -xf - -C / && {script}"
        return [
            "docker", "run", "--rm",
            "--name", self._name(spec),
            "--label", "themis.cell=1",
            "--label", f"themis.attempt={spec.attempt_id}",
            "--cpus", str(spec.cpus),
            "--memory", f"{spec.memory_mb}m",
            *extra,
            "-v", f"{spec.workspace_dir}:/workspace",
            "-v", f"{spec.cell_dir}:/cell",
            "-e", f"THEMIS_TASK_ID={spec.task_id}",
            "-e", f"THEMIS_TASK_TITLE={spec.title}",
            *[a for k, v in spec.env.items() for a in ("-e", f"{k}={v}")],
            spec.image,
            "sh", "-c", script,
        ]  # fmt: skip

    async def run(self, spec: CellSpec, on_log: LogSink) -> CellResult:
        prepare_dirs(spec)
        args = self.build_args(spec)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                env=docker_env(spec.docker_host),
                stdin=asyncio.subprocess.PIPE if spec.secret_files else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            raise CellError("The docker CLI was not found on this machine") from None
        try:
            if spec.secret_files:
                assert proc.stdin is not None
                owner = self._owner() or (0, 0)
                proc.stdin.write(secrets_archive(spec.secret_files, *owner))
                with contextlib.suppress(ConnectionError):
                    await proc.stdin.drain()
                    proc.stdin.close()
            async with asyncio.timeout(spec.timeout_seconds):
                assert proc.stdout is not None
                while chunk := await proc.stdout.read(4096):
                    await on_log(chunk.decode(errors="replace"))
                code = await proc.wait()
        except TimeoutError:
            await self.kill(spec)
            raise CellError(f"Cell timed out after {spec.timeout_seconds}s and was stopped") from None
        except asyncio.CancelledError:
            await self.kill(spec)
            raise
        finally:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                await proc.wait()
        return CellResult(exit_code=code, result=read_result(spec))

    async def kill(self, spec: CellSpec) -> None:
        proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", self._name(spec),
            env=docker_env(spec.docker_host),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )  # fmt: skip
        await proc.wait()

    async def cleanup_orphans(self, docker_host: str) -> int:
        """Remove cells left behind by a previous process (crash or restart)."""
        env = docker_env(docker_host)
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "ps", "-aq", "--filter", "label=themis.cell=1",
                env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )  # fmt: skip
            out, _ = await proc.communicate()
            ids = out.decode().split()
            if proc.returncode == 0 and ids:
                rm = await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", *ids,
                    env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                )  # fmt: skip
                await rm.wait()
            return len(ids) if proc.returncode == 0 else 0
        except FileNotFoundError:
            return 0


def make_cell_manager() -> CellManager:
    return FakeCellManager(duration=2.0) if settings.cell_backend == "fake" else DockerCellManager()
