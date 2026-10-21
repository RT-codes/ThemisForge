"""Tool servers (MCP) of a project, and the keys that can be given to agents. See app/mcp.py and app/keys.py."""

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import mcp_catalog, mcp_registry, project_config
from ..app_settings import load_settings
from ..crypto import decrypt
from ..deps import AdminUser, CurrentUser, SessionDep
from ..keys import unique_env_names
from ..mcp import McpIn, probe_http
from ..mcp_auth import ACTIVE, AuthProblem, detect, login_for
from ..models import Agent, McpServer, Project, Secret, utcnow
from ..toolcheck import image_for, missing_commands
from .mcp_auth import ToolSignIn, tool_sign_ins
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
    auth: str  # how the server signs people in ("" when it does not), see app/mcp_auth
    sign_in: ToolSignIn | None = None  # where that stands for the project's owner, when the tool signs in
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


async def _present(session, project: Project, servers: list[McpServer]) -> list[McpOut]:
    """Tools as the API returns them: the stored fields, and for a tool that signs in where its sign in stands for
    the project's owner (the one runs use)."""
    states = await tool_sign_ins(session, project.owner_id, servers)
    out = []
    for server in servers:
        item = McpOut.model_validate(server)
        item.sign_in = states.get(server.id)
        out.append(item)
    return out


@router.get("/projects/{project_id}/mcp-servers", response_model=list[McpOut])
async def list_servers(project_id: int, session: SessionDep, user: CurrentUser) -> list[McpOut]:
    project = await _project(session, project_id, user)
    await project_config.sync_project(
        session, project_id
    )  # a file may have been edited in the Files page or on disk
    rows = await session.scalars(
        select(McpServer).where(McpServer.project_id == project_id).order_by(McpServer.name)
    )
    return await _present(session, project, list(rows.all()))


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
    # BaseException on purpose: a cancelled request must not leave a half-written config
    except BaseException:
        await session.rollback()
        raise


@router.post("/projects/{project_id}/mcp-servers", response_model=McpOut, status_code=status.HTTP_201_CREATED)
async def create_server(project_id: int, body: McpIn, session: SessionDep, user: CurrentUser) -> McpOut:
    project = await _project(session, project_id, user)
    await _check_keys(session, body, user)
    async with project_config.lock:
        server = McpServer(project_id=project_id, **body.model_dump())
        session.add(server)
        await _save(session, server)
    return (await _present(session, project, [server]))[0]


@router.put("/mcp-servers/{server_id}", response_model=McpOut)
async def replace_server(server_id: int, body: McpIn, session: SessionDep, user: CurrentUser) -> McpOut:
    server, project = await _server(session, server_id, user)
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
    return (await _present(session, project, [server]))[0]


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
async def test_server(server_id: int, request: Request, session: SessionDep, user: CurrentUser) -> ProbeOut:
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
        elif server.auth:
            # The token is the project owner's sign in for this exact address, so it cannot be sent anywhere else
            login = await login_for(session, project.owner_id, server.url)
            if login is None or login.status != ACTIVE:
                note = " Tested without signing in: the project's owner has not signed in to this tool."
            else:
                try:
                    bearer = await request.app.state.mcp_logins.bearer(login.id)
                except AuthProblem as e:
                    note = f" Tested without signing in: {e}"
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


# ----- adding tools from the MCP registry (see app/mcp_registry.py) -----


class CategoryOut(BaseModel):
    id: str
    label: str
    count: int  # of the tools matching the search (before the category is applied)


class CatalogStatus(BaseModel):
    state: str  # empty | building | updating | ready | error
    count: int
    synced_at: str
    error: str
    counting: bool  # npm download counts are still being fetched


class RegistryPage(BaseModel):
    tools: list[mcp_registry.RegistryTool]
    total: int  # matching the search and filters
    offset: int
    categories: list[CategoryOut]
    status: CatalogStatus


class PrefillIn(BaseModel):
    name: str  # the registry's name for the tool
    values: dict[str, str] = {}  # input id -> what was filled in (a key's id for a secret)


async def _runners(session, project: Project | None) -> frozenset[str] | None:
    """The programs the project's cell image can start a tool with (None when that cannot be known). Without a
    project it is the image agents use by default."""
    cfg = await load_settings(session)
    return await mcp_registry.available_runners(image_for(project, cfg, "codex", None), cfg.docker_host)


async def _optional_project(session, project_id: int | None, user) -> Project | None:
    """The registry can be browsed from a project, and from Settings where there is none (then `project_id` is None)."""
    return await _project(session, project_id, user) if project_id is not None else None


def _with_catalog_facts(tool: mcp_registry.RegistryTool, entry: dict) -> mcp_registry.RegistryTool:
    """What the browser shows beside a tool (icon, category, downloads) for one looked up on its own: from the
    catalog's row when it has one, else worked out from the entry."""
    row = mcp_catalog.catalog.rows.get(tool.name) or mcp_catalog.make_row({"server": entry})
    if row:
        tool.icon, tool.category = mcp_catalog.icon_url(row), row.category
        tool.downloads, tool.updated = row.downloads, row.updated
    return tool


