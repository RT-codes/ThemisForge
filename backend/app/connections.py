"""Connections: a user's sign in to an outside service (GitHub today), kept once and used by agents on projects.

One shape for every service. A `Provider` says what the service is, how a person connects to it (paste a token, or sign
in with a code), who the credential belongs to, and what a cell gets so its agent can use the service. Everything else
is shared: the `connections` table, the encryption, the Settings list, the project's choice of connection, an agent's
opt-in, and getting the credential into the cell and out of the log. Adding a service means writing a provider module
(see app/github.py) and listing it in `providers()`.

How a connection reaches an agent, in three steps:
1. The project picks one of its owner's connections per provider (`ProjectConnection`), with settings of its own
   (for GitHub, the repository).
2. An agent opts in by naming the provider (`Agent.connections`).
3. When a run starts, the provider's secret values go into the cell as in-memory key files, exactly like stored keys
   (app/keys.py), so they are exported as variables and scrubbed from the log. Plain settings (git author, default
   repository) go in as ordinary environment variables.

Safety rules this module keeps, the same as for the Codex login:
- Credentials are encrypted (app/crypto.py) before they touch the database and are never returned by the API.
- Only the owner of a connection can see or manage it; a project can only use connections of its own owner.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, ClassVar

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .app_settings import AppSettings
from .crypto import decrypt, encrypt
from .models import Agent, Connection, ProjectConnection, utcnow

log = logging.getLogger("themis.connections")

MIN_POLL_SECONDS = 1.0  # a floor under the service's own advice; tests lower it
HTTP_SECONDS = 15


class ConnectionProblem(Exception):
    """Something the person can act on: a rejected token, an unreachable service, a connection that needs redoing."""


def http_client() -> httpx.AsyncClient:
    """The one place connections talk to the outside. Redirects are not followed: a credential must not follow one."""
    return httpx.AsyncClient(timeout=HTTP_SECONDS, follow_redirects=False)


@dataclass(frozen=True)
class Identity:
    """What a service says about a credential: who it belongs to, and whatever the provider wants to remember."""

    account: str
    settings: dict[str, Any] = field(default_factory=dict)  # never a secret: it is returned by the API


@dataclass(frozen=True)
class DeviceFlow:
    """A sign in with a code (RFC 8628): the person opens a link on any device and enters the code."""

    code_url: str
    token_url: str
    scope: str


@dataclass(frozen=True)
class ConfigField:
    """A setting a project gives its connection (for GitHub, which repository)."""

    key: str
    label: str
    placeholder: str = ""
    help: str = ""


class Provider:
    """A service Themis can connect to. Subclass it, set the class attributes and fill in what the service needs."""

    id: ClassVar[str]
    name: ClassVar[str]
    category: ClassVar[str]  # "ai" (an agent thinks with it) | "service" (an agent acts through it)
    description: ClassVar[str]
    icon: ClassVar[str]  # the name of a Lucide icon
    token_help: ClassVar[str] = ""  # for people: what kind of token to make and where
    device: ClassVar[DeviceFlow | None] = None
    config_fields: ClassVar[tuple[ConfigField, ...]] = ()
    env_names: ClassVar[tuple[str, ...]] = ()  # the variables the secret is available as in a cell

    def device_client_id(self, cfg: AppSettings) -> str:
        """The app id the code sign in needs, from Settings. Empty means the sign in is not set up yet."""
        return ""

    async def identify(self, token: str) -> Identity:
        """Asks the service whose token this is. Raises ConnectionProblem when it is rejected or unreachable."""
        raise NotImplementedError

    async def check_config(self, token: str, config: dict[str, Any]) -> dict[str, Any]:
        """The project's settings, checked against the service and tidied. Raises ConnectionProblem."""
        return {}

    def secret_env(self, token: str) -> dict[str, str]:
        """What a cell gets as secret variables (hidden from the log)."""
        return dict.fromkeys(self.env_names, token)

    def plain_env(self, settings: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
        """Settings a cell gets as ordinary variables. These are visible on the host, so never a secret."""
        return {}

    def agent_note(self, account: str, config: dict[str, Any]) -> str:
        """A few lines for the agent's prompt: what it can use and how."""
        return ""


def providers() -> dict[str, Provider]:
    from .github import GitHub  # here, not at the top: a provider module imports this one

    return {p.id: p for p in (GitHub(),)}


def get_provider(provider_id: str) -> Provider:
    found = providers().get(provider_id)
    if found is None:
        raise ConnectionProblem(f"Unknown connection: {provider_id}")
    return found


# ----- storing -----


def unseal(conn: Connection) -> dict[str, Any] | None:
    """The decrypted credential, or None when it was written under a different THEMIS_SECRET_KEY."""
    text = decrypt(conn.credential_encrypted)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) and data.get("token") else None


