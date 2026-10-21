from dataclasses import asdict

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

import app.features.agents.skills as skill_store
import app.features.project_config.store as project_config
from app.errors import ApplicationError, invalid
from app.execution.harnesses.catalog import CATALOG, defaults_for
from app.features.agents.schemas import AgentIn, AgentPatch, CheckIn, CheckOut, HarnessOut
from app.features.connections.service import providers
from app.features.projects.access import require_project
from app.features.storage.volumes import MountRef
from app.features.system.settings import load_settings
from app.features.tools.toolcheck import image_for, missing_commands
from app.persistence.models import Agent, McpServer, Project, Secret, Task, TaskStatus, User, Volume


async def _agent(session, agent_id: int, user) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Agent not found")
    await require_project(session, agent.project_id, user)
    return agent


async def _mounts(session, project_id: int, refs: list[MountRef]) -> list[dict]:
    """The folders an agent mounts: each must belong to the project. Asking for one twice keeps the last."""
    by_id = {r.volume_id: r for r in refs}
    if by_id:
        found = set(
            await session.scalars(
                # the config folder is never mounted: it is where agents are set up
                select(Volume.id).where(
                    Volume.project_id == project_id, Volume.id.in_(list(by_id)), Volume.kind != "config"
                )
            )
        )
        if missing := set(by_id) - found:
            raise invalid(f"Folder {min(missing)} does not exist in this project")
    return [r.model_dump() for r in by_id.values()]


async def _capabilities(session, project_id: int, body, user, before: Agent | None = None) -> dict:
    """Checks and returns the skills, tool servers and keys an agent is given (only what the request sets).

    Skills and tool servers must exist in the project, keys must exist, and only an administrator may change which
    keys an agent has, because a key is paid for or trusted by the whole installation."""
    out: dict = {}
    if body.skills is not None:
        names = list(dict.fromkeys(body.skills))
        if gone := skill_store.missing(project_id, names):
            raise invalid(f"The skill '{gone[0]}' does not exist in this project")
        out["skills"] = names
    if body.mcp_servers is not None:
        ids = list(dict.fromkeys(body.mcp_servers))
        found = set(
            await session.scalars(
                select(McpServer.id).where(McpServer.project_id == project_id, McpServer.id.in_(ids))
            )
        )
        if gone := set(ids) - found:
            raise invalid(f"Tool {min(gone)} does not exist in this project")
        out["mcp_servers"] = ids
    if body.secrets is not None:
        ids = list(dict.fromkeys(body.secrets))
        found = set(await session.scalars(select(Secret.id).where(Secret.id.in_(ids)))) if ids else set()
        if gone := set(ids) - found:
            raise invalid(f"Key {min(gone)} does not exist")
        if set(ids) != set(before.secrets if before else []) and not user.is_admin:
            raise ApplicationError(status.HTTP_403_FORBIDDEN, "Only an administrator can give an agent keys")
        out["secrets"] = ids
    if body.connections is not None:
        names = list(dict.fromkeys(body.connections))
        if unknown := [n for n in names if n not in providers()]:
            raise invalid(f"Themis has no connection called '{unknown[0]}'")
        out["connections"] = names
    return out


async def check_agent_tools(project_id: int, body: CheckIn, session: AsyncSession, user: User) -> CheckOut:
    """Before saving: would the agent's tool servers start in the image it will run in?"""
    project: Project = await require_project(session, project_id, user)
    cfg = await load_settings(session)
    image = image_for(project, cfg, body.harness, body.cell_profile.clean() if body.cell_profile else None)
    commands = {}
    if body.mcp_servers:
        rows = await session.scalars(
            select(McpServer).where(
                McpServer.project_id == project_id,
                McpServer.id.in_(body.mcp_servers),
                McpServer.kind == "stdio",
            )
        )
        commands = {r.name: r.command for r in rows}
    return CheckOut(image=image, warnings=await missing_commands(image, commands, cfg.docker_host))


