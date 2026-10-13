"""Does the image an agent runs in have what its tool servers need to start?

A tool server that runs a command (npx, uvx, a binary) fails when the image does not have it, and the agent just
carries on without the tool, which is hard to notice. So when an agent is saved, the commands are looked up in the image
and anything missing is reported.
"""

from typing import Any

from .app_settings import AppSettings
from .config import settings
from .docker_check import docker_env, run_command
from .harness import plan_for
from .models import Project


def image_for(
    project: Project | None, cfg: AppSettings, harness: str, cell_profile: dict[str, Any] | None
) -> str:
    """The image an agent of this harness would run in: its own cell, else the project's, else the harness's. With no
    project (a look at tools in general, from Settings) it is the harness's."""
    hp = plan_for(harness, cfg)
    return (
        (cell_profile or {}).get("image")
        or ((project.cell_profile if project else None) or {}).get("image")
        or (hp.image if hp else cfg.cell_image)
    )


async def commands_in_image(image: str, commands: set[str], docker_host: str = "") -> dict[str, bool] | None:
    """Which of these commands the image has, as {command: found}. None when that cannot be said: there is nothing to
    look up, cells are simulated, or the image is not on this machine yet."""
    if not commands or settings.cell_backend == "fake":
        return None
    env = docker_env(docker_host)
    code, _, _ = await run_command(["docker", "image", "inspect", image], env, 30)
    if code != 0:
        return None
    found: dict[str, bool] = {}
    for command in sorted(commands):
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
    return found


async def missing_commands(image: str, commands: dict[str, str], docker_host: str = "") -> list[str]:
    """Warnings (for people) about tool servers whose command is not in the image. `commands` is server name -> command.
    Nothing is checked, and nothing is reported, when cells are simulated or there is nothing to look up."""
    if not commands or settings.cell_backend == "fake":
        return []
    found = await commands_in_image(image, set(commands.values()), docker_host)
    if found is None:
        return [f"The image {image} is not on this machine yet, so its tools could not be checked."]
    return [
        f"'{command}' is not in the image {image}, so the tool '{server}' would fail to start. "
        "Choose an image that has it."
        for server, command in commands.items()
        if not found[command]
    ]
