import asyncio
import codecs
import contextlib
import csv
import io
import os
from pathlib import Path

import app.execution.cell_package as package
import app.features.agents.skills as skill_store
from app.execution.cells.contract import (
    DEFAULT_CELL_SCRIPT,
    SECRETS_DIR,
    CellError,
    CellResult,
    CellSpec,
    CellTimeout,
    LogSink,
)
from app.execution.cells.files import prepare_dirs, read_blocked, read_result
from app.execution.cells.secrets import WritebackFilter, secrets_archive
from app.features.system.docker_check import docker_bin, docker_env


def mount_arg(source: Path | str, target: str, *, read_only: bool = False) -> list[str]:
    """A bind mount as `--mount type=bind,source=...,target=...`. Not `-v source:target`: its colon cannot tell a Windows
    drive (C:\\notes) from the separator. The fields are quoted the way Docker reads them (as CSV), so a comma or a quote
    in a folder name cannot start a new field and mount something else. A folder that does not exist is an error with
    --mount (where -v made it), so prepare_dirs makes every one first."""
    fields = ["type=bind", f"source={source}", f"target={target}", *(["readonly"] if read_only else [])]
    out = io.StringIO()
    csv.writer(out, lineterminator="").writerow(fields)
    return ["--mount", out.getvalue()]


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
        script = spec.script or DEFAULT_CELL_SCRIPT
        extra: list[str] = []
        if owner:
            extra += ["--user", f"{owner[0]}:{owner[1]}"]
        if spec.secret_files:
            owner_opts = f",uid={owner[0]},gid={owner[1]}" if owner else ""
            extra += ["-i", "--tmpfs", f"{SECRETS_DIR}:rw,noexec,nosuid,nodev,size=32m,mode=0700{owner_opts}"]
            script = f"tar -xf - -C / || exit 1\n{script}"
        return [
            docker_bin(), "run", "--rm",
            "--name", self._name(spec),
            "--label", "themis.cell=1",
            "--label", f"themis.attempt={spec.attempt_id}",
            "--cpus", str(spec.cpus),
            "--memory", f"{spec.memory_mb}m",
            *extra,
            *mount_arg(spec.workspace_dir, "/workspace"),
            *[a for m in spec.mounts for a in mount_arg(m.source, f"/workspace/{m.name}", read_only=m.read_only)],
            *(mount_arg(spec.skills_dir, skill_store.mount_at(spec.harness), read_only=True) if spec.mounts_skills else []),
            *(mount_arg(package.skills_root(), package.SKILLS_MOUNT_AT, read_only=True) if spec.package_skill and not spec.skills_bundle else []),
            *mount_arg(spec.cell_dir, "/cell"),
            "-e", f"THEMIS_TASK_ID={spec.task_id}",
            "-e", f"THEMIS_TASK_TITLE={spec.title}",
            *[a for k, v in spec.env.items() for a in ("-e", f"{k}={v}")],
            spec.image,
            "sh", "-c", script,
        ]  # fmt: skip

    async def run(self, spec: CellSpec, on_log: LogSink) -> CellResult:
        prepare_dirs(spec)
        args = self.build_args(spec)
        wb = WritebackFilter(spec.writeback)
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
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                while chunk := await proc.stdout.read(4096):
                    if text := wb.feed(decoder.decode(chunk)):
                        await on_log(text)
                if text := wb.feed(decoder.decode(b"", final=True)) + wb.flush():
                    await on_log(text)
                code = await proc.wait()
        except TimeoutError:
            await self.kill(spec)
            raise CellTimeout(f"Cell timed out after {spec.timeout_seconds}s and was stopped") from None
        except asyncio.CancelledError:
            await self.kill(spec)
            raise
        finally:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                await proc.wait()
        return CellResult(
            exit_code=code, result=read_result(spec), blocked=read_blocked(spec), writeback=wb.files
        )

    async def kill(self, spec: CellSpec) -> None:
        proc = await asyncio.create_subprocess_exec(
            docker_bin(), "rm", "-f", self._name(spec),
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
                docker_bin(), "ps", "-aq", "--filter", "label=themis.cell=1",
                env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )  # fmt: skip
            out, _ = await proc.communicate()
            ids = out.decode().split()
            if proc.returncode == 0 and ids:
                rm = await asyncio.create_subprocess_exec(
                    docker_bin(), "rm", "-f", *ids,
                    env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                )  # fmt: skip
                await rm.wait()
            return len(ids) if proc.returncode == 0 else 0
        except FileNotFoundError:
            return 0
