import asyncio
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass

# The oldest Docker Engine Themis is asked to work with: older ones are out of support upstream. Docker Desktop reports
# the version of the engine inside it, so the same number applies there.
MIN_DOCKER = (24, 0)
MIN_DOCKER_TEXT = ".".join(str(n) for n in MIN_DOCKER)
INSTALL_LINKS = (
    "Docker Desktop (Windows): https://docs.docker.com/desktop/setup/install/windows-install/ - "
    "Docker Engine (Linux): https://docs.docker.com/engine/install/"
)


@dataclass
class DockerStatus:
    ok: bool
    installed: bool
    host: str  # what we are pointed at ("local socket" when no override is set)
    version: str | None = None
    os: str | None = None
    os_type: str | None = None  # "linux" or "windows": which kind of containers the engine runs
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


def docker_bin() -> str:
    """The docker program as the system finds it (PATH and PATHEXT), so docker.exe and a docker.cmd both work on Windows,
    where a bare "docker" only ever finds an .exe."""
    return shutil.which("docker") or "docker"


async def run_command(args: list[str], env: dict[str, str], timeout: float) -> tuple[int, str, str]:
    if args and args[0] == "docker":
        args = [docker_bin(), *args[1:]]
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


def parse_version(text: str | None) -> tuple[int, ...] | None:
    """(27, 1, 0) from "27.1.0", "24.0.7-ce" or "25.0.0-rc.1"; None when it does not start with numbers."""
    m = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?", (text or "").strip())
    return tuple(int(n) for n in m.groups() if n is not None) if m else None


def _hint(error: str) -> str | None:
    low = error.lower()
    if "permission denied" in low:
        return "The Themis user cannot use Docker. Add it to the 'docker' group and restart the service."
    if "cannot connect" in low or "is the docker daemon running" in low or "no such file" in low:
        return "The Docker daemon is not reachable. Start Docker (open Docker Desktop, or run: sudo systemctl start docker) or fix the Docker host."
    return None


async def check_docker(host: str = "") -> DockerStatus:
    label = host or "local socket"
    if shutil.which("docker") is None:
        return DockerStatus(
            ok=False,
            installed=False,
            host=label,
            error="The docker CLI was not found on this machine.",
            hint=f"Install Docker and make sure 'docker' is on the PATH. {INSTALL_LINKS}",
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
    status = DockerStatus(
        ok=True,
        installed=True,
        host=label,
        version=info.get("ServerVersion"),
        os=info.get("OperatingSystem"),
        os_type=info.get("OSType"),
        cpus=info.get("NCPU"),
        memory_mb=int(memory / 1024 / 1024) if memory else None,
    )
    # Reachable is not enough: the engine must run Linux containers (cells are Linux), and be recent enough.
    if status.os_type and status.os_type != "linux":
        status.ok = False
        status.error = f"Docker is set to run {status.os_type} containers, and cells are Linux containers."
        status.hint = "In Docker Desktop, right-click its tray icon and choose 'Switch to Linux containers'."
    elif (found := parse_version(status.version)) is not None and found < MIN_DOCKER:
        status.ok = False
        status.error = (
            f"Docker {status.version} is older than {MIN_DOCKER_TEXT}, the oldest version Themis supports."
        )
        status.hint = f"Update Docker. {INSTALL_LINKS}"
    return status
