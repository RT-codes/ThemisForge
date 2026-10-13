"""What a way of signing in to a tool server looks like, and the list of the ways Themis knows.

The rest of Themis (the stored logins, the run that needs a token, the sign in pages) only ever talks to this
interface. A way of signing in is one class that fills it in and is added to SCHEMES; nothing else changes. Standard
OAuth for MCP servers (app/mcp_auth/oauth.py) is the only one today. A server that wants something different would be a
second class here: another OAuth flavour (a device code, a client that was registered by hand), an API key with its own
header, a cookie.

What a scheme must keep true:
- Its secrets live only in the `credential` dict. The store encrypts it and never shows it.
- `bearer()` is cheap and does no network call: it is what a run reads. Network calls happen in begin/complete/renew.
- A token that can no longer be renewed is `SignInRequired` (a person must act); anything else that goes wrong is an
  `AuthProblem` (try again later). The store treats the two differently.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar
from urllib.parse import urlsplit

from ..app_settings import McpAuthPolicy
from ..connections import ConnectionProblem
from .profiles import Profile, profile_for


class AuthProblem(ConnectionProblem):
    """Signing in, or renewing a sign in, failed in a way worth showing. The message is for people."""


class SignInRequired(AuthProblem):
    """The stored sign in cannot be used again and a person has to sign in once more (it was withdrawn, or it
    lapsed)."""


@dataclass(frozen=True)
class Context:
    """What a scheme is given besides its own state: where it is signing in, and the rules to follow."""

    resource: str  # the tool server's address (canonical, see resource_key)
    policy: McpAuthPolicy
    profile: Profile  # what is different about this server (app/mcp_auth/servers.yaml)
    redirect_uri: str = ""  # where the service sends the person back to (only a sign in needs it)


@dataclass(frozen=True)
class Begun:
    """A sign in that was started: send the person to `url`, and keep `pending` until they come back."""

    url: str
    pending: dict[str, Any]  # secret (a code verifier, for instance): kept in memory, never sent anywhere


@dataclass(frozen=True)
class Granted:
    """What a sign in, or a renewal, produced."""

    credential: dict[str, Any]  # the scheme's own state, secret: stored encrypted
    expires_at: datetime | None  # when the bearer stops working, None when it never does
    account: str = (
        ""  # who it belongs to, for people; "" when this answer does not say (a renewal often does not)
    )
    settings: dict[str, Any] = field(default_factory=dict)  # facts the service gave, never a secret


class AuthScheme(ABC):
    id: ClassVar[str]  # what a tool's file says after `auth:`
    label: ClassVar[str]  # for people

    @abstractmethod
    async def detect(self, ctx: Context) -> bool:
        """Does this server want this way of signing in? Used when a tool is added, so it can say so up front.
        False when it does not, or when that cannot be told: a wrong "yes" is worse than a missing hint."""

    @abstractmethod
    async def begin(self, ctx: Context, state: str, previous: dict[str, Any] | None) -> Begun:
        """Starts a sign in. `state` is the value the service must hand back unchanged, `previous` the credential of an
        earlier sign in to the same server (so a registration is reused instead of made again)."""

    @abstractmethod
    async def complete(self, ctx: Context, pending: dict[str, Any], params: dict[str, str]) -> Granted:
        """Finishes a sign in with what the service sent the person's browser back with."""

    @abstractmethod
    async def renew(self, ctx: Context, credential: dict[str, Any]) -> Granted:
        """A new credential from an old one, before it stops working. Raises SignInRequired when it cannot."""

    @abstractmethod
    def bearer(self, credential: dict[str, Any]) -> str:
        """The value to send as the bearer token right now. No network."""


SCHEMES: dict[str, AuthScheme] = {}


def register(scheme: AuthScheme) -> AuthScheme:
    SCHEMES[scheme.id] = scheme
    return scheme


def get_scheme(scheme_id: str) -> AuthScheme:
    try:
        return SCHEMES[scheme_id]
    except KeyError:
        raise AuthProblem(f"Themis does not know the sign in method '{scheme_id}'") from None


def resource_key(url: str) -> str:
    """A server's address as it is compared and sent as the resource: scheme and host in lower case, default port,
    fragment and trailing slash dropped. Two tools that name the same server the same way share one sign in."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    default = {"https": 443, "http": 80}.get(parts.scheme.lower())
    port = f":{parts.port}" if parts.port and parts.port != default else ""
    host = f"[{host}]" if ":" in host else host
    path = parts.path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme.lower()}://{host}{port}{path}{query}"


async def detect(resource: str, policy: McpAuthPolicy) -> str:
    """The id of the scheme a server at this address wants, or "" when it wants none (or that cannot be told). Asks
    each known scheme in turn, so a new scheme is found without a change here."""
    key = resource_key(resource)
    ctx = Context(key, policy, profile_for(key))
    try:
        async with asyncio.timeout(policy.request_timeout_seconds * 2):
            for scheme in SCHEMES.values():
                if await scheme.detect(ctx):
                    return scheme.id
    except TimeoutError:
        pass
    return ""
