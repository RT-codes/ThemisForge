from fastapi import APIRouter, Request, status

import app.features.tools.registry as mcp_registry
import app.features.tools.service as operations
from app.api.dependencies import AdminUser, CurrentUser, SessionDep
from app.features.tools.mcp import McpIn
from app.features.tools.schemas import CatalogStatus, KeyOut, McpOut, PrefillIn, ProbeOut, RegistryPage

router = APIRouter(tags=["tools"])


@router.get("/keys", response_model=list[KeyOut])
async def available_keys(session: SessionDep, _: CurrentUser) -> list[KeyOut]:
    """The names of the stored keys (never their values) and how an agent sees each one."""

    return await operations.available_keys(session, _)


@router.get("/projects/{project_id}/mcp-servers", response_model=list[McpOut])
async def list_servers(project_id: int, session: SessionDep, user: CurrentUser) -> list[McpOut]:
    return await operations.list_servers(project_id, session, user)


@router.post("/projects/{project_id}/mcp-servers", response_model=McpOut, status_code=status.HTTP_201_CREATED)
async def create_server(project_id: int, body: McpIn, session: SessionDep, user: CurrentUser) -> McpOut:
    return await operations.create_server(project_id, body, session, user)


@router.put("/mcp-servers/{server_id}", response_model=McpOut)
async def replace_server(server_id: int, body: McpIn, session: SessionDep, user: CurrentUser) -> McpOut:
    return await operations.replace_server(server_id, body, session, user)


@router.delete("/mcp-servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Removes the tool from the project and from the agents that had it."""

    return await operations.delete_server(server_id, session, user)


@router.post("/mcp-servers/{server_id}/test", response_model=ProbeOut)
async def test_server(server_id: int, request: Request, session: SessionDep, user: CurrentUser) -> ProbeOut:
    """Can the project reach this tool? A web tool is connected to and asked what it offers. A command is looked up in
    the image agents run in (it is only started when an agent runs, which needs a whole cell)."""

    return await operations.test_server(server_id, request.app.state, session, user)


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

    return await operations.browse_registry(
        session, user, q, category, sort, supported_only, offset, limit, project_id
    )


@router.post("/mcp-registry/refresh", response_model=CatalogStatus)
@router.post("/projects/{project_id}/mcp-registry/refresh", response_model=CatalogStatus)
async def refresh_registry(
    session: SessionDep, user: AdminUser, project_id: int | None = None
) -> CatalogStatus:
    """Reads what changed in the registry now, instead of waiting for the daily update."""

    return await operations.refresh_registry(session, user, project_id)


@router.get("/mcp-registry/entry", response_model=mcp_registry.RegistryTool)
@router.get("/projects/{project_id}/mcp-registry/entry", response_model=mcp_registry.RegistryTool)
async def registry_entry(name: str, session: SessionDep, user: AdminUser, project_id: int | None = None):
    """One tool with everything to fill in for it (the list leaves that out)."""

    return await operations.registry_entry(name, session, user, project_id)


@router.get("/mcp-registry/featured", response_model=list[mcp_registry.RegistryTool])
@router.get("/projects/{project_id}/mcp-registry/featured", response_model=list[mcp_registry.RegistryTool])
async def featured_registry_tools(
    session: SessionDep, user: AdminUser, project_id: int | None = None
) -> list[mcp_registry.RegistryTool]:
    return await operations.featured_registry_tools(session, user, project_id)


@router.post("/mcp-registry/prefill", response_model=McpIn)
@router.post("/projects/{project_id}/mcp-registry/prefill", response_model=McpIn)
async def prefill_from_registry(
    body: PrefillIn, session: SessionDep, user: AdminUser, project_id: int | None = None
) -> McpIn:
    """The fields of a tool for a registry entry and the person's answers. Nothing is saved: the form that opens with
    them creates the tool like any other, so every check on creating a tool applies."""

    return await operations.prefill_from_registry(body, session, user, project_id)
