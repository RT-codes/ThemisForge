"""Signed in tool servers: the stored sign ins, starting one, finishing one, and a token for a run.

This is the one place that touches the database and the clock for tool sign ins. It knows nothing about any protocol:
every call that depends on how a server signs people in goes to the scheme (scheme.py), so a new way of signing in
needs no change here.

Rules this module keeps:
- A sign in belongs to a user and is found by the server's address, so signing in once covers every project and tool
  that points at that server (see McpLogin).
- A run never sees more than a bearer token. Renewing is done here, under a lock per sign in, because services rotate
  the refresh token on every use and using an old one can end the whole sign in.
- A token is renewed when it would not last the run (its time limit plus a margin from Settings), not on a timer.
- A renewal that fails because the service is down keeps the old token while it still works. One the service refuses
  marks the sign in as needing a person, and the run says so instead of failing in a way that looks like a bug.
"""

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..app_settings import McpAuthPolicy, load_settings
from ..crypto import decrypt, encrypt
from ..models import McpLogin, utcnow
from . import oauth as _oauth  # noqa: F401  (registers the standard scheme)
from .profiles import profile_for
from .scheme import AuthProblem, AuthScheme, Context, Granted, SignInRequired, get_scheme, resource_key

log = logging.getLogger("themis.mcp_auth")

ACTIVE, NEEDS_SIGN_IN = "active", "needs_sign_in"


def unseal(login: McpLogin) -> dict[str, Any] | None:
    """The decrypted credential, or None when it was written under a different THEMIS_SECRET_KEY (or was cleared)."""
    text = decrypt(login.credential_encrypted) if login.credential_encrypted else None
    try:
        data = json.loads(text) if text else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def login_for(session: AsyncSession, user_id: int, resource: str) -> McpLogin | None:
    return await session.scalar(
        select(McpLogin).where(McpLogin.user_id == user_id, McpLogin.resource == resource_key(resource))
    )


@dataclass
class _Pending:
    """A sign in that was started and is waiting for the person to come back."""

    user_id: int
    resource: str
    scheme: str
    redirect_uri: str
    return_to: str
    expires_at: datetime
    data: dict[str, Any] = field(repr=False)  # the scheme's secret state (a code verifier)


@dataclass(frozen=True)
class Completed:
    login: McpLogin | None
    return_to: str  # where to send the person's browser next ("" when the sign in could not be matched)
    error: str = ""


