from datetime import datetime

from pydantic import BaseModel, ConfigDict

import app.features.tools.registry as mcp_registry
from app.features.tools.auth_schemas import ToolSignIn


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


class ProbeOut(BaseModel):
    ok: bool
    message: str
    tools: list[str]  # what the server offers (a web tool that answered)
    at: datetime


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
