"""Each user connects their own Codex (ChatGPT plan). Nothing here ever returns a token, and a user can
only see and manage their own connection - administrators included."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..codex import (
    CodexError,
    CodexLogins,
    LoginFlow,
    codex_executable,
    get_connection,
    key_is_secure,
)
from ..crypto import decrypt
from ..deps import CurrentUser, SessionDep

router = APIRouter(prefix="/codex", tags=["codex"])


class LoginState(BaseModel):
    status: Literal["starting", "waiting", "connected", "failed", "cancelled"]
    verification_url: str
    code: str
    expires_at: datetime | None
    error: str


class CodexStatus(BaseModel):
    cli_installed: bool
    secret_key_secure: bool  # a login is only stored under a real THEMIS_SECRET_KEY
    connected: bool
    needs_reconnect: bool  # stored, but unreadable (the secret key changed)
    account: str
    connected_at: datetime | None
    refreshed_at: datetime | None
    login: LoginState | None


def _state(flow: LoginFlow | None) -> LoginState | None:
    if flow is None:
        return None
    return LoginState(
        status=flow.status,  # type: ignore[arg-type]
        verification_url=flow.verification_url,
        code=flow.code,
        expires_at=flow.expires_at,
        error=flow.error,
    )


def _logins(request: Request) -> CodexLogins:
    return request.app.state.codex_logins


async def _status(request: Request, session: SessionDep, user: CurrentUser) -> CodexStatus:
    conn = await get_connection(session, user.id)
    readable = conn is not None and decrypt(conn.auth_encrypted) is not None
    return CodexStatus(
        cli_installed=codex_executable() is not None,
        secret_key_secure=key_is_secure(),
        connected=readable,
        needs_reconnect=conn is not None and not readable,
        account=conn.account if conn else "",
        connected_at=conn.connected_at if conn else None,
        refreshed_at=conn.refreshed_at if conn else None,
        login=_state(_logins(request).get(user.id)),
    )


@router.get("", response_model=CodexStatus)
async def codex_status(request: Request, session: SessionDep, user: CurrentUser) -> CodexStatus:
    return await _status(request, session, user)


@router.post("/login", response_model=LoginState, status_code=status.HTTP_201_CREATED)
async def start_login(request: Request, user: CurrentUser) -> LoginState:
    """Begin a device sign in: the response carries a link and a one-time code to enter there."""
    if not key_is_secure():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Set a real THEMIS_SECRET_KEY before connecting Codex: the login is encrypted with it.",
        )
    try:
        flow = await _logins(request).start(user.id)
    except CodexError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
    state = _state(flow)
    assert state is not None
    return state


@router.delete("/login", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_login(request: Request, user: CurrentUser) -> None:
    await _logins(request).cancel(user.id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(session: SessionDep, user: CurrentUser) -> None:
    conn = await get_connection(session, user.id)
    if conn is not None:
        await session.delete(conn)
        await session.commit()