async def list_harnesses(session: AsyncSession, _: User) -> list[HarnessOut]:
    cfg = await load_settings(session)
    return [
        HarnessOut(
            **asdict(h),
            default_model=defaults_for(h.id, cfg)[1],
            default_effort=defaults_for(h.id, cfg)[2],
        )
        for h in CATALOG
    ]


async def list_agents(project_id: int, session: AsyncSession, user: User) -> list[Agent]:
    await require_project(session, project_id, user)
    await project_config.sync_project(
        session, project_id
    )  # a file may have been edited in the Files page or on disk
    return list(
        (
            await session.scalars(select(Agent).where(Agent.project_id == project_id).order_by(Agent.name))
        ).all()
    )


async def create_agent(project_id: int, body: AgentIn, session: AsyncSession, user: User) -> Agent:
    await require_project(session, project_id, user)
    async with project_config.lock:
        agent = Agent(
            project_id=project_id,
            name=body.name,
            role=body.role,
            description=body.description,
            instructions=body.instructions,
            harness=body.harness,
            model=body.model,
            reasoning_effort=body.reasoning_effort,
            cell_profile=body.cell_profile.clean() if body.cell_profile else None,
            mounts=await _mounts(session, project_id, body.mounts),
            **await _capabilities(session, project_id, body, user),
        )
        session.add(agent)
        await _save(session, agent)
    return agent


async def _save(session, agent: Agent, *, renamed: bool = False) -> None:
    """Commits an agent row together with its file (the caller holds the config lock). The row goes first, so a name
    that is taken is refused before any file is written."""
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise ApplicationError(
            status.HTTP_409_CONFLICT, "This project already has an agent with that name"
        ) from None
    try:
        await project_config.write_agent(session, agent, renamed=renamed)
        await session.commit()
    # BaseException on purpose: a cancelled request must not leave a half-written config
    except BaseException:
        await session.rollback()
        raise


async def get_agent(agent_id: int, session: AsyncSession, user: User) -> Agent:
    agent = await _agent(session, agent_id, user)
    await project_config.sync_project(session, agent.project_id)
    await session.refresh(agent)
    return agent


async def update_agent(agent_id: int, body: AgentPatch, session: AsyncSession, user: User) -> Agent:
    agent = await _agent(session, agent_id, user)
    async with project_config.lock:
        await session.refresh(agent)  # a sync may have changed it since it was loaded
        return await _update(session, agent, body, user)


async def _update(session, agent: Agent, body: AgentPatch, user) -> Agent:
    old_name = agent.name
    fields = body.model_fields_set
    for key in ("name", "role", "description", "instructions", "harness", "model", "reasoning_effort"):
        value = getattr(body, key)
        if key in fields and value is not None:
            setattr(agent, key, value.strip() if key in ("name", "role") else value)
    if not agent.name:
        raise invalid("Name cannot be empty")
    if "cell_profile" in fields:
        agent.cell_profile = body.cell_profile.clean() if body.cell_profile else None
    if "mounts" in fields and body.mounts is not None:
        agent.mounts = await _mounts(session, agent.project_id, body.mounts)
    for key, value in (await _capabilities(session, agent.project_id, body, user, before=agent)).items():
        setattr(agent, key, value)
    await _save(session, agent, renamed=agent.name != old_name)
    return agent


async def delete_agent(agent_id: int, session: AsyncSession, user: User) -> None:
    agent = await _agent(session, agent_id, user)
    running = await session.scalar(
        select(func.count()).where(Task.agent_id == agent.id, Task.status == TaskStatus.RUNNING)
    )
    if running:
        raise ApplicationError(status.HTTP_409_CONFLICT, "This agent is running a task. Cancel it first.")
    async with project_config.lock:
        project_config.remove_agent_file(agent)
        await session.delete(agent)
        await session.commit()
