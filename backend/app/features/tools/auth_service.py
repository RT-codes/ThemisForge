from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.errors import ApplicationError
from app.features.tools.auth import ACTIVE, SCHEMES, McpLogins, resource_key
from app.features.tools.auth_schemas import ToolSignIn
from app.persistence.models import McpLogin, McpServer, User
from app.runtime import Runtime


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


def _logins(runtime: Runtime) -> McpLogins:
    return runtime.mcp_logins


async def list_logins(session: AsyncSession, user: User) -> list[McpLogin]:
    """The signed in tool servers of the current user (nobody else's, administrators included)."""
    rows = await session.scalars(
        select(McpLogin).where(McpLogin.user_id == user.id).order_by(McpLogin.resource)
    )
    return list(rows.all())


async def sign_out(login_id: int, session: AsyncSession, user: User) -> None:
    """Forgets a sign in. The tools that used it say they need one again. This does not revoke it at the service:
    that is done in the service's own settings."""
    login = await session.get(McpLogin, login_id)
    if login is None or login.user_id != user.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Sign in not found")
    await session.delete(login)
    await session.commit()