def _unavailable(e: mcp_registry.RegistryUnavailable) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"{e} You can still add a tool by hand.")


# Only administrators browse the registry for now: a tool from it is a package or address nobody here has looked at.
@router.get("/mcp-registry", response_model=RegistryPage)
@router.get("/projects/{project_id}/mcp-registry", response_model=RegistryPage)
async def browse_registry(
    session: SessionDep,
    user: AdminUser,
    q: str = "",
    category: str = "",
    sort: str = "recommended",
    supported_only: bool = False,
    offset: int = 0,
    limit: int = 30,
    project_id: int | None = None,
) -> RegistryPage:
    """A page of the local copy of the registry's catalog (see app/mcp_catalog.py). The first call after install
    starts building that copy in the background, and says so in `status` until it is there."""
    project = await _optional_project(session, project_id, user)
    await mcp_catalog.catalog.ensure_current()
    available = await _runners(session, project)
    offset = max(offset, 0)
    page = await asyncio.to_thread(
        mcp_catalog.catalog.browse,
        q=q[:100],
        category=category[:40],
        sort=sort if sort in mcp_catalog.SORTS else "recommended",
        supported_only=supported_only,
        offset=offset,
        limit=min(max(limit, 1), 60),
        available=available,
        featured=frozenset(n for n, _ in mcp_registry.featured_names()),
    )
    return RegistryPage(
        tools=[mcp_catalog.catalog.as_tool(row, way) for row, way in page.rows],
        total=page.total,
        offset=offset,
        categories=[CategoryOut(id=i, label=label, count=n) for i, label, n in page.categories],
        status=CatalogStatus(**mcp_catalog.catalog.status()),
    )


@router.post("/mcp-registry/refresh", response_model=CatalogStatus)
@router.post("/projects/{project_id}/mcp-registry/refresh", response_model=CatalogStatus)
async def refresh_registry(
    session: SessionDep, user: AdminUser, project_id: int | None = None
) -> CatalogStatus:
    """Reads what changed in the registry now, instead of waiting for the daily update."""
    await _optional_project(session, project_id, user)
    catalog = mcp_catalog.catalog
    await catalog.load()
    if not (catalog.task and not catalog.task.done()):
        catalog.failed_at = 0.0
        catalog.task = asyncio.create_task(catalog.sync(full=not catalog.rows))
    return CatalogStatus(**catalog.status())


@router.get("/mcp-registry/entry", response_model=mcp_registry.RegistryTool)
@router.get("/projects/{project_id}/mcp-registry/entry", response_model=mcp_registry.RegistryTool)
async def registry_entry(name: str, session: SessionDep, user: AdminUser, project_id: int | None = None):
    """One tool with everything to fill in for it (the list leaves that out)."""
    project = await _optional_project(session, project_id, user)
    try:
        entry = await mcp_registry.get_entry(name)
    except mcp_registry.RegistryUnavailable as e:
        raise _unavailable(e) from e
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The registry has no tool with that name")
    return _with_catalog_facts(mcp_registry.to_tool(entry, await _runners(session, project)), entry)


@router.get("/mcp-registry/featured", response_model=list[mcp_registry.RegistryTool])
@router.get("/projects/{project_id}/mcp-registry/featured", response_model=list[mcp_registry.RegistryTool])
async def featured_registry_tools(
    session: SessionDep, user: AdminUser, project_id: int | None = None
) -> list[mcp_registry.RegistryTool]:
    project = await _optional_project(session, project_id, user)
    try:
        found = await mcp_registry.featured()
    except mcp_registry.RegistryUnavailable as e:
        raise _unavailable(e) from e
    available = await _runners(session, project)
    return [_with_catalog_facts(mcp_registry.to_tool(e, available, note), e) for e, note in found]


@router.post("/mcp-registry/prefill", response_model=McpIn)
@router.post("/projects/{project_id}/mcp-registry/prefill", response_model=McpIn)
async def prefill_from_registry(
    body: PrefillIn, session: SessionDep, user: AdminUser, project_id: int | None = None
) -> McpIn:
    """The fields of a tool for a registry entry and the person's answers. Nothing is saved: the form that opens with
    them creates the tool like any other, so every check on creating a tool applies."""
    project = await _optional_project(session, project_id, user)
    try:
        entry = await mcp_registry.get_entry(body.name)
    except mcp_registry.RegistryUnavailable as e:
        raise _unavailable(e) from e
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The registry has no tool with that name")
    try:
        tool = mcp_registry.build_tool(entry, body.values, await _runners(session, project))
    except ValueError as e:  # includes MissingInput
        raise _bad(str(e)) from e
    await _check_keys(session, tool, user)
    if tool.kind == "http" and tool.bearer_secret_id is None and not tool.auth:
        # A hosted server that wants people to sign in says so when asked; the form then opens set up for it
        tool.auth = await detect(tool.url, (await load_settings(session)).mcp_auth)
    return tool
