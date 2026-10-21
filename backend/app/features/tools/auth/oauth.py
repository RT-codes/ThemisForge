"""The standard way MCP servers ask people to sign in: OAuth 2.1 with a code, PKCE and, where offered, a client that
registers itself. A server only has to follow the MCP authorization spec; nothing here knows any server by name (what
a particular server needs differently comes from its profile, see profiles.py).

The steps, and the standards each one is:
1. A request without a token is answered 401 with a pointer to the server's metadata (RFC 9728, with the well known
   addresses as the fallback for a server that does not point).
2. The metadata names the authorization server, whose own metadata (RFC 8414, or OpenID's) has the addresses to use.
3. Themis registers itself as a client there (RFC 7591), or uses a client id from the server's profile.
4. The person is sent to approve with a PKCE challenge (RFC 7636) and the tool server named as the resource (RFC 8707).
5. The code that comes back is exchanged for tokens, and later the refresh token for new ones.

Only an access token ever leaves this process, as the bearer token of a run. The refresh token stays in the stored
credential, because the service rotates it on every use and a cell is not a safe place to do that.
"""

import base64
import hashlib
import json
import re
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

import app.features.connections.service as connections
from app.features.tools.auth.profiles import DEFAULT_ACCOUNT_FIELDS
from app.features.tools.auth.scheme import (
    AuthProblem,
    AuthScheme,
    Begun,
    Context,
    Granted,
    SignInRequired,
    register,
)
from app.persistence.models import utcnow

MAX_REPLY = 1_000_000  # bytes read from a service: a reply cannot be allowed to fill memory
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
# What a token answer holds that is not a fact about the account (the rest is kept as settings, for people).
NOT_SETTINGS = {"access_token", "refresh_token", "id_token", "token_type", "expires_in", "client_secret"}
# Errors that mean the refresh token is no good any more and only a new sign in helps.
TERMINAL_ERRORS = {"invalid_grant", "invalid_client", "unauthorized_client", "invalid_token", "access_denied"}
_PARAM = re.compile(r'([A-Za-z_][\w-]*)=(?:"([^"]*)"|([^\s,]+))')


# ----- talking to the service -----


def _safe(url: str, what: str) -> str:
    """Every address that comes from a server's own answer is checked before it is called: it must be a secure web
    address (plain http only for this machine, for tools under development) and carry no password."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    secure = parts.scheme == "https" or (parts.scheme == "http" and host in LOCAL_HOSTS)
    if not secure or not host or parts.username or parts.password:
        raise AuthProblem(f"The server's {what} is not a secure web address, so Themis will not use it.")
    return url


async def _send(
    method: str, url: str, timeout: float, **kwargs: Any
) -> tuple[int, httpx.Headers, dict[str, Any] | None]:
    """One call to a service: its status, headers and JSON body (None when the body was not a JSON object).
    Redirects are not followed and a huge answer is cut off, because what answers is a third party."""
    host = urlsplit(url).hostname or url
    try:
        async with (
            connections.http_client() as client,
            client.stream(method, url, timeout=timeout, **kwargs) as reply,
        ):
            raw = b""
            async for chunk in reply.aiter_bytes():
                raw += chunk
                if len(raw) > MAX_REPLY:
                    break
            status, headers = reply.status_code, reply.headers
    except httpx.TimeoutException:
        raise AuthProblem(f"{host} did not answer in time.") from None
    except httpx.HTTPError:
        raise AuthProblem(f"Could not reach {host}. Check the address, and that it is running.") from None
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    return status, headers, body if isinstance(body, dict) else None


def _challenge_params(header: str) -> dict[str, str]:
    """The parameters of a WWW-Authenticate: Bearer header (`resource_metadata`, `scope`, `error`, ...)."""
    return {
        m.group(1).lower(): m.group(2) if m.group(2) is not None else m.group(3)
        for m in _PARAM.finditer(header)
    }


def _origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}", parts.path.rstrip("/")


async def _challenge(ctx: Context) -> tuple[int, dict[str, str]]:
    """What the server says to a first request with no token: its status and the Bearer challenge's parameters."""
    status, headers, _ = await _send(
        "POST",
        _safe(ctx.resource, "address"),
        ctx.policy.request_timeout_seconds,
        headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "themis", "version": "1"},
            },
        },
    )
    return status, _challenge_params(headers.get("www-authenticate", ""))


