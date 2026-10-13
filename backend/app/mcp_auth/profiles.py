"""What one tool server does differently from the standard, read from servers.yaml.

The standard way of signing in needs no knowledge of a server: it finds out how the server wants it from the server
itself. Some servers still need a nudge (a scope they do not advertise, a parameter that makes the consent screen
appear, a client that was registered by hand, a different place to look for the account name). Those facts are data, in
a file that is read on every use, so a fix for one server is an edit to that file and not a change to the code.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

PROFILES_FILE = Path(__file__).with_name("servers.yaml")

# Where a service says whose sign in this is, in the order they are tried (a profile can name its own first).
DEFAULT_ACCOUNT_FIELDS = ("workspace_name", "account", "email", "username", "user_id")


@dataclass(frozen=True)
class Profile:
    name: str = ""  # the service, for people ("Notion")
    # None = ask for what the server advertises (or nothing). A list, even an empty one, is asked for exactly.
    scopes: tuple[str, ...] | None = None
    authorize_params: dict[str, str] = field(
        default_factory=dict
    )  # extra query parameters on the sign in link
    client_id: str = ""  # a client that was registered by hand, for a server that cannot register apps itself
    issuer: str = ""  # the authorization server, when the server does not say (or says it wrongly)
    send_resource: bool = True  # RFC 8707: name the tool server in the sign in and token requests
    token_seconds: int | None = (
        None  # how long a token lasts when the server does not say, over the global default
    )
    account_fields: tuple[str, ...] = ()


def _strings(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, str):
        return tuple(value.split())
    if isinstance(value, list):
        return tuple(str(v) for v in value if isinstance(v, (str, int)))
    return None


def _profile(item: dict[str, Any]) -> Profile:
    params = item.get("authorize_params")
    seconds = item.get("token_seconds")
    return Profile(
        name=str(item.get("name") or ""),
        scopes=_strings(item["scopes"]) if "scopes" in item else None,
        authorize_params={str(k): str(v) for k, v in params.items()} if isinstance(params, dict) else {},
        client_id=str(item.get("client_id") or ""),
        issuer=str(item.get("issuer") or "").rstrip("/"),
        send_resource=bool(item.get("send_resource", True)),
        token_seconds=seconds if isinstance(seconds, int) and seconds > 0 else None,
        account_fields=_strings(item.get("account_fields")) or (),
    )


def _matches(pattern: str, host: str) -> bool:
    pattern = pattern.lower()
    if pattern.startswith("*."):
        return host.endswith(pattern[1:])
    return host == pattern


def profile_for(resource: str) -> Profile:
    """The profile of the server at this address; the standard one when nothing matches. A broken file is the standard
    profile too: signing in still works for every server that follows the standard."""
    try:
        data = yaml.safe_load(PROFILES_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return Profile()
    items = data.get("servers") if isinstance(data, dict) else None
    host = (urlsplit(resource).hostname or "").lower()
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and _matches(str(item.get("match") or ""), host):
            return _profile(item)
    return Profile()
