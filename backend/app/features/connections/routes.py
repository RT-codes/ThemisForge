from fastapi import APIRouter, Request, status

from app.api.dependencies import CurrentUser, SessionDep
from app.features.connections import operations
from app.features.connections.schemas import (
    BindingIn,
    BindingOut,
    ConnectionOut,
    ConnectionsOut,
    LoginState,
    TokenIn,
)

router = APIRouter(tags=["connections"])


@router.get("/connections", response_model=ConnectionsOut)
async def list_connections(session: SessionDep, user: CurrentUser) -> ConnectionsOut:
    """The services Themis can connect to, and this user's connections to them."""

    return await operations.list_connections(session, user)


@router.post("/connections", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def connect_with_token(body: TokenIn, session: SessionDep, user: CurrentUser) -> ConnectionOut:
    return await operations.connect_with_token(body, session, user)


@router.post("/connections/{connection_id}/test", response_model=ConnectionOut)
async def test_connection(connection_id: int, session: SessionDep, user: CurrentUser) -> ConnectionOut:
    """Asks the service again whether the credential works and whose it is."""

    return await operations.test_connection(connection_id, session, user)


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(connection_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Removes the credential from Themis, and from the projects that used it."""

    return await operations.disconnect(connection_id, session, user)


@router.post(
    "/connection-logins/{provider_id}", response_model=LoginState, status_code=status.HTTP_201_CREATED
)
async def start_login(
    provider_id: str, request: Request, session: SessionDep, user: CurrentUser
) -> LoginState:
    """Begins a sign in: the response carries a link and a code to enter there."""

    return await operations.start_login(provider_id, request.app.state, session, user)


@router.get("/connection-logins/{provider_id}", response_model=LoginState | None)
async def login_state(provider_id: str, request: Request, user: CurrentUser) -> LoginState | None:
    return await operations.login_state(provider_id, request.app.state, user)


@router.delete("/connection-logins/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_login(provider_id: str, request: Request, user: CurrentUser) -> None:
    return await operations.cancel_login(provider_id, request.app.state, user)


@router.get("/projects/{project_id}/connections", response_model=list[BindingOut])
async def project_connections(project_id: int, session: SessionDep, user: CurrentUser) -> list[BindingOut]:
    return await operations.project_connections(project_id, session, user)


@router.put("/projects/{project_id}/connections/{provider_id}", response_model=BindingOut)
async def use_connection(
    project_id: int, provider_id: str, body: BindingIn, session: SessionDep, user: CurrentUser
) -> BindingOut:
    """The project uses this connection for the provider. It must be the project owner's own, and its settings
    (for GitHub, the repository) are checked with the service before they are saved."""

    return await operations.use_connection(project_id, provider_id, body, session, user)


@router.delete("/projects/{project_id}/connections/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def stop_using_connection(
    project_id: int, provider_id: str, session: SessionDep, user: CurrentUser
) -> None:
    """Agents that opted in keep the opt-in, and their runs stop with a reason until the project picks a connection."""

    return await operations.stop_using_connection(project_id, provider_id, session, user)
