"""The project's config folder: agents, skills and tool servers as files a person can read and edit.

    data/projects/<id>/config/
        agents/<slug>/agent.md      settings between two --- lines, then the agent's instructions
        skills/<name>/SKILL.md      see app/skills.py
        mcp/<name>.yaml             a tool server (MCP)

The files are the source of truth. The Files page shows and edits them like any other folder (the folder is a Volume of
kind "config", which can never be mounted into a cell). The `agents` and `mcp_servers` rows follow the files:

  * a row is the identity of its file (tasks and workflows point at the id, so a rename must not make a new agent)
    plus a parsed copy, so lists and runs do not parse files and the API keeps its shape;
  * `sync_project` reads the files into the rows, and the API writes a row's file when it changes the row;
  * a file that cannot be read keeps its last good row and flags it in `config_error`, so a typo never takes an
    agent away: the agent just refuses to run until the file is fixed;
  * a file that disappears flags its row instead of deleting it, because the files are all there is.

Files refer to things by name (a folder, skill, tool or key), rows by id. Names are checked on every save through the
Files page (`validate_write`), so a file that cannot work is refused with a reason instead of saved.
"""

import asyncio
import contextlib
import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from . import skills as skill_store
from .harness import clean_model_name
from .mcp import NAME, McpIn
from .models import Agent, McpServer, Project, Secret, User, Volume
from .profiles import ProfileOverrides
from .volumes import config_dir

log = logging.getLogger(__name__)

AGENTS, SKILLS, MCP = "agents", "skills", "mcp"
LAYOUT = (AGENTS, SKILLS, MCP)  # the folders Themis itself relies on: they cannot be renamed or deleted
AGENT_FILE = "agent.md"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

# Held while rows and files are brought in line (a sync, or an API change that writes a file), so a sync never sees a
# file whose row is not committed yet.
lock = asyncio.Lock()


class ConfigError(Exception):
    """A config file cannot be used. The message is meant for the person editing it."""


# ----- reading and writing the files -----


def ensure_layout(project_id: int) -> Path:
    """The config folder with its three folders. Skills used to live beside it, and are moved in once."""
    root = config_dir(project_id)
    legacy = root.parent / "skills"
    if legacy.is_dir() and not (root / SKILLS).exists():
        root.mkdir(parents=True, exist_ok=True)
        legacy.rename(root / SKILLS)
    for name in LAYOUT:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def _write(path: Path, text: str) -> None:
    """Written beside the target and renamed into place, so nobody reads half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.{uuid.uuid4().hex}.part")
    try:
        partial.write_text(text)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(
            flow, False
        )  # list items are indented under their setting, as people write them


def _long_text_as_block(dumper: yaml.SafeDumper, value: str):
    # a description with line breaks reads as written instead of as one quoted line full of \n
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


_Dumper.add_representer(str, _long_text_as_block)


def _dump(data: dict[str, Any]) -> str:
    return yaml.dump(
        data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
    )


def _load(text: str, what: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as e:
        problem = getattr(e, "problem", None) or "it is not valid"
        line = f" (line {e.problem_mark.line + 1})" if getattr(e, "problem_mark", None) else ""
        raise ConfigError(f"The {what} cannot be read{line}: {problem}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"The {what} must be a list of 'setting: value' lines")
    return {k: v for k, v in data.items() if v is not None}  # "model:" with nothing after it means "not set"


def _checked[T: BaseModel](model: type[T], data: dict[str, Any]) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0]
        where = ".".join(str(p) for p in err["loc"])
        if err["type"] == "extra_forbidden":
            raise ConfigError(f"'{where}' is not a setting here") from None
        raise ConfigError(
            f"{where}: {err['msg'].removeprefix('Value error, ')}" if where else err["msg"]
        ) from None


def split_frontmatter(text: str) -> tuple[str, str]:
    """The lines between the two --- lines at the top, and the text after them."""
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    if lines[0].strip() != "---":
        raise ConfigError("The file must start with a --- line, then the settings, then another --- line")
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ConfigError("The first --- line is never closed: add a --- line after the settings")
    body = "\n".join(lines[end + 1 :])
    return "\n".join(lines[1:end]), body.removeprefix("\n").removesuffix("\n")


# ----- agents -----


class FolderRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    mode: Literal["ro", "rw"] = "rw"


class AgentFile(BaseModel):
    """An agent.md, by names (a row refers to the same things by id)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    harness: Literal["codex"] = "codex"
    model: str = Field(default="", max_length=100)
    reasoning_effort: Literal["", "low", "medium", "high"] = ""
    cell: ProfileOverrides | None = None
    folders: list[FolderRef] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=50)
    tools: list[str] = Field(default_factory=list, max_length=50)
    keys: list[str] = Field(default_factory=list, max_length=50)
    instructions: str = Field(default="", max_length=20_000)  # the text below the settings

    @field_validator("name", "role")
    @classmethod
    def trimmed(cls, v: str) -> str:
        return v.strip()

    @field_validator("name")
    @classmethod
    def named(cls, v: str) -> str:
        if not v:
            raise ValueError("The name cannot be empty")
        return v

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str) -> str:
        return clean_model_name(v)