async def save_connection(
    session: AsyncSession, user_id: int, provider: str, method: str, token: str, identity: Identity
) -> Connection:
    """Stores a credential. Connecting the same account again replaces the old credential instead of adding another."""
    conn = await session.scalar(
        select(Connection).where(
            Connection.user_id == user_id,
            Connection.provider == provider,
            Connection.account == identity.account,
        )
    )
    if conn is None:
        conn = Connection(user_id=user_id, provider=provider, account=identity.account)
        session.add(conn)
    conn.method = method
    conn.credential_encrypted = encrypt(json.dumps({"token": token}))
    conn.settings = identity.settings
    conn.connected_at = conn.checked_at = utcnow()
    await session.commit()
    return conn


async def retest(session: AsyncSession, conn: Connection) -> Connection:
    """Asks the service again who the credential belongs to. Raises ConnectionProblem when it no longer works."""
    credential = unseal(conn)
    if credential is None:
        raise ConnectionProblem(
            "The stored credential can no longer be read (the secret key changed). Connect again."
        )
    identity = await get_provider(conn.provider).identify(credential["token"])
    conn.settings = identity.settings
    conn.checked_at = utcnow()
    await session.commit()
    return conn


# ----- using a connection in a run -----


@dataclass(frozen=True)
class RunConnection:
    """One connection a run uses. Holds no secret: the values are read when the cell starts."""

    provider: str
    connection_id: int
    env_names: tuple[str, ...]  # the variables the secret is exported as


@dataclass
class RunPlan:
    connections: list[RunConnection] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)  # plain settings for the cell
    notes: list[str] = field(default_factory=list)  # for the agent's prompt
    error: str = ""  # why the run cannot start


async def plan_for_run(session: AsyncSession, project_id: int, agent: Agent | None) -> RunPlan:
    """What the agent's opted-in connections give a run. A connection that is missing stops the run with a reason,
    instead of running without what the agent was set up to have."""
    plan = RunPlan()
    if agent is None or not agent.connections:
        return plan
    known = providers()
    for provider_id in dict.fromkeys(agent.connections):
        provider = known.get(provider_id)
        if provider is None:
            plan.error = (
                f"The agent uses '{provider_id}', which Themis does not know. Check the agent's Connections."
            )
            return plan
        bound = await session.scalar(
            select(ProjectConnection).where(
                ProjectConnection.project_id == project_id, ProjectConnection.provider == provider_id
            )
        )
        conn = await session.get(Connection, bound.connection_id) if bound else None
        if bound is None or conn is None:
            plan.error = (
                f"The agent uses {provider.name}, but the project has no {provider.name} connection. "
                "Choose one in the project's Connections."
            )
            return plan
        plan.connections.append(RunConnection(provider_id, conn.id, provider.env_names))
        plan.env.update(provider.plain_env(conn.settings, bound.config))
        if note := provider.agent_note(conn.account, bound.config):
            plan.notes.append(note)
    return plan


async def secret_values(maker: async_sessionmaker[AsyncSession], used: list[RunConnection]) -> dict[str, str]:
    """The secret variables of the connections a run uses, by variable name. Read when the cell starts."""
    if not used:
        return {}
    async with maker() as session:
        rows = {
            c.id: c
            for c in await session.scalars(
                select(Connection).where(Connection.id.in_([u.connection_id for u in used]))
            )
        }
    out: dict[str, str] = {}
    for u in used:
        conn = rows.get(u.connection_id)
        if conn is None:
            raise ConnectionProblem("A connection this agent uses was removed before its run started")
        credential = unseal(conn)
        if credential is None:
            raise ConnectionProblem(
                f"The {get_provider(u.provider).name} connection can no longer be read. "
                "If THEMIS_SECRET_KEY changed, connect again in Settings."
            )
        out.update(get_provider(u.provider).secret_env(credential["token"]))
    return out


# ----- signing in with a code -----


