"""Connections to outside services (see app/connections.py). A user sees and manages only their own, administrators
included, and nothing here ever returns a credential. A project uses one connection per provider, and only one of its
owner's."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..app_settings import load_settings
from ..config import DEFAULT_SECRET_KEY, settings
from ..connections import (
    ConnectionProblem,
    DeviceLogins,
    DeviceState,
    Provider,
    get_provider,
    providers,
    retest,
    save_connection,
    unseal,
)
from ..deps import CurrentUser, SessionDep
from ..models import Connection, ProjectConnection
from .projects import _project

router = APIRouter(tags=["connections"])


class MethodOut(BaseModel):
    id: Literal["token", "oauth"]
    available: bool
    reason: str  # why it is not available, in words for the person


class FieldOut(BaseModel):
    key: str
    label: str
    placeholder: str
    help: str


class ProviderOut(BaseModel):
    id: str
    name: str
    category: str
    description: str
    icon: str
    token_help: str
    methods: list[MethodOut]
    config_fields: list[FieldOut]


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    method: str
    account: str
    settings: dict[str, Any]
    connected_at: datetime
    checked_at: datetime | None
    needs_reconnect: bool = False  # stored, but unreadable (the secret key changed)


class ConnectionsOut(BaseModel):
    secret_key_secure: bool  # a credential is only stored under a real THEMIS_SECRET_KEY
    providers: list[ProviderOut]
    connections: list[ConnectionOut]


class TokenIn(BaseModel):
    provider: str
    token: str = Field(min_length=1, max_length=4096)


class LoginState(BaseModel):
    status: Literal["starting", "waiting", "connected", "failed", "cancelled"]
    verification_url: str
    code: str
    expires_at: datetime | None
    error: str


class BindingIn(BaseModel):
    connection_id: int
    config: dict[str, Any] = Field(default_factory=dict)


class BindingOut(BaseModel):
    provider: str
    connection_id: int
    account: str
    config: dict[str, Any]


def _out(conn: Connection) -> ConnectionOut:
    out = ConnectionOut.model_validate(conn)
    out.needs_reconnect = unseal(conn) is None
    return out


def _logins(request: Request) -> DeviceLogins:
    return request.app.state.device_logins


def _state(state: DeviceState | None) -> LoginState | None:
    if state is None:
        return None
    return LoginState(
        status=state.status,  # type: ignore[arg-type]
        verification_url=state.verification_url,
        code=state.code,
        expires_at=state.expires_at,
        error=state.error,
    )


def _provider(provider_id: str) -> Provider:
    try:
        return get_provider(provider_id)
    except ConnectionProblem as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None


def _need_secure_key() -> None:
    if settings.secret_key == DEFAULT_SECRET_KEY:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Set a real THEMIS_SECRET_KEY before connecting: the credential is encrypted with it.",
        )


async def _own(session, connection_id: int, user) -> Connection:
    conn = await session.get(Connection, connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    return conn


@router.get("/connections", response_model=ConnectionsOut)
async def list_connections(session: SessionDep, user: CurrentUser) -> ConnectionsOut:
    """The services Themis can connect to, and this user's connections to them."""
    cfg = await load_settings(session)
    out = []
    for p in providers().values():
        oauth_reason = (
            ""
            if p.device_client_id(cfg)
            else "An administrator needs to add the sign in app's client id in Settings."
        )
        out.append(
            ProviderOut(
                id=p.id,
                name=p.name,
                category=p.category,
                description=p.description,
                icon=p.icon,
                token_help=p.token_help,
                methods=[
                    MethodOut(id="token", available=True, reason=""),
                    *(
                        [MethodOut(id="oauth", available=not oauth_reason, reason=oauth_reason)]
                        if p.device
                        else []
                    ),
                ],
                config_fields=[FieldOut(**vars(f)) for f in p.config_fields],
            )
        )
    rows = await session.scalars(
        select(Connection)
        .where(Connection.user_id == user.id)
        .order_by(Connection.provider, Connection.account)
    )
    return ConnectionsOut(
        secret_key_secure=settings.secret_key != DEFAULT_SECRET_KEY,
        providers=out,
        connections=[_out(c) for c in rows],
    )