def parse_agent(text: str) -> AgentFile:
    settings_text, body = split_frontmatter(text)
    data = _load(settings_text, "settings at the top of the file")
    if "instructions" in data:
        raise ConfigError("The instructions are the text below the settings, not a setting")
    return _checked(AgentFile, {**data, "instructions": body})


def render_agent(af: AgentFile) -> str:
    meta: dict[str, Any] = {
        "name": af.name,
        "role": af.role,
        "description": af.description,
        "harness": af.harness,
        "model": af.model,
        "reasoning_effort": af.reasoning_effort,
    }
    if af.cell and (cell := af.cell.clean()):
        meta["cell"] = cell  # left out when the agent just uses the project's cell
    meta["folders"] = [f.model_dump() for f in af.folders]
    meta["skills"], meta["tools"], meta["keys"] = af.skills, af.tools, af.keys
    return f"---\n{_dump(meta)}---\n\n{af.instructions}\n" if af.instructions else f"---\n{_dump(meta)}---\n"


# ----- tool servers -----


class McpFile(BaseModel):
    """A mcp/<name>.yaml. The name is the file's name, so a tool cannot be called one thing and filed as another."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(default="", max_length=2000)
    kind: Literal["stdio", "http"] = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    keys: dict[str, str] = Field(default_factory=dict)  # environment variable -> the name of a stored key
    bearer_key: str = ""  # http: the stored key sent as a bearer token

    @field_validator("args", mode="before")
    @classmethod
    def args_as_text(cls, v: Any) -> Any:
        return [str(a) for a in v] if isinstance(v, list) else v  # `- 8080` is a number to YAML

    @field_validator("env", mode="before")
    @classmethod
    def values_as_text(cls, v: Any) -> Any:
        return {k: str(x) for k, x in v.items()} if isinstance(v, dict) else v


def parse_mcp(text: str) -> McpFile:
    return _checked(McpFile, _load(text, "file"))


def render_mcp(mf: McpFile) -> str:
    meta: dict[str, Any] = {"description": mf.description, "kind": mf.kind}
    if mf.kind == "http":
        meta["url"] = mf.url
        if mf.bearer_key:
            meta["bearer_key"] = mf.bearer_key
    else:
        meta["command"], meta["args"] = mf.command, mf.args
        if mf.env:
            meta["env"] = mf.env
        if mf.keys:
            meta["keys"] = mf.keys
    return _dump(meta)


# ----- the names a file uses, and what they point at -----


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
)


def agent_fields(af: AgentFile, refs: Refs, actor: User | None, before: Agent | None) -> dict[str, Any]:
    """The columns of an agent row that this file stands for, or a ConfigError saying what is wrong."""
    modes = {f.name: f.mode for f in af.folders}
    folder_ids = _look_up([f.name for f in af.folders], refs.folders, "folder")
    keys = _look_up(af.keys, refs.keys, "key", "")
    _keys_only_for_admins(actor, set(keys), set(before.secrets) if before else set(), "an agent")
    if gone := [s for s in dict.fromkeys(af.skills) if s not in refs.skills]:
        raise ConfigError(f"The skill '{gone[0]}' does not exist in this project")
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
    )


# ----- paths -----


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-") or "agent"


def _taken_slugs(project_id: int, rows: list[Agent], own: str) -> set[str]:
    """Agent folder names in use, by a row or on disk, other than `own` (the folder of the agent being named)."""
    taken = {Path(a.path).parent.name for a in rows if a.path}
    folder = config_dir(project_id) / AGENTS
    return (taken | ({p.name for p in folder.iterdir()} if folder.is_dir() else set())) - {own}


def _free_slug(base: str, taken: set[str]) -> str:
    slug, n = base, 1
    while slug in taken:
        n += 1
        slug = f"{base[: 40 - len(str(n)) - 1]}-{n}"
    return slug


def agent_path(slug: str) -> str:
    return f"{AGENTS}/{slug}/{AGENT_FILE}"


def mcp_path(name: str) -> str:
    return f"{MCP}/{name}.yaml"


# ----- writing a row's file (the API changed the row) -----


async def write_agent(session: AsyncSession, agent: Agent, *, renamed: bool = False) -> None:
    """Writes the agent's file from its row. The caller commits, and holds `lock`.

    A new agent's folder is named after it. An existing agent's folder only follows when the agent was `renamed`: a
    folder a person named or moved by hand keeps the name they gave it."""
    root = ensure_layout(agent.project_id)
    rows = list((await session.scalars(select(Agent).where(Agent.project_id == agent.project_id))).all())
    current = Path(agent.path).parent.name if agent.path else ""
    taken = _taken_slugs(agent.project_id, rows, own=current)
    wanted = _free_slug(slugify(agent.name), taken)
    if (
        current
        and current != wanted
        and (root / AGENTS / current).is_dir()
        and not (root / AGENTS / wanted).exists()
    ):
        (root / AGENTS / current).rename(root / AGENTS / wanted)  # the folder follows the agent's name
        current = wanted
    agent.path = agent_path(current or wanted)
    agent.config_error = ""
    refs = await load_refs(session, agent.project_id)
    _write(root / agent.path, render_agent(agent_file(agent, refs)))


def remove_agent_file(agent: Agent) -> None:
    """Takes the agent's file away, and its folder when nothing else was put in it."""
    if not agent.path:
        return
    path = config_dir(agent.project_id) / agent.path
    path.unlink(missing_ok=True)
    with contextlib.suppress(OSError):  # not empty (a person keeps notes there), or already gone
        path.parent.rmdir()