class McpLogins:
    """Held by the app (and by the scheduler, which needs tokens for runs). Pending sign ins live in memory: one is
    over in a minute or two, and losing it on a restart only means the person presses Sign in again."""

    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker
        self._pending: dict[str, _Pending] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, login_id: int) -> asyncio.Lock:
        return self._locks.setdefault(login_id, asyncio.Lock())

    # ----- signing in -----

    async def begin(
        self, user_id: int, resource: str, scheme_id: str, redirect_uri: str, return_to: str
    ) -> str:
        """Starts a sign in and returns where to send the person. Raises AuthProblem."""
        scheme = get_scheme(scheme_id)
        key = resource_key(resource)
        async with self._maker() as s:
            policy = (await load_settings(s)).mcp_auth
            existing = await login_for(s, user_id, key)
            previous = unseal(existing) if existing and existing.scheme == scheme_id else None
        now = utcnow()
        self._pending = {k: p for k, p in self._pending.items() if p.expires_at > now}  # forget the abandoned
        state = secrets.token_urlsafe(24)
        begun = await scheme.begin(Context(key, policy, profile_for(key), redirect_uri), state, previous)
        self._pending[state] = _Pending(
            user_id=user_id,
            resource=key,
            scheme=scheme_id,
            redirect_uri=redirect_uri,
            return_to=return_to,
            expires_at=now + timedelta(minutes=policy.sign_in_minutes),
            data=begun.pending,
        )
        return begun.url

    async def complete(self, user_id: int, params: dict[str, str]) -> Completed:
        """Finishes the sign in the service's redirect belongs to. Never raises: the person is sent back with the
        outcome either way."""
        pending = self._pending.pop(params.get("state", ""), None)
        if pending is None or pending.expires_at <= utcnow():
            return Completed(None, "", "This sign in link has expired or was already used. Start it again.")
        if pending.user_id != user_id:
            return Completed(None, "", "This sign in was started by someone else.")
        try:
            async with self._maker() as s:
                policy = (await load_settings(s)).mcp_auth
                ctx = Context(pending.resource, policy, profile_for(pending.resource), pending.redirect_uri)
                granted = await get_scheme(pending.scheme).complete(ctx, pending.data, params)
                login = await self._store(s, pending, granted)
            return Completed(login, pending.return_to)
        except AuthProblem as e:
            return Completed(None, pending.return_to, str(e))
        except Exception:
            log.exception("signing in to %s failed", pending.resource)  # the message can never hold a token
            return Completed(None, pending.return_to, "Could not complete the sign in.")

    @staticmethod
    async def _store(session: AsyncSession, pending: _Pending, granted: Granted) -> McpLogin:
        """Saves a finished sign in. Signing in again to the same server replaces the old one."""
        login = await session.scalar(
            select(McpLogin).where(McpLogin.user_id == pending.user_id, McpLogin.resource == pending.resource)
        )
        if login is None:
            login = McpLogin(user_id=pending.user_id, resource=pending.resource)
            session.add(login)
        now = utcnow()
        login.scheme, login.status, login.error = pending.scheme, ACTIVE, ""
        login.credential_encrypted = encrypt(json.dumps(granted.credential))
        login.account = granted.account or urlsplit(pending.resource).hostname or pending.resource
        login.settings = granted.settings
        login.expires_at, login.refreshed_at, login.connected_at = granted.expires_at, now, now
        await session.commit()
        return login

    # ----- using a sign in -----

    async def bearer(self, login_id: int, need_seconds: int = 0) -> str:
        """The token a run sends, valid for at least `need_seconds` plus the margin from Settings: renewed first when it
        would not be. Raises SignInRequired when a person has to sign in again, AuthProblem when it cannot be had."""
        return await self._token(login_id, need_seconds, force=False)

    async def _token(self, login_id: int, need_seconds: int, force: bool) -> str:
        async with self._lock(login_id), self._maker() as s:
            login = await s.get(McpLogin, login_id)
            if login is None:
                raise AuthProblem("A sign in this tool uses was removed. Sign in again.")
            if login.status != ACTIVE:
                raise SignInRequired(login.error or "This tool needs to be signed in again.")
            credential = unseal(login)
            if credential is None:
                raise AuthProblem(
                    "The stored sign in can no longer be read. If THEMIS_SECRET_KEY changed, sign in again."
                )
            scheme = get_scheme(login.scheme)
            policy = (await load_settings(s)).mcp_auth
            wanted = timedelta(seconds=need_seconds + policy.refresh_margin_seconds)
            if not force and not (login.expires_at and login.expires_at - utcnow() < wanted):
                return scheme.bearer(credential)
            return await self._renew(s, login, credential, scheme, policy)

    @staticmethod
    async def _renew(
        s: AsyncSession,
        login: McpLogin,
        credential: dict[str, Any],
        scheme: AuthScheme,
        policy: McpAuthPolicy,
    ) -> str:
        ctx = Context(login.resource, policy, profile_for(login.resource))
        try:
            granted = await scheme.renew(ctx, credential)
        except SignInRequired as e:
            # The tokens are dead. What identifies the client stays, so signing in again does not register another.
            keep = {k: credential[k] for k in ("client", "server") if k in credential}
            login.status, login.error = NEEDS_SIGN_IN, str(e)
            login.credential_encrypted, login.expires_at = encrypt(json.dumps(keep)), None
            await s.commit()
            raise
        except AuthProblem as e:
            if (
                login.expires_at and login.expires_at > utcnow()
            ):  # the service is down: this token still works
                log.warning(
                    "could not renew the sign in to %s, using the current token: %s", login.resource, e
                )
                return scheme.bearer(credential)
            raise
        login.credential_encrypted = encrypt(json.dumps(granted.credential))
        login.expires_at, login.refreshed_at = granted.expires_at, utcnow()
        login.account = granted.account or login.account
        login.settings = {
            **login.settings,
            **granted.settings,
        }  # a renewal leaves out what the first answer said
        await s.commit()
        return scheme.bearer(granted.credential)

    async def keep_alive(self) -> int:
        """Renews the sign ins nobody has used for the configured number of days, so a service does not let them lapse
        from disuse. Returns how many were renewed. A failure is logged and left for the next pass."""
        async with self._maker() as s:
            days = (await load_settings(s)).mcp_auth.keepalive_days
            if days <= 0:
                return 0
            cutoff = utcnow() - timedelta(days=days)
            ids = list(
                await s.scalars(
                    select(McpLogin.id).where(
                        McpLogin.status == ACTIVE,
                        func.coalesce(McpLogin.refreshed_at, McpLogin.connected_at) < cutoff,
                    )
                )
            )
        renewed = 0
        for login_id in ids:
            try:
                await self._token(login_id, 0, force=True)
                renewed += 1
            except AuthProblem as e:
                log.warning("keeping sign in %s alive failed: %s", login_id, e)
        return renewed