@router.post("/connections", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def connect_with_token(body: TokenIn, session: SessionDep, user: CurrentUser) -> ConnectionOut:
    provider = _provider(body.provider)
    _need_secure_key()
    try:
        identity = await provider.identify(body.token)
    except ConnectionProblem as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    return _out(await save_connection(session, user.id, provider.id, "token", body.token.strip(), identity))


@router.post("/connections/{connection_id}/test", response_model=ConnectionOut)
async def test_connection(connection_id: int, session: SessionDep, user: CurrentUser) -> ConnectionOut:
    """Asks the service again whether the credential works and whose it is."""
    conn = await _own(session, connection_id, user)
    try:
        return _out(await retest(session, conn))
    except ConnectionProblem as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(connection_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Removes the credential from Themis, and from the projects that used it."""
    await session.delete(await _own(session, connection_id, user))
    await session.commit()


# ----- signing in with a code -----


@router.post(
    "/connection-logins/{provider_id}", response_model=LoginState, status_code=status.HTTP_201_CREATED
)
async def start_login(
    provider_id: str, request: Request, session: SessionDep, user: CurrentUser
) -> LoginState:
    """Begins a sign in: the response carries a link and a code to enter there."""
    provider = _provider(provider_id)
    _need_secure_key()
    client_id = provider.device_client_id(await load_settings(session))
    if provider.device is None or not client_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Signing in to {provider.name} is not set up. Connect with a token, or ask an administrator to add the client id in Settings.",
        )
    try:
        state = await _logins(request).start(user.id, provider, client_id)
    except ConnectionProblem as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
    out = _state(state)
    assert out is not None
    return out


@router.get("/connection-logins/{provider_id}", response_model=LoginState | None)
async def login_state(provider_id: str, request: Request, user: CurrentUser) -> LoginState | None:
    return _state(_logins(request).get(user.id, provider_id))


@router.delete("/connection-logins/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_login(provider_id: str, request: Request, user: CurrentUser) -> None:
    await _logins(request).cancel(user.id, provider_id)


# ----- the connection a project uses -----


async def _bindings(session, project_id: int) -> list[BindingOut]:
    rows = await session.execute(
        select(ProjectConnection, Connection.account)
        .join(Connection, Connection.id == ProjectConnection.connection_id)
        .where(ProjectConnection.project_id == project_id)
        .order_by(ProjectConnection.provider)
    )
    return [
        BindingOut(provider=b.provider, connection_id=b.connection_id, account=account, config=b.config)
        for b, account in rows
    ]


@router.get("/projects/{project_id}/connections", response_model=list[BindingOut])
async def project_connections(project_id: int, session: SessionDep, user: CurrentUser) -> list[BindingOut]:
    await _project(session, project_id, user)
    return await _bindings(session, project_id)


@router.put("/projects/{project_id}/connections/{provider_id}", response_model=BindingOut)
async def use_connection(
    project_id: int, provider_id: str, body: BindingIn, session: SessionDep, user: CurrentUser
) -> BindingOut:
    """The project uses this connection for the provider. It must be the project owner's own, and its settings
    (for GitHub, the repository) are checked with the service before they are saved."""
    await _project(session, project_id, user)
    provider = _provider(provider_id)
    conn = await _own(session, body.connection_id, user)
    if conn.provider != provider.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"That is not a {provider.name} connection"
        )
    credential = unseal(conn)
    if credential is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The stored credential can no longer be read. Connect again in Settings.",
        )
    try:
        config = await provider.check_config(credential["token"], body.config)
    except ConnectionProblem as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    bound = await session.scalar(
        select(ProjectConnection).where(
            ProjectConnection.project_id == project_id, ProjectConnection.provider == provider.id
        )
    )
    if bound is None:
        bound = ProjectConnection(project_id=project_id, provider=provider.id)
        session.add(bound)
    bound.connection_id, bound.config = conn.id, config
    await session.commit()
    return next(b for b in await _bindings(session, project_id) if b.provider == provider.id)


@router.delete("/projects/{project_id}/connections/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def stop_using_connection(
    project_id: int, provider_id: str, session: SessionDep, user: CurrentUser
) -> None:
    """Agents that opted in keep the opt-in, and their runs stop with a reason until the project picks a connection."""
    await _project(session, project_id, user)
    bound = await session.scalar(
        select(ProjectConnection).where(
            ProjectConnection.project_id == project_id, ProjectConnection.provider == provider_id
        )
    )
    if bound is not None:
        await session.delete(bound)
        await session.commit()
