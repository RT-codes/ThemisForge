"""Tool servers (MCP) of a project, and the keys that can be given to agents. See app/mcp.py and app/keys.py."""

import shlex
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..deps import CurrentUser, SessionDep
from ..keys import ENV_NAME, unique_env_names
from ..mcp import NAME
from ..models import Agent, McpServer, Project, Secret
from .projects import _bad, _project

router = APIRouter(tags=["tools"])


class McpIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    kind: Literal["stdio", "http"] = "stdio"
    command: str = Field(default="", max_length=1000)
    args: list[str] = Field(default_factory=list, max_length=50)
    url: str = Field(default="", max_length=2000)
    env: dict[str, str] = Field(default_factory=dict)
    secret_env: dict[str, int] = Field(default_factory=dict)  # environment variable -> key id
    bearer_secret_id: int | None = None  # http: a key sent as a bearer token

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str) -> str:
        v = v.strip().lower()
        if not NAME.match(v):
            raise ValueError("Use lowercase letters, digits and dashes, starting with a letter or digit")
        return v

    @field_validator("args")
    @classmethod
    def short_args(cls, v: list[str]) -> list[str]:
        if any(len(a) > 2000 for a in v):
            raise ValueError("An argument is too long")
        return v

    @field_validator("env", "secret_env")
    @classmethod
    def valid_variable_names(cls, v: dict) -> dict:
        if len(v) > 50 or any(not ENV_NAME.match(k) for k in v):
            raise ValueError("Environment variable names use letters, digits and underscores")
        return v

    @model_validator(mode="after")
    def valid_for_kind(self) -> "McpIn":
        if self.kind == "http":
            if not self.url.strip().startswith(("http://", "https://")):
                raise ValueError("A web tool needs a URL that starts with http:// or https://")
            self.url, self.command, self.args = self.url.strip(), "", []
            self.env, self.secret_env = {}, {}
        else:
            command = self.command.strip()
            if not command:
                raise ValueError(
                    "A tool needs the command that starts it, such as: npx -y @scope/some-server"
                )
            if not self.args and any(c.isspace() for c in command):
                parts = shlex.split(command)  # "npx -y pkg" typed into the command box
                command, self.args = parts[0], parts[1:]
            self.command, self.url, self.bearer_secret_id = command, "", None
        return self


class McpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    kind: str
    command: str
    args: list[str]
    url: str
    env: dict[str, str]
    secret_env: dict[str, int]
    bearer_secret_id: int | None
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
    return list(
        (
            await session.scalars(
                select(McpServer).where(McpServer.project_id == project_id).order_by(McpServer.name)
            )
        ).all()
    )


@router.post("/projects/{project_id}/mcp-servers", response_model=McpOut, status_code=status.HTTP_201_CREATED)
async def create_server(project_id: int, body: McpIn, session: SessionDep, user: CurrentUser) -> McpServer:
    await _project(session, project_id, user)
    await _check_keys(session, body, user)
    server = McpServer(project_id=project_id, **body.model_dump())
    session.add(server)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This project already has a tool with that name"
        ) from None
    return server


@router.put("/mcp-servers/{server_id}", response_model=McpOut)
async def replace_server(server_id: int, body: McpIn, session: SessionDep, user: CurrentUser) -> McpServer:
    server, _ = await _server(session, server_id, user)
    await _check_keys(session, body, user, before=server)
    for key, value in body.model_dump().items():
        setattr(server, key, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This project already has a tool with that name"
        ) from None
    return server


@router.delete("/mcp-servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Removes the tool from the project and from the agents that had it."""
    server, project = await _server(session, server_id, user)
    for agent in await session.scalars(select(Agent).where(Agent.project_id == project.id)):
        if server.id in agent.mcp_servers:
            agent.mcp_servers = [i for i in agent.mcp_servers if i != server.id]
    await session.delete(server)
    await session.commit()