async def _protected_resource(ctx: Context, hint: str) -> dict[str, Any] | None:
    """The server's own description of how it is protected (RFC 9728): where the header pointed, else the well known
    address with the server's path, else the one at its root."""
    origin, path = _origin(ctx.resource)
    urls = [hint] if hint else []
    urls += [
        f"{origin}/.well-known/oauth-protected-resource{path}",
        f"{origin}/.well-known/oauth-protected-resource",
    ]
    for url in dict.fromkeys(urls):
        status, _, body = await _send(
            "GET", _safe(url, "metadata address"), ctx.policy.request_timeout_seconds
        )
        if status == 200 and body and isinstance(body.get("authorization_servers"), list):
            return body
    return None


async def _discover(ctx: Context) -> dict[str, Any]:
    """Where to register, send the person and exchange codes. Plain data, so it can be stored with the sign in."""
    status, challenge = await _challenge(ctx)
    if status not in (401, 403):
        raise AuthProblem(
            "This server did not ask for a sign in"
            + (f" (it answered HTTP {status})." if status >= 300 else ", so there is nothing to sign in to.")
        )
    resource = await _protected_resource(ctx, challenge.get("resource_metadata", ""))
    servers = [s for s in (resource or {}).get("authorization_servers", []) if isinstance(s, str)]
    origin, _ = _origin(ctx.resource)
    issuer = (ctx.profile.issuer or (servers[0] if servers else origin)).rstrip("/")
    base, path = _origin(_safe(issuer, "authorization server address"))
    candidates = [
        f"{base}/.well-known/oauth-authorization-server{path}",
        f"{base}/.well-known/openid-configuration{path}",
    ] + ([f"{issuer}/.well-known/openid-configuration"] if path else [])
    meta = None
    for url in dict.fromkeys(candidates):
        status, _, body = await _send("GET", url, ctx.policy.request_timeout_seconds)
        if status == 200 and body and "authorization_endpoint" in body and "token_endpoint" in body:
            meta = body
            break
    if meta is None:
        raise AuthProblem("The server asks for a sign in, but Themis could not find out where it happens.")
    if str(meta.get("issuer", issuer)).rstrip("/") != issuer:
        # RFC 8414: the metadata must name the server it was fetched for, or a different server could be passed off
        raise AuthProblem("The server's sign in details name a different authorization server. Stopped.")
    if "S256" not in (meta.get("code_challenge_methods_supported") or ["S256"]):
        raise AuthProblem(
            "The server's sign in does not support the safe code exchange Themis requires (PKCE)."
        )
    advertised = (resource or {}).get("scopes_supported") or []
    return {
        "issuer": issuer,
        "authorization_endpoint": _safe(str(meta["authorization_endpoint"]), "sign in address"),
        "token_endpoint": _safe(str(meta["token_endpoint"]), "token address"),
        "registration_endpoint": _safe(str(meta["registration_endpoint"]), "registration address")
        if meta.get("registration_endpoint")
        else "",
        "token_auth_methods": [
            m for m in meta.get("token_endpoint_auth_methods_supported") or [] if isinstance(m, str)
        ],
        "iss_in_response": bool(meta.get("authorization_response_iss_parameter_supported")),
        "scope": challenge.get("scope") or " ".join(s for s in advertised if isinstance(s, str)),
    }


# ----- the client and the tokens -----


