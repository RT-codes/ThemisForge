import asyncio
import json
import os
import shutil
from dataclasses import asdict, dataclass


@dataclass
class DockerStatus:
    ok: bool
    installed: bool
    host: str  # what we are pointed at ("local socket" when no override is set)
    version: str | None = None
    os: str | None = None
    cpus: int | None = None
    memory_mb: int | None = None
    error: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def docker_env(host: str = "") -> dict[str, str]:
    env = dict(os.environ)
    if host:
        env["DOCKER_HOST"] = host
    return env


async def run_command(args: list[str], env: dict[str, str], timeout: float) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"timed out after {timeout:.0f}s"
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def _hint(error: str) -> str | None:
    low = error.lower()
    if "permission denied" in low:
        return "The ThemisForge user cannot use Docker. Add it to the 'docker' group and restart the service."
    if "cannot connect" in low or "is the docker daemon running" in low or "no such file" in low:
        return "The Docker daemon is not reachable. Start it (systemctl start docker) or fix the Docker host."
    return None


async def check_docker(host: str = "") -> DockerStatus:
    label = host or "local socket"
    if shutil.which("docker") is None:
        return DockerStatus(
            ok=False,
            installed=False,
            host=label,
            error="The docker CLI was not found on this machine.",
            hint="Run ./themis install, or install Docker Engine and make sure 'docker' is on the PATH.",
        )
    code, out, err = await run_command(["docker", "info", "--format", "{{json .}}"], docker_env(host), 15)
    if code != 0:
        error = (err or out).strip().splitlines()[-1] if (err or out).strip() else "docker info failed"
        return DockerStatus(ok=False, installed=True, host=label, error=error, hint=_hint(error))
    try:
        info = json.loads(out)
    except json.JSONDecodeError:
        return DockerStatus(ok=False, installed=True, host=label, error="Unexpected output from docker info")
    memory = info.get("MemTotal")
    return DockerStatus(
        ok=True,
        installed=True,
        host=label,
        version=info.get("ServerVersion"),
        os=info.get("OperatingSystem"),
        cpus=info.get("NCPU"),
        memory_mb=int(memory / 1024 / 1024) if memory else None,
    )
