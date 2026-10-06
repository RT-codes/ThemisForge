"""Does the image an agent runs in have what its tool servers need to start?

A tool server that runs a command (npx, uvx, a binary) fails when the image does not have it, and the agent just
carries on without the tool, which is hard to notice. So when an agent is saved, the commands are looked up in the image
and anything missing is reported.
"""

from .config import settings
from .docker_check import docker_env, run_command


async def missing_commands(image: str, commands: dict[str, str], docker_host: str = "") -> list[str]:
    """Warnings (for people) about tool servers whose command is not in the image. `commands` is server name -> command.
    Nothing is checked, and nothing is reported, when cells are simulated or there is nothing to look up."""
    if not commands or settings.cell_backend == "fake":
        return []
    env = docker_env(docker_host)
    code, _, _ = await run_command(["docker", "image", "inspect", image], env, 30)
    if code != 0:
        return [f"The image {image} is not on this machine yet, so its tools could not be checked."]
    warnings = []
    found: dict[str, bool] = {}
    for server, command in commands.items():
        if command not in found:
            code, _, _ = await run_command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--entrypoint",
                    "sh",
                    image,
                    "-c",
                    'command -v "$1" >/dev/null',
                    "sh",
                    command,
                ],
                env,
                60,
            )
            found[command] = code == 0
        if not found[command]:
            warnings.append(
                f"'{command}' is not in the image {image}, so the tool '{server}' would fail to start. "
                "Choose an image that has it."
            )
    return warnings