@dataclass
class DeviceState:
    status: str = "starting"  # starting | waiting | connected | failed | cancelled
    verification_url: str = ""
    code: str = ""
    expires_at: datetime | None = None
    error: str = ""
    task: asyncio.Task | None = None

    @property
    def active(self) -> bool:
        return self.status in ("starting", "waiting")


class DeviceLogins:
    """Runs the sign in with a code for people: they get a link and a code, approve on any device, and the connection
    appears. No browser callback is needed, which also makes it work on localhost and behind a reverse proxy."""

    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker
        self._flows: dict[tuple[int, str], DeviceState] = {}

    def get(self, user_id: int, provider: str) -> DeviceState | None:
        return self._flows.get((user_id, provider))

    async def start(self, user_id: int, provider: Provider, client_id: str) -> DeviceState:
        flow = provider.device
        if flow is None:
            raise ConnectionProblem(f"{provider.name} cannot be connected by signing in")
        await self.cancel(user_id, provider.id)
        try:
            async with http_client() as client:
                reply = await client.post(
                    flow.code_url,
                    data={"client_id": client_id, "scope": flow.scope},
                    headers={"Accept": "application/json"},
                )
            body = reply.json()
        except (httpx.HTTPError, ValueError):
            raise ConnectionProblem(f"Could not reach {provider.name} to start the sign in.") from None
        if reply.status_code >= 300 or "device_code" not in body:
            detail = body.get("error_description") or body.get("error") or f"HTTP {reply.status_code}"
            raise ConnectionProblem(f"{provider.name} did not start the sign in: {detail}")
        expires = int(body.get("expires_in", 900))
        state = DeviceState(
            status="waiting",
            verification_url=body.get("verification_uri", ""),
            code=body.get("user_code", ""),
            expires_at=utcnow() + timedelta(seconds=expires),
        )
        self._flows[(user_id, provider.id)] = state
        state.task = asyncio.create_task(
            self._poll(
                user_id,
                provider,
                client_id,
                body["device_code"],
                float(body.get("interval", 5)),
                expires,
                state,
            )
        )
        return state

    async def cancel(self, user_id: int, provider: str) -> None:
        state = self._flows.get((user_id, provider))
        if state is None or not state.active or state.task is None:
            return
        state.status = "cancelled"
        state.task.cancel()
        await asyncio.gather(state.task, return_exceptions=True)

    async def shutdown(self) -> None:
        for user_id, provider in list(self._flows):
            await self.cancel(user_id, provider)

    async def _poll(
        self,
        user_id: int,
        provider: Provider,
        client_id: str,
        device_code: str,
        interval: float,
        expires_in: int,
        state: DeviceState,
    ) -> None:
        assert provider.device is not None
        try:
            async with asyncio.timeout(expires_in):
                token = await self._wait_for_token(provider.device, client_id, device_code, interval)
            identity = await provider.identify(token)
            async with self._maker() as session:
                await save_connection(session, user_id, provider.id, "oauth", token, identity)
            state.status = "connected"
        except asyncio.CancelledError:
            state.status = "cancelled"
            raise
        except TimeoutError:
            state.status, state.error = "failed", "The code expired. Start again to get a new one."
        except ConnectionProblem as e:
            state.status, state.error = "failed", str(e)
        except Exception:
            log.exception("sign in to %s failed", provider.id)  # the message can never contain the token
            state.status, state.error = "failed", "Could not complete the sign in"

    @staticmethod
    async def _wait_for_token(flow: DeviceFlow, client_id: str, device_code: str, interval: float) -> str:
        failures = 0
        while True:
            await asyncio.sleep(max(interval, MIN_POLL_SECONDS))
            try:
                async with http_client() as client:
                    reply = await client.post(
                        flow.token_url,
                        data={
                            "client_id": client_id,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        },
                        headers={"Accept": "application/json"},
                    )
                body = reply.json()
                failures = 0
            except (httpx.HTTPError, ValueError):
                failures += 1  # a hiccup is not the end of the sign in, a dead service is
                if failures >= 5:
                    raise ConnectionProblem("Lost contact with the service during the sign in.") from None
                continue
            if token := body.get("access_token"):
                return token
            match body.get("error"):
                case "authorization_pending":
                    continue
                case "slow_down":
                    interval += 5
                case "access_denied":
                    raise ConnectionProblem("The sign in was declined.")
                case "expired_token":
                    raise TimeoutError
                case other:
                    raise ConnectionProblem(body.get("error_description") or other or "The sign in failed.")