async def write_mcp(session: AsyncSession, server: McpServer) -> None:
    """Writes the tool's file from its row, named after the tool. The caller commits, and holds `lock`."""
    root = ensure_layout(server.project_id)
    wanted = mcp_path(server.name)
    if (
        server.path
        and server.path != wanted
        and (root / server.path).is_file()
        and not (root / wanted).exists()
    ):
        (root / server.path).rename(root / wanted)
    server.path = wanted
    server.config_error = ""
    refs = await load_refs(session, server.project_id)
    _write(root / wanted, render_mcp(mcp_file(server, refs)))


def remove_mcp_file(server: McpServer) -> None:
    if server.path:
        (config_dir(server.project_id) / server.path).unlink(missing_ok=True)


async def rewrite_agents(session: AsyncSession, agents: list[Agent]) -> None:
    """Writes the files of agents whose rows were just changed (a skill, tool, folder or key they had was deleted).
    An agent whose file could not be read is left alone: writing it would replace what the person wrote."""
    for agent in agents:
        if not agent.config_error:
            await write_agent(session, agent)


# ----- reading files into rows -----


def _apply(row: Agent | McpServer, fields: dict[str, Any]) -> None:
    for key, value in fields.items():
        if getattr(row, key) != value:  # untouched columns stay untouched, so updated_at means something
            setattr(row, key, value)
    row.config_error = ""


async def sync_project(session: AsyncSession, project_id: int) -> None:
    """Brings the rows in line with the files. Cheap enough to call before every read: a few small files."""
    async with lock:
        try:
            await _sync(session, project_id)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            log.exception("Could not sync the config of project %s", project_id)


