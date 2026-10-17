"""The MCP control plane: how an agent outside a cell (Claude Code on this machine or another, later a run's own
agent) looks at and drives a project through the Model Context Protocol, served at /mcp by this same app.

There is one way into Themis's behaviour and it is the REST routers: a tool calls the same handler the web interface
does, as the project's owner, so every rule they check (ownership, validation, what a task may be) holds here without
being written twice. What this module adds is only who is asking and what they may reach:

- A request carries a control token (`Authorization: Bearer ...`, see ControlToken). The token names one project and a
  scope. Every tool is pinned to that project: an id that belongs to another one answers "not found", like a missing one.
- v1 has read tools only. `scope` is already part of the token so that write tools can come without making old tokens
  more powerful than they were when they were made.
- MCP is served stateless, one JSON answer per request: nothing is kept between calls, so a restart loses no session
  and there is nothing to expire.
"""

import functools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import HTTPException
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from .models import ControlToken, Project, User, utcnow
from .routers import agents, projects, workflows, workspaces
from .routers.agents import AgentOut
from .routers.workflows import WorkflowSummary
from .schemas import (
    AttemptDetail,
    AttemptOut,
    ProjectOut,
    TaskOut,
    UsageRow,
    WorkspaceOut,
)
from .security import hash_secret

INSTRUCTIONS = (
    "Themis runs AI agents as tasks in throwaway containers. This connection is limited to one project. Start with "
    "get_project and list_boards to learn its boards and statuses, then list_tasks and get_task for the work, and "
    "get_attempt to read how a run went. get_usage shows what the runs spent."
)
NOT_FOUND = "Not found in this project"
LAST_USED_EVERY = timedelta(minutes=1)  # so a busy agent does not make a write of every read


@dataclass(frozen=True)
class Caller:
    """Who is asking: what a control token stands for."""

    token_id: int
    project_id: int
    owner_id: int  # the tools act as this user
    scope: str


# set while a request is handled, for the tools to read
_caller: ContextVar[Caller] = ContextVar("control_caller")


def bearer(scope: Scope) -> str:
    """The token from the Authorization header, '' when there is none."""
    for name, value in scope["headers"]:
        if name == b"authorization":
            kind, _, token = value.decode("latin-1").partition(" ")
            return token.strip() if kind.lower() == "bearer" else ""
    return ""