async def _register(ctx: Context, server: dict[str, Any]) -> dict[str, Any]:
    """The client Themis signs in as at this authorization server: from the profile when it has one, else a new
    registration."""
    base = {"redirect_uri": ctx.redirect_uri, "issuer": server["issuer"]}
    if ctx.profile.client_id:
        return {**base, "client_id": ctx.profile.client_id, "client_secret": "", "auth_method": "none"}
    if not server["registration_endpoint"]:
        raise AuthProblem(
            "This server does not let apps register themselves. Register Themis there by hand and add its client "
            "id to app/mcp_auth/servers.yaml."
        )
    methods = server["token_auth_methods"]
    method = "none" if not methods or "none" in methods else "client_secret_basic"
    status, _, reply = await _send(
        "POST",
        server["registration_endpoint"],
        ctx.policy.request_timeout_seconds,
        headers={"Accept": "application/json"},
        json={
            "client_name": ctx.policy.client_name,
            "redirect_uris": [ctx.redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": method,
        },
    )
    if status not in (200, 201) or not reply or not isinstance(reply.get("client_id"), str):
        detail = (reply or {}).get("error_description") or (reply or {}).get("error") or f"HTTP {status}"
        raise AuthProblem(f"The server did not accept Themis as a client: {detail}")
    return {
        **base,
        "client_id": reply["client_id"],
        "client_secret": str(reply.get("client_secret") or ""),
        "auth_method": str(reply.get("token_endpoint_auth_method") or method),
    }


async def _token_call(ctx: Context, server: dict[str, Any], client: dict[str, Any], form: dict[str, str]):
    """A request to the token address, with the client authenticating the way it registered for."""
    form = {**form, "client_id": client["client_id"]}
    options: dict[str, Any] = {}
    if client.get("client_secret"):
        if client.get("auth_method") == "client_secret_post":
            form["client_secret"] = client["client_secret"]
        else:
            options["auth"] = (client["client_id"], client["client_secret"])
    return await _send(
        "POST",
        server["token_endpoint"],
        ctx.policy.request_timeout_seconds,
        data=form,
        headers={"Accept": "application/json"},
        **options,
    )


def _granted(ctx: Context, reply: dict[str, Any], base: dict[str, Any]) -> Granted:
    access = reply.get("access_token")
    if not isinstance(access, str) or not access:
        raise AuthProblem("The server accepted the sign in but sent no access token.")
    if str(reply.get("token_type", "bearer")).lower() != "bearer":
        raise AuthProblem(f"The server sent a '{reply.get('token_type')}' token, which Themis cannot use.")
    refresh = reply.get("refresh_token") or base.get("refresh_token") or ""
    try:
        seconds = int(reply["expires_in"])
    except (KeyError, TypeError, ValueError):
        seconds = 0
    if seconds <= 0 and refresh:
        # No lifetime given: assume the configured one and renew by then, rather than trust it to last forever
        seconds = ctx.profile.token_seconds or ctx.policy.default_token_seconds
    extras = {
        k: v
        for k, v in reply.items()
        if k not in NOT_SETTINGS and isinstance(v, (str, int, bool)) and len(str(v)) <= 500
    }
    account = next(
        (
            str(extras[f]).strip()
            for f in (*ctx.profile.account_fields, *DEFAULT_ACCOUNT_FIELDS)
            if extras.get(f)
        ),
        "",
    )
    credential = {
        **base,
        "access_token": access,
        "refresh_token": refresh,
        "scope": str(reply.get("scope") or base.get("scope") or ""),
    }
    return Granted(
        credential=credential,
        expires_at=utcnow() + timedelta(seconds=seconds) if seconds > 0 else None,
        account=account[:320],
        settings=extras,
    )


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class StandardOAuth(AuthScheme):
    id = "oauth"
    label = "Sign in with the service"

    async def detect(self, ctx: Context) -> bool:
        try:
            status, challenge = await _challenge(ctx)
            if status not in (401, 403):
                return False
            # A bare 401 Bearer is also what a server that wants an API key says: only a pointer to metadata, or
            # metadata at the well known address, says this server signs people in.
            return bool(challenge.get("resource_metadata")) or await _protected_resource(ctx, "") is not None
        except AuthProblem:
            return False

    async def begin(self, ctx: Context, state: str, previous: dict[str, Any] | None) -> Begun:
        if not ctx.redirect_uri:
            raise AuthProblem("Themis does not know its own address to come back to. Set it in Settings.")
        server = await _discover(ctx)
        client = (previous or {}).get("client") or {}
        reusable = (
            client.get("client_id")
            and client.get("issuer") == server["issuer"]
            and client.get("redirect_uri") == ctx.redirect_uri
        )
        if not reusable:  # a client registered again would orphan the grants made with the old one
            client = await _register(ctx, server)
        verifier, challenge = _pkce()
        scope = " ".join(ctx.profile.scopes) if ctx.profile.scopes is not None else server["scope"]
        query = {
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": ctx.redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if scope:
            query["scope"] = scope
        if ctx.profile.send_resource:
            query["resource"] = ctx.resource
        query.update(ctx.profile.authorize_params)
        parts = urlsplit(server["authorization_endpoint"])
        url = urlunsplit(parts._replace(query=urlencode([*parse_qsl(parts.query), *query.items()])))
        return Begun(
            url=url, pending={"verifier": verifier, "server": server, "client": client, "scope": scope}
        )

    async def complete(self, ctx: Context, pending: dict[str, Any], params: dict[str, str]) -> Granted:
        server, client = pending["server"], pending["client"]
        if error := params.get("error"):
            detail = params.get("error_description") or error
            raise AuthProblem(
                "The sign in was declined."
                if error == "access_denied"
                else f"The service refused the sign in: {detail}"
            )
        issuer = params.get("iss")
        if (issuer is None and server["iss_in_response"]) or (
            issuer and issuer.rstrip("/") != server["issuer"]
        ):
            # RFC 9207: the answer must come from the server the sign in was started at
            raise AuthProblem(
                "The sign in came back from a different server than it was started at. Stopped."
            )
        if not params.get("code"):
            raise AuthProblem("The service sent the person back without a sign in code.")
        form = {
            "grant_type": "authorization_code",
            "code": params["code"],
            "redirect_uri": client["redirect_uri"],
            "code_verifier": pending["verifier"],
        }
        if ctx.profile.send_resource:
            form["resource"] = ctx.resource
        status, _, reply = await _token_call(ctx, server, client, form)
        if status >= 400 or not reply:
            detail = (reply or {}).get("error_description") or (reply or {}).get("error") or f"HTTP {status}"
            raise AuthProblem(f"The service would not give a token for that sign in: {detail}")
        return _granted(ctx, reply, {"server": server, "client": client, "scope": pending.get("scope", "")})

    async def renew(self, ctx: Context, credential: dict[str, Any]) -> Granted:
        refresh = credential.get("refresh_token")
        if not refresh:
            raise SignInRequired("This sign in cannot be renewed, so it has to be done again.")
        form = {"grant_type": "refresh_token", "refresh_token": refresh}
        if ctx.profile.send_resource:
            form["resource"] = ctx.resource
        status, _, reply = await _token_call(ctx, credential["server"], credential["client"], form)
        error = str((reply or {}).get("error") or "")
        if status == 429 or status >= 500:
            raise AuthProblem(f"The service could not renew the sign in right now (HTTP {status}).")
        if status >= 400 or not reply:
            if error in TERMINAL_ERRORS or 400 <= status < 500:
                raise SignInRequired("The service ended this sign in. Sign in again to keep using the tool.")
            raise AuthProblem(f"The service did not renew the sign in (HTTP {status}).")
        return _granted(ctx, reply, credential)

    def bearer(self, credential: dict[str, Any]) -> str:
        return str(credential.get("access_token") or "")


register(StandardOAuth())
