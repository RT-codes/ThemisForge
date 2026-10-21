from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.features.agents.skills as skill_store
from app.execution.profiles import ProfileOverrides
from app.features.connections.service import providers as connection_providers
from app.features.project_config.common import ConfigError
from app.features.project_config.formats import AgentFile, FolderRef, McpFile
from app.features.tools.mcp import McpIn
from app.persistence.models import Agent, McpServer, Secret, User, Volume


@dataclass
class Refs:
    """Everything a config file can name, in one project. Folders exclude the config folder: it is never mounted."""

    folders: dict[str, int]
    tools: dict[str, int]
    keys: dict[str, int]
    skills: set[str]

    @staticmethod
    def invert(names: dict[str, int]) -> dict[int, str]:
        return {i: n for n, i in names.items()}


async def load_refs(session: AsyncSession, project_id: int) -> Refs:
    volumes = await session.execute(
        select(Volume.name, Volume.id).where(Volume.project_id == project_id, Volume.kind != "config")
    )
    tools = await session.execute(
        select(McpServer.name, McpServer.id).where(McpServer.project_id == project_id)
    )
    keys = await session.execute(select(Secret.name, Secret.id))
    return Refs(
        folders=dict(volumes.all()),
        tools=dict(tools.all()),
        keys=dict(keys.all()),
        skills={s.name for s in skill_store.list_skills(project_id)},
    )


def _look_up(names: list[str], known: dict[str, int], what: str, where: str = "in this project") -> list[int]:
    ids = []
    for name in dict.fromkeys(names):
        if name not in known:
            raise ConfigError(f"The {what} '{name}' does not exist {where}")
        ids.append(known[name])
    return ids


def _keys_only_for_admins(actor: User | None, wanted: set[int], before: set[int], what: str) -> None:
    # A key is paid for or trusted by the whole installation, so only an administrator may hand one out. `actor` is
    # None when Themis itself reads a file, which only happens for files that were already accepted.
    if actor is not None and not actor.is_admin and wanted != before:
        raise ConfigError(f"Only an administrator can give {what} keys")


AGENT_COLUMNS = (
    "name",
    "role",
    "description",
    "instructions",
    "harness",
    "model",
    "reasoning_effort",
    "cell_profile",
    "mounts",
    "skills",
    "mcp_servers",
    "secrets",
    "connections",
)


def agent_fields(af: AgentFile, refs: Refs, actor: User | None, before: Agent | None) -> dict[str, Any]:
    """The columns of an agent row that this file stands for, or a ConfigError saying what is wrong."""
    modes = {f.name: f.mode for f in af.folders}
    folder_ids = _look_up([f.name for f in af.folders], refs.folders, "folder")
    keys = _look_up(af.keys, refs.keys, "key", "")
    _keys_only_for_admins(actor, set(keys), set(before.secrets) if before else set(), "an agent")
    if gone := [s for s in dict.fromkeys(af.skills) if s not in refs.skills]:
        raise ConfigError(f"The skill '{gone[0]}' does not exist in this project")
    if unknown := [c for c in dict.fromkeys(af.connections) if c not in connection_providers()]:
        raise ConfigError(f"Themis has no connection called '{unknown[0]}'")
    by_id = Refs.invert(refs.folders)
    return {
        "name": af.name,
        "role": af.role,
        "description": af.description,
        "instructions": af.instructions,
        "harness": af.harness,
        "model": af.model,
        "reasoning_effort": af.reasoning_effort,
        "cell_profile": af.cell.clean() if af.cell else None,
        "mounts": [{"volume_id": i, "mode": modes[by_id[i]]} for i in folder_ids],
        "skills": list(dict.fromkeys(af.skills)),
        "mcp_servers": _look_up(af.tools, refs.tools, "tool"),
        "secrets": keys,
        "connections": list(dict.fromkeys(af.connections)),
    }


def agent_file(agent: Agent, refs: Refs) -> AgentFile:
    """An agent row as a file. Something the row points at that no longer exists is left out."""
    folders, tools, keys = (Refs.invert(x) for x in (refs.folders, refs.tools, refs.keys))
    return AgentFile(
        name=agent.name,
        role=agent.role,
        description=agent.description,
        harness=agent.harness,  # type: ignore[arg-type]
        model=agent.model,
        reasoning_effort=agent.reasoning_effort,  # type: ignore[arg-type]
        cell=ProfileOverrides.model_validate(agent.cell_profile) if agent.cell_profile else None,
        folders=[
            FolderRef(name=folders[m["volume_id"]], mode=m["mode"])
            for m in agent.mounts
            if m["volume_id"] in folders
        ],
        skills=list(agent.skills),
        tools=[tools[i] for i in agent.mcp_servers if i in tools],
        keys=[keys[i] for i in agent.secrets if i in keys],
        connections=list(agent.connections),
        instructions=agent.instructions,
    )


def before_key_ids(server: McpServer) -> set[int]:
    return set(server.secret_env.values()) | ({server.bearer_secret_id} if server.bearer_secret_id else set())


def mcp_fields(
    name: str, mf: McpFile, refs: Refs, actor: User | None, before: McpServer | None
) -> dict[str, Any]:
    secret_env = {var: _look_up([key], refs.keys, "key", "")[0] for var, key in mf.keys.items()}
    bearer = _look_up([mf.bearer_key], refs.keys, "key", "")[0] if mf.bearer_key else None
    wanted = set(secret_env.values()) | ({bearer} if bearer else set())
    _keys_only_for_admins(actor, wanted, before_key_ids(before) if before else set(), "a tool")
    try:
        valid = McpIn(
            name=name,
            description=mf.description,
            kind=mf.kind,
            command=mf.command,
            args=mf.args,
            url=mf.url,
            env=mf.env,
            secret_env=secret_env,
            bearer_secret_id=bearer,
            auth=mf.auth,
        )
    except ValidationError as e:
        err = e.errors()[0]
        raise ConfigError(err["msg"].removeprefix("Value error, ")) from None
    return valid.model_dump(exclude={"name"})


def mcp_file(server: McpServer, refs: Refs) -> McpFile:
    keys = Refs.invert(refs.keys)
    return McpFile(
        description=server.description,
        kind=server.kind,  # type: ignore[arg-type]
        command=server.command,
        args=list(server.args),
        url=server.url,
        env=dict(server.env),
        keys={var: keys[i] for var, i in server.secret_env.items() if i in keys},
        bearer_key=keys.get(server.bearer_secret_id or 0, ""),
        auth=server.auth,
    )