class ControlPlane:
    """The /mcp endpoint of one app: checks the token, then hands the request to the MCP server."""

    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self.maker = maker
        self.server = MCPServer("Themis", instructions=INSTRUCTIONS)
        self._register_tools()
        self._app = self.server.streamable_http_app(
            streamable_http_path="/",
            stateless_http=True,
            json_response=True,
            # The SDK would only answer to a Host of localhost. Themis is reached under whatever name its machine has,
            # and the token, which a web page cannot add to a request, is what keeps other pages out.
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )

    @asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        """Keep this open for as long as the app serves requests (the SDK's session manager needs it)."""
        async with self._app.router.lifespan_context(self._app):
            yield

    async def authenticate(self, token: str) -> Caller | None:
        if not token:
            return None
        async with self.maker() as s:
            row = await s.scalar(select(ControlToken).where(ControlToken.token_hash == hash_secret(token)))
            project = await s.get(Project, row.project_id) if row else None
            if row is None or project is None:
                return None
            now = utcnow()
            if row.last_used_at is None or now - row.last_used_at > LAST_USED_EVERY:
                row.last_used_at = now
                await s.commit()
            return Caller(row.id, row.project_id, project.owner_id, row.scope)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        caller = await self.authenticate(bearer(scope))
        if caller is None:
            reply = JSONResponse(
                {"error": "Missing or unknown control token"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="themis"'},
            )
            await reply(scope, receive, send)
            return
        _caller.set(caller)
        # The server answers on "/" of its own, so /mcp is served without the redirect a mounted app would add
        await self._app({**scope, "path": "/", "raw_path": b"/"}, receive, send)

    # the tools

    @asynccontextmanager
    async def _acting(self) -> AsyncIterator[tuple[AsyncSession, User, Caller]]:
        caller = _caller.get()
        async with self.maker() as s:
            owner = await s.get(User, caller.owner_id)
            if owner is None:  # the project's owner was removed while the token lived on
                raise ToolError(NOT_FOUND)
            yield s, owner, caller

    @staticmethod
    async def _task_in_project(s: AsyncSession, owner: User, caller: Caller, task_id: int) -> TaskOut:
        """A task of the token's project, or 'not found' (also for another project's task, so ids tell nothing)."""
        task = await projects.get_task(task_id, s, owner)
        if task.project_id != caller.project_id:
            raise ToolError(NOT_FOUND)
        return task

    def _tool(self, fn):
        """Register a tool, with the failures of the REST handlers it calls turned into the tool's own errors."""

        @functools.wraps(fn)
        async def run(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except HTTPException as e:
                # a missing id and another project's id get the same answer, so ids tell nothing about other projects
                raise ToolError(NOT_FOUND if e.status_code == 404 else str(e.detail)) from None

        self.server.tool()(run)
        return fn

    def _register_tools(self) -> None:
        tool = self._tool

        @tool
        async def get_project() -> ProjectOut:
            """The project this connection is for: its name, purpose, description and custom task properties."""
            async with self._acting() as (s, owner, caller):
                return ProjectOut.model_validate(await projects.get_project(caller.project_id, s, owner))

        @tool
        async def list_boards() -> list[WorkspaceOut]:
            """The project's workspaces with their boards and the statuses of each board. A task's board_id and
            status refer to these."""
            async with self._acting() as (s, owner, caller):
                return await workspaces.list_workspaces(caller.project_id, s, owner)

        @tool
        async def list_tasks(
            board_id: int | None = None,
            status: str | None = None,
            limit: Annotated[int, Field(ge=1, le=500)] = 100,
        ) -> list[TaskOut]:
            """Tasks of the project in board order, optionally only one board's or one status's. Steps made by
            workflow runs are left out."""
            async with self._acting() as (s, owner, caller):
                tasks = await projects.list_tasks(
                    caller.project_id, s, owner, board_id=board_id, include_steps=False
                )
                if status is not None:
                    tasks = [t for t in tasks if t.status == status]
                return tasks[:limit]

        @tool
        async def get_task(task_id: int) -> TaskOut:
            """One task with its description, properties, schedule, latest attempt status and workflow stages."""
            async with self._acting() as (s, owner, caller):
                return await self._task_in_project(s, owner, caller, task_id)

        @tool
        async def list_attempts(
            task_id: int, limit: Annotated[int, Field(ge=1, le=100)] = 10
        ) -> list[AttemptOut]:
            """The newest attempts (runs) of a task, with how each ended and what it used. Use get_attempt for the
            log and result."""
            async with self._acting() as (s, owner, caller):
                await self._task_in_project(s, owner, caller, task_id)
                return [
                    AttemptOut.model_validate(a)
                    for a in await projects.list_attempts(task_id, s, owner, limit=limit)
                ]

        @tool
        async def get_attempt(
            attempt_id: int,
            log_chars: Annotated[
                int, Field(ge=0, le=50_000, description="How much of the end of the log to return")
            ] = 4000,
        ) -> AttemptDetail:
            """One attempt: how it ended, why it failed if it did, its result, what it used, and the end of its log."""
            async with self._acting() as (s, owner, caller):
                attempt = await projects.get_attempt(attempt_id, s, owner)
                await self._task_in_project(s, owner, caller, attempt.task_id)
                return attempt.model_copy(update={"log": attempt.log[-log_chars:] if log_chars else ""})

        @tool
        async def list_agents() -> list[AgentOut]:
            """The project's agents: name, role, instructions, harness, model and what each is given."""
            async with self._acting() as (s, owner, caller):
                return [
                    AgentOut.model_validate(a) for a in await agents.list_agents(caller.project_id, s, owner)
                ]

        @tool
        async def list_workflows() -> list[WorkflowSummary]:
            """The project's workflows, by name."""
            async with self._acting() as (s, owner, caller):
                return await workflows.list_workflows(caller.project_id, s, owner)

        @tool
        async def get_usage(days: Annotated[int, Field(ge=1, le=365)] = 7) -> list[UsageRow]:
            """What the project's attempts used over the last days, per harness and model. Tokens are as the
            harness reported them; cached input is part of input and reasoning part of output."""
            async with self._acting() as (s, owner, caller):
                return await projects.project_usage(caller.project_id, s, owner, days=days)


class ControlEndpoint:
    """The route /mcp. It looks up the app's control plane at request time, so an app (or a test) can hold its own."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await scope["app"].state.control.handle(scope, receive, send)