async def _sync(session: AsyncSession, project_id: int) -> None:
    root = ensure_layout(project_id)
    mcp_rows = list(
        (await session.scalars(select(McpServer).where(McpServer.project_id == project_id))).all()
    )
    agent_rows = list((await session.scalars(select(Agent).where(Agent.project_id == project_id))).all())

    # rows from before the files existed get theirs now (tools first: agent files name them)
    for server in (s for s in mcp_rows if not s.path):
        await write_mcp(session, server)
    refs = await load_refs(session, project_id)
    for agent in (a for a in agent_rows if not a.path):
        await write_agent(session, agent)

    # tools: the file's name is the tool's name
    seen: set[str] = set()
    by_path = {s.path: s for s in mcp_rows}
    for file in sorted((root / MCP).glob("*.yaml")):
        name, path = file.stem, mcp_path(file.stem)
        if not NAME.match(name) or not file.is_file():
            continue
        seen.add(path)
        row = by_path.get(path)
        try:
            fields = mcp_fields(name, parse_mcp(file.read_text(errors="replace")), refs, None, row)
        except ConfigError as e:
            if row is not None:
                row.config_error = str(e)
            else:
                log.warning("Ignoring %s of project %s: %s", path, project_id, e)
            continue
        if row is None:
            row = McpServer(project_id=project_id, name=name, path=path)
            session.add(row)
            mcp_rows.append(row)
        _apply(row, fields)
    for row in mcp_rows:
        if row.path not in seen:
            row.config_error = "Its file is missing from the config folder"
    await session.flush()
    refs = await load_refs(session, project_id)

    # agents
    seen = set()
    by_path = {a.path: a for a in agent_rows}
    for file in sorted((root / AGENTS).glob(f"*/{AGENT_FILE}")):
        path = agent_path(file.parent.name)
        if not file.is_file() or not SLUG.match(file.parent.name):
            continue
        seen.add(path)
        row = by_path.get(path)
        try:
            af = parse_agent(file.read_text(errors="replace"))
            fields = agent_fields(af, refs, None, row)
        except ConfigError as e:
            if row is not None:
                row.config_error = str(e)
            else:
                log.warning("Ignoring %s of project %s: %s", path, project_id, e)
            continue
        if row is None:
            # a folder that was moved: its agent keeps its identity, found by the name its file still has
            row = next(
                (
                    a
                    for a in agent_rows
                    if a.name == af.name and a.path not in seen and not (root / a.path).is_file()
                ),
                None,
            )
            if row is None:
                row = Agent(project_id=project_id)
                session.add(row)
                agent_rows.append(row)
            row.path = path
        if any(a is not row and a.name == fields["name"] for a in agent_rows):
            row.config_error = f"Another agent is already called '{fields['name']}'"
            continue
        _apply(row, fields)
    for row in agent_rows:
        if row.path and row.path not in seen:
            row.config_error = "Its file is missing from the config folder"


async def sync_all_configs(maker) -> None:
    """At startup: every project's agents and tools are read from their files (and written, for projects from before
    the files existed), so nothing needs to be opened first."""
    async with maker() as session:
        for project_id in (await session.scalars(select(Project.id))).all():
            await sync_project(session, project_id)


# ----- checking a file before it is saved (the Files page) -----


async def validate_write(session: AsyncSession, project_id: int, rel: str, text: str, actor: User) -> None:
    """Refuses a config file that could not work, with a reason. Files of other kinds (notes, scripts) pass."""
    parts = [p for p in rel.split("/") if p]
    if len(parts) == 3 and parts[0] == SKILLS and parts[2] == skill_store.SKILL_FILE:
        try:
            skill_store.validate(parts[1], text)
        except skill_store.SkillError as e:
            raise ConfigError(str(e)) from None
    elif len(parts) == 3 and parts[0] == AGENTS and parts[2] == AGENT_FILE:
        if not SLUG.match(parts[1]):
            raise ConfigError("The agent's folder is named with lowercase letters, digits and dashes")
        refs = await load_refs(session, project_id)
        rows = list((await session.scalars(select(Agent).where(Agent.project_id == project_id))).all())
        before = next((a for a in rows if a.path == rel), None)
        af = parse_agent(text)
        agent_fields(af, refs, actor, before)
        root = config_dir(project_id)
        # an agent whose file is gone may be taken over by a moved file with its name; any other clash is a mistake
        if any(a is not before and a.name == af.name and a.path and (root / a.path).is_file() for a in rows):
            raise ConfigError(f"Another agent is already called '{af.name}'")
    elif len(parts) == 2 and parts[0] == MCP and parts[1].endswith(".yaml"):
        name = parts[1].removesuffix(".yaml")
        if not NAME.match(name):
            raise ConfigError("A tool's file is named with lowercase letters, digits and dashes")
        refs = await load_refs(session, project_id)
        before = await session.scalar(
            select(McpServer).where(McpServer.project_id == project_id, McpServer.path == rel)
        )
        mcp_fields(name, parse_mcp(text), refs, actor, before)


def is_validated(rel: str) -> bool:
    """Whether a file at this path in the config folder has a format that is checked when it is saved."""
    parts = [p for p in rel.split("/") if p]
    return (
        (len(parts) == 3 and parts[0] == SKILLS and parts[2] == skill_store.SKILL_FILE)
        or (len(parts) == 3 and parts[0] == AGENTS and parts[2] == AGENT_FILE)
        or (len(parts) == 2 and parts[0] == MCP and parts[1].endswith(".yaml"))
    )


def is_layout_folder(rel: str) -> bool:
    """The three folders Themis relies on: renaming or deleting one would break everything in it."""
    return rel.strip("/") in LAYOUT
