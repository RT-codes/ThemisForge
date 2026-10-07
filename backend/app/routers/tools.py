"""Tool servers (MCP) of a project, and the keys that can be given to agents. See app/mcp.py and app/keys.py."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import project_config
from ..app_settings import load_settings
from ..crypto import decrypt
from ..deps import CurrentUser, SessionDep
from ..keys import unique_env_names
from ..mcp import McpIn, probe_http
from ..models import Agent, McpServer, Project, Secret, utcnow
from ..toolcheck import image_for, missing_commands
from .projects import _bad, _project

router = APIRouter(tags=["tools"])


class McpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str
    kind: str
    command: str
    args: list[str]
    url: str
    env: dict[str, str]
    secret_env: dict[str, int]
    bearer_secret_id: int | None
    path: str  # the tool's file in the project's config folder
    config_error: str  # why that file cannot be used right now ("" when it is fine)
    last_test: dict | None  # the latest connection test, see test_server
    created_at: datetime


class KeyOut(BaseModel):
    id: int
    name: str
    kind: str
    env_name: str  # the variable an agent finds it in


async def _server(session, server_id: int, user) -> tuple[McpServer, Project]:
    server = await session.get(McpServer, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tool not found")
    return server, await _project(session, server.project_id, user)


async def _check_keys(session, body: McpIn, user, before: McpServer | None = None) -> None:
    """The keys a tool refers to must exist, and only an administrator may point a tool at a different key."""
    ids = set(body.secret_env.values()) | ({body.bearer_secret_id} if body.bearer_secret_id else set())
    if ids:
        found = set(await session.scalars(select(Secret.id).where(Secret.id.in_(ids))))
        if gone := ids - found:
            raise _bad(f"Key {min(gone)} does not exist")
    old = set()
    if before is not None:
        old = set(before.secret_env.values()) | (
            {before.bearer_secret_id} if before.bearer_secret_id else set()
        )
    if ids != old and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can give a tool access to keys")


@router.get("/keys", response_model=list[KeyOut])
async def available_keys(session: SessionDep, _: CurrentUser) -> list[KeyOut]:
    """The names of the stored keys (never their values) and how an agent sees each one."""
    rows = list((await session.scalars(select(Secret).order_by(Secret.id))).all())
    names = unique_env_names([(r.id, r.name) for r in rows])
    return [KeyOut(id=r.id, name=r.name, kind=r.kind, env_name=names[r.id]) for r in rows]


@router.get("/projects/{project_id}/mcp-servers", response_model=list[McpOut])
async def list_servers(project_id: int, session: SessionDep, user: CurrentUser) -> list[McpServer]:
    await _project(session, project_id, user)
    await project_config.sync_project(
        session, project_id
    )  # a file may have been edited in the Files page or on disk
    return list(
        (
            await session.scalars(
                select(McpServer).where(McpServer.project_id == project_id).order_by(McpServer.name)
            )
        ).all()
    )


async def _save(session, server: McpServer) -> None:
    """Commits a tool row together with its file (the caller holds the config lock). The row goes first, so a name
    that is taken is refused before any file is written."""
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This project already has a tool with that name"
        ) from None
    try:
        await project_config.write_mcp(session, server)
        await session.commit()
    except BaseException:
        await session.rollback()
        raise


@router.post("/projects/{project_id}/mcp-servers", response_model=McpOut, status_code=status.HTTP_201_CREATED)
async def create_server(project_id: int, body: McpIn, session: SessionDep, user: CurrentUser) -> McpServer:
    await _project(session, project_id, user)
    await _check_keys(session, body, user)
    async with project_config.lock:
        server = McpServer(project_id=project_id, **body.model_dump())
        session.add(server)
        await _save(session, server)
    return server


@router.put("/mcp-servers/{server_id}", response_model=McpOut)
async def replace_server(server_id: int, body: McpIn, session: SessionDep, user: CurrentUser) -> McpServer:
    server, _ = await _server(session, server_id, user)
    async with project_config.lock:
        await session.refresh(server)
        await _check_keys(session, body, user, before=server)
        renamed = body.name != server.name
        for key, value in body.model_dump().items():
            setattr(server, key, value)
        server.last_test = None  # what was tried is not what is saved any more
        await _save(session, server)
        if renamed:  # agent files name their tools, so the ones that use this one are written again
            agents = await session.scalars(select(Agent).where(Agent.project_id == server.project_id))
            await project_config.rewrite_agents(session, [a for a in agents if server.id in a.mcp_servers])
            await session.commit()
    return server


@router.delete("/mcp-servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Removes the tool from the project and from the agents that had it."""
    server, project = await _server(session, server_id, user)
    async with project_config.lock:
        changed = []
        for agent in await session.scalars(select(Agent).where(Agent.project_id == project.id)):
            if server.id in agent.mcp_servers:
                agent.mcp_servers = [i for i in agent.mcp_servers if i != server.id]
                changed.append(agent)
        project_config.remove_mcp_file(server)
        await session.delete(server)
        await session.flush()
        await project_config.rewrite_agents(session, changed)
        await session.commit()


class ProbeOut(BaseModel):
    ok: bool
    message: str
    tools: list[str]  # what the server offers (a web tool that answered)
    at: datetime


@router.post("/mcp-servers/{server_id}/test", response_model=ProbeOut)
async def test_server(server_id: int, session: SessionDep, user: CurrentUser) -> ProbeOut:
    """Can the project reach this tool? A web tool is connected to and asked what it offers. A command is looked up in
    the image agents run in (it is only started when an agent runs, which needs a whole cell)."""
    server, project = await _server(session, server_id, user)
    cfg = await load_settings(session)
    if server.kind == "http":
        bearer, note = None, ""
        if server.bearer_secret_id:
            if user.is_admin:  # a key is only ever sent where an administrator may send it
                secret = await session.get(Secret, server.bearer_secret_id)
                bearer = decrypt(secret.value_encrypted) if secret else None
            else:
                note = " Tested without its key: only an administrator can test with it."
        probe = await probe_http(server.url, bearer)
        ok, message, tools = probe.ok, probe.message + note, list(probe.tools)
    else:
        image = image_for(project, cfg, "codex", None)
        warnings = await missing_commands(image, {server.name: server.command}, cfg.docker_host)
        ok = not warnings
        message = (
            warnings[0]
            if warnings
            else f"'{server.command}' is available in {image}. It is started when an agent runs, not by this test."
        )
        tools = []
    result = ProbeOut(ok=ok, message=message, tools=tools, at=utcnow())
    server.last_test = {**result.model_dump(mode="json")}
    await session.commit()
    return result
