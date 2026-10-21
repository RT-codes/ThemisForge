from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.config import DEFAULT_SECRET_KEY, settings
from app.errors import ApplicationError
from app.features.connections.schemas import (
    BindingIn,
    BindingOut,
    ConnectionOut,
    ConnectionsOut,
    FieldOut,
    LoginState,
    MethodOut,
    ProviderOut,
    TokenIn,
)
from app.features.connections.service import (
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
from app.features.projects.access import require_project
from app.features.system.settings import load_settings
from app.persistence.models import Connection, ProjectConnection, User
from app.runtime import Runtime


def _out(conn: Connection) -> ConnectionOut:
    out = ConnectionOut.model_validate(conn)
    out.needs_reconnect = unseal(conn) is None
    return out


def _logins(runtime: Runtime) -> DeviceLogins:
    return runtime.device_logins


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
        raise ApplicationError(status.HTTP_404_NOT_FOUND, str(e)) from None


def require_secure_key() -> None:
    if settings.secret_key == DEFAULT_SECRET_KEY:
        raise ApplicationError(
            status.HTTP_409_CONFLICT,
            "Set a real THEMIS_SECRET_KEY before connecting: the credential is encrypted with it.",
        )


async def _own(session, connection_id: int, user) -> Connection:
    conn = await session.get(Connection, connection_id)
    if conn is None or conn.user_id != user.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Connection not found")
    return conn


async def list_connections(session: AsyncSession, user: User) -> ConnectionsOut:
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
                harness=p.harness,
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


async def connect_with_token(body: TokenIn, session: AsyncSession, user: User) -> ConnectionOut:
    provider = _provider(body.provider)
    require_secure_key()
    try:
        identity = await provider.identify(body.token)
    except ConnectionProblem as e:
        raise ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    return _out(await save_connection(session, user.id, provider.id, "token", body.token.strip(), identity))


async def test_connection(connection_id: int, session: AsyncSession, user: User) -> ConnectionOut:
    """Asks the service again whether the credential works and whose it is."""
    conn = await _own(session, connection_id, user)
    try:
        return _out(await retest(session, conn))
    except ConnectionProblem as e:
        raise ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None


async def disconnect(connection_id: int, session: AsyncSession, user: User) -> None:
    """Removes the credential from Themis, and from the projects that used it."""
    await session.delete(await _own(session, connection_id, user))
    await session.commit()


async def start_login(provider_id: str, runtime: Runtime, session: AsyncSession, user: User) -> LoginState:
    """Begins a sign in: the response carries a link and a code to enter there."""
    provider = _provider(provider_id)
    require_secure_key()
    client_id = provider.device_client_id(await load_settings(session))
    if provider.device is None or not client_id:
        raise ApplicationError(
            status.HTTP_409_CONFLICT,
            f"Signing in to {provider.name} is not set up. Connect with a token, or ask an administrator to add the client id in Settings.",
        )
    try:
        state = await _logins(runtime).start(user.id, provider, client_id)
    except ConnectionProblem as e:
        raise ApplicationError(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
    out = _state(state)
    assert out is not None
    return out


async def login_state(provider_id: str, runtime: Runtime, user: User) -> LoginState | None:
    return _state(_logins(runtime).get(user.id, provider_id))


async def cancel_login(provider_id: str, runtime: Runtime, user: User) -> None:
    await _logins(runtime).cancel(user.id, provider_id)


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


async def project_connections(project_id: int, session: AsyncSession, user: User) -> list[BindingOut]:
    await require_project(session, project_id, user)
    return await _bindings(session, project_id)


async def use_connection(
    project_id: int, provider_id: str, body: BindingIn, session: AsyncSession, user: User
) -> BindingOut:
    """The project uses this connection for the provider. It must be the project owner's own, and its settings
    (for GitHub, the repository) are checked with the service before they are saved."""
    await require_project(session, project_id, user)
    provider = _provider(provider_id)
    if provider.harness:
        raise ApplicationError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{provider.name} is the login of its agents: connect it in Settings, no project needs to choose it",
        )
    conn = await _own(session, body.connection_id, user)
    if conn.provider != provider.id:
        raise ApplicationError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"That is not a {provider.name} connection"
        )
    credential = unseal(conn)
    if credential is None:
        raise ApplicationError(
            status.HTTP_409_CONFLICT,
            "The stored credential can no longer be read. Connect again in Settings.",
        )
    try:
        config = await provider.check_config(credential["token"], body.config)
    except ConnectionProblem as e:
        raise ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
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


async def stop_using_connection(project_id: int, provider_id: str, session: AsyncSession, user: User) -> None:
    """Agents that opted in keep the opt-in, and their runs stop with a reason until the project picks a connection."""
    await require_project(session, project_id, user)
    bound = await session.scalar(
        select(ProjectConnection).where(
            ProjectConnection.project_id == project_id, ProjectConnection.provider == provider_id
        )
    )
    if bound is not None:
        await session.delete(bound)
        await session.commit()
