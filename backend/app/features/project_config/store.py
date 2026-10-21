import asyncio
import contextlib
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app.features.agents.skills as skill_store
from app.features.project_config.common import AGENT_FILE, AGENTS, LAYOUT, MCP, SKILLS, SLUG, ConfigError
from app.features.project_config.formats import parse_agent, parse_mcp, render_agent, render_mcp
from app.features.project_config.references import agent_fields, agent_file, load_refs, mcp_fields, mcp_file
from app.features.storage.volumes import config_dir
from app.features.tools.mcp import NAME
from app.persistence.models import Agent, McpServer, Project, User

log = logging.getLogger("app.project_config")


lock = asyncio.Lock()


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
        partial.write_text(text, encoding="utf-8", newline="\n")
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


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
            fields = mcp_fields(
                name, parse_mcp(file.read_text(encoding="utf-8", errors="replace")), refs, None, row
            )
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
            af = parse_agent(file.read_text(encoding="utf-8", errors="replace"))
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
