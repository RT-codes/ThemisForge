"""Signing in to the tool servers that ask for it (see app/mcp_auth).

A sign in is the project owner's: runs use the owner's, like their connections, so only the owner can start one for a
project's tool. It is found by the server's address, so it also covers the owner's other projects that use the same
server. Nothing here returns a token."""

from datetime import datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from ..app_settings import AppSettings, load_settings
from ..deps import CurrentUser, SessionDep
from ..mcp_auth import ACTIVE, SCHEMES, AuthProblem, McpLogins, resource_key
from ..models import McpLogin, McpServer
from .connections import _need_secure_key
from .projects import _project

router = APIRouter(tags=["mcp-auth"])


class LoginOut(BaseModel):
    """A stored sign in as people see it. Which of their tools use it is told by the tools, not here."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    resource: str
    scheme: str
    status: Literal["active", "needs_sign_in"]
    error: str
    account: str
    expires_at: datetime | None
    refreshed_at: datetime | None
    connected_at: datetime


class ToolSignIn(BaseModel):
    """Where a tool that signs in stands, for the owner of its project."""

    state: Literal["signed_in", "needs_sign_in", "not_signed_in"]
    method: str  # the scheme's label, such as "Sign in with the service"
    login_id: int | None
    account: str
    error: str
    expires_at: datetime | None


async def tool_sign_ins(session, owner_id: int, servers: list[McpServer]) -> dict[int, ToolSignIn]:
    """The sign in state of each of these tools that signs in (the others are left out)."""
    wanted = {s.id: resource_key(s.url) for s in servers if s.auth}
    if not wanted:
        return {}
    rows = await session.scalars(
        select(McpLogin).where(McpLogin.user_id == owner_id, McpLogin.resource.in_(set(wanted.values())))
    )
    by_resource = {r.resource: r for r in rows}
    out: dict[int, ToolSignIn] = {}
    for server in servers:
        if server.id not in wanted:
            continue
        login = by_resource.get(wanted[server.id])
        scheme = SCHEMES.get(server.auth)
        state = (
            "not_signed_in" if login is None else "signed_in" if login.status == ACTIVE else "needs_sign_in"
        )
        out[server.id] = ToolSignIn(
            state=state,  # type: ignore[arg-type]
            method=scheme.label if scheme else server.auth,
            login_id=login.id if login else None,
            account=login.account if login else "",
            error=login.error if login else "",
            expires_at=login.expires_at if login and login.status == ACTIVE else None,
        )
    return out


def _logins(request: Request) -> McpLogins:
    return request.app.state.mcp_logins


def _redirect_uri(request: Request, cfg: AppSettings) -> str:
    """Where the service sends the person back to: the address Themis was opened on, unless Settings names one (a
    reverse proxy can make the address the backend sees different from the one a browser uses)."""
    base = cfg.mcp_auth.public_url or str(request.base_url).rstrip("/")
    return f"{base}/api/mcp-auth/callback"


def _local_path(path: str) -> str:
    """Where to send the browser after a sign in: only a path on this site, so the callback can never be turned into
    a redirect to somewhere else."""
    return path if path.startswith("/") and not path.startswith("//") and "\\" not in path else "/"


class SignInIn(BaseModel):
    return_to: str = "/"  # the page to come back to, as a path


class SignInOut(BaseModel):
    url: str  # where to send the person's browser


@router.get("/mcp-auth/logins", response_model=list[LoginOut])
async def list_logins(session: SessionDep, user: CurrentUser) -> list[McpLogin]:
    """The signed in tool servers of the current user (nobody else's, administrators included)."""
    rows = await session.scalars(
        select(McpLogin).where(McpLogin.user_id == user.id).order_by(McpLogin.resource)
    )
    return list(rows.all())


@router.post("/mcp-servers/{server_id}/sign-in", response_model=SignInOut)
async def start_sign_in(
    server_id: int, body: SignInIn, request: Request, session: SessionDep, user: CurrentUser
) -> SignInOut:
    server = await session.get(McpServer, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tool not found")
    await _project(
        session, server.project_id, user
    )  # a project is its owner's alone, and runs use their sign in
    if server.kind != "http" or not server.auth:
        raise HTTPException(status.HTTP_409_CONFLICT, "This tool does not ask for a sign in")
    _need_secure_key()
    cfg = await load_settings(session)
    try:
        url = await _logins(request).begin(
            user.id, server.url, server.auth, _redirect_uri(request, cfg), _local_path(body.return_to)
        )
    except AuthProblem as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None
    return SignInOut(url=url)


@router.get("/mcp-auth/callback")
async def sign_in_callback(request: Request, user: CurrentUser) -> RedirectResponse:
    """Where the service sends the person's browser back to. The outcome travels to the page as query parameters, the
    page shows it and removes them."""
    done = await _logins(request).complete(user.id, dict(request.query_params))
    if done.error:
        outcome = {"mcp_sign_in": "error", "message": done.error}
    else:
        outcome = {"mcp_sign_in": "ok", "message": done.login.account if done.login else ""}
    # the outcome goes in the query, before any #fragment the page was opened with (the Tools section's, for instance)
    target = urlsplit(_local_path(done.return_to))
    query = urlencode([*parse_qsl(target.query), *outcome.items()])
    return RedirectResponse(
        urlunsplit(("", "", target.path, query, target.fragment)), status.HTTP_303_SEE_OTHER
    )


@router.delete("/mcp-auth/logins/{login_id}", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(login_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Forgets a sign in. The tools that used it say they need one again. This does not revoke it at the service:
    that is done in the service's own settings."""
    login = await session.get(McpLogin, login_id)
    if login is None or login.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sign in not found")
    await session.delete(login)
    await session.commit()
