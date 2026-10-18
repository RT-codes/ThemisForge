"""The MCP control plane: how an agent outside a cell (Claude Code on this machine or another, later a run's own
agent) looks at and drives Themis through the Model Context Protocol, served at /mcp by this same app.

There is one way into Themis's behaviour and it is the REST routers: a tool calls the same handler the web interface
does, as the token's user, so every rule they check (ownership, validation, what a task may be) holds here without
being written twice. This module adds only who is asking and what they may reach (the tools are in control_tools.py):

- A request carries a control token (`Authorization: Bearer ...`, see ControlToken). A token belongs to a user and acts
  as them. It either names one project, which is all it can reach, or none, which means all of the user's projects and
  the global settings the user may see. An id outside that reach answers "not found", exactly like a missing one.
- A token's `scope` is "read" (the default) or "write". Tools that change things (`write_tool`) refuse a "read" token,
  so tokens made before the action tools existed can still only look.
- MCP is served stateless, one JSON answer per request: nothing is kept between calls, so a restart loses no session
  and there is nothing to expire.
"""

import functools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from fastapi import HTTPException
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from . import control_tools
from .control_tools import NOT_FOUND
from .models import ControlToken, User, utcnow
from .security import hash_secret

INSTRUCTIONS = (
    "Themis runs AI agents as tasks in throwaway containers, organised in projects. Start with get_project_overview "
    "(or list_projects first, on a connection for all projects) to see what is going on, then go down: list_boards "
    "and get_board for the work, get_task and get_attempt for how a run went, list_agents, list_workflows and the "
    "other list tools for how the project is set up, list_files and read_file for its folders. The tools that change "
    "things (making, moving, running and cancelling tasks, running workflows, answering approvals, halting and "
    "resuming) only work on a connection that was made with permission to change things."
)
WRITE_NEEDED = (
    "This connection can only read. Make one that can change things (in Themis, under Connections, with 'Allow "
    "changes') to use this tool."
)
LAST_USED_EVERY = timedelta(minutes=1)  # so a busy agent does not make a write of every read


@dataclass(frozen=True)
class Caller:
    """Who is asking: what a control token stands for."""

    token_id: int
    user_id: int  # the tools act as this user
    project_id: int | None  # the only project it reaches; None: all of the user's
    scope: str
    name: str  # what the owner called the connection, so the history can say who really acted


class UserVia:
    """The user a tool acts as, with a name that says an agent did it: "Ada via Claude Code". The REST handlers write
    `user.name` into the project history as the actor, so this is how an action taken through MCP is told apart from
    one Ada took herself. Everything else (id, rights) is the user's own; nothing is changed on the user row."""

    def __init__(self, user: User, connection: str) -> None:
        self._user = user
        self.name = f"{user.name} via {connection}"

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._user, attribute)


# set while a request is handled, for the tools to read
_caller: ContextVar[Caller] = ContextVar("control_caller")
_app: ContextVar[Any] = ContextVar("control_app")  # the FastAPI app that got the request


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
        control_tools.register(self)
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
            if row is None:
                return None
            now = utcnow()
            if row.last_used_at is None or now - row.last_used_at > LAST_USED_EVERY:
                row.last_used_at = now
                await s.commit()
            return Caller(row.id, row.user_id, row.project_id, row.scope, row.name)

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
        _app.set(scope["app"])
        # The server answers on "/" of its own, so /mcp is served without the redirect a mounted app would add
        await self._app({**scope, "path": "/", "raw_path": b"/"}, receive, send)

    # what the tools build on

    @asynccontextmanager
    async def acting(self) -> AsyncIterator[tuple[AsyncSession, User, Caller]]:
        """A database session and the user the tool acts as, for the caller of this request."""
        caller = _caller.get()
        async with self.maker() as s:
            user = await s.get(User, caller.user_id)
            if user is None:  # the user was removed while the token lived on
                raise ToolError(NOT_FOUND)
            yield (
                s,
                cast(User, UserVia(user, caller.name)),
                caller,
            )  # stands in for the User the handlers expect

    @staticmethod
    def app() -> Any:
        """The app that is serving this request, for the few handlers that read its state (scheduler, preflight)."""
        return _app.get()

    def tool(self, fn, *, writes: bool = False):
        """Register a tool, with the failures of the REST handlers it calls turned into the tool's own errors.

        A tool that `writes` changes things, so it only runs for a token made with the "write" scope. The check is made
        here, once, rather than in each tool, so a new action cannot forget it. It is also announced to the agent
        (read-only hint), which lets a client let the reading tools through without asking and ask about the others."""

        @functools.wraps(fn)
        async def run(*args, **kwargs):
            if writes and _caller.get().scope != "write":
                raise ToolError(WRITE_NEEDED)
            try:
                return await fn(*args, **kwargs)
            except HTTPException as e:
                # a missing id and one out of reach get the same answer, so ids tell nothing about what is beyond it
                raise ToolError(NOT_FOUND if e.status_code == 404 else str(e.detail)) from None

        self.server.tool(annotations=ToolAnnotations(read_only_hint=not writes))(run)
        return fn

    def write_tool(self, fn):
        """Register a tool that changes things (see `tool`)."""
        return self.tool(fn, writes=True)


class ControlEndpoint:
    """The route /mcp. It looks up the app's control plane at request time, so an app (or a test) can hold its own."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await scope["app"].state.control.handle(scope, receive, send)
