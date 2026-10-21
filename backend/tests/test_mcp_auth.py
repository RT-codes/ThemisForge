"""Signing in to tool servers that ask for it (app/mcp_auth): the standard OAuth flow end to end against a fake
service, tokens for runs, renewal, and the numbers that come from Settings."""

import base64
import hashlib
import json
import tomllib
from datetime import timedelta
from urllib.parse import parse_qs, parse_qsl, urlsplit

import httpx
import pytest
import yaml
from sqlalchemy import select

import app.features.connections.service as connections
import app.features.tools.auth.oauth as oauth_module
from app.config import settings
from app.features.project_config.store import config_dir
from app.features.system.settings import AppSettings, McpAuthPolicy, save_settings
from app.features.tools.auth import (
    ACTIVE,
    NEEDS_SIGN_IN,
    AuthProblem,
    McpLogins,
    SignInRequired,
    detect,
    profiles,
    resource_key,
    unseal,
)
from app.features.tools.keys import HIDDEN
from app.persistence.models import McpLogin, utcnow
from tests.conftest import drain, make_project, make_task, register
from tests.registry_fakes import entry
from tests.test_agents import make_agent
from tests.test_harness import connect
from tests.test_tools import make_server

MCP = "https://mcp.example.test/mcp"
AUTH = "https://auth.example.test"
CALLBACK = "http://test/api/mcp-auth/callback"


class FakeService:
    """A tool server that asks for a sign in and its authorization server, in one. It checks what a real one checks
    (the PKCE verifier, the redirect address, that a refresh token is the current one) and remembers what it saw."""

    def __init__(self, mcp_url: str = MCP) -> None:
        parts = urlsplit(mcp_url)
        self.host, self.path = parts.hostname, parts.path
        self.expires_in: int | None = 36000
        self.requires_sign_in = True
        self.pointer = True  # the 401 says where the metadata is
        self.well_known = True  # the metadata is also at the well known address
        self.registration = True
        self.token_endpoint = f"{AUTH}/token"
        self.refresh_failure: tuple[int, dict] | None = None
        self.callback = CALLBACK  # the redirect address the sign in must register and use
        self.registrations = 0
        self.refreshes = 0
        self.access, self.refresh = "access-0", "refresh-0"
        self.codes: dict[str, dict] = {}
        self.authorizations: list[dict] = []
        self.token_forms: list[dict] = []
        self._n = 0

    def approve(self, url: str) -> dict[str, str]:
        """The person approves on the service's page: what the redirect back carries."""
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.authorizations.append(query)
        code = f"code-{len(self.authorizations)}"
        self.codes[code] = {
            "challenge": query["code_challenge"],
            "redirect_uri": query["redirect_uri"],
            "client_id": query["client_id"],
        }
        return {"code": code, "state": query["state"]}

    def _tokens(self, first: bool) -> httpx.Response:
        self._n += 1
        self.access, self.refresh = f"access-{self._n}", f"refresh-{self._n}"
        body = {"access_token": self.access, "token_type": "bearer", "refresh_token": self.refresh}
        if self.expires_in is not None:
            body["expires_in"] = self.expires_in
        if first:  # only the first answer says whose workspace this is
            body |= {"workspace_name": "Acme", "workspace_id": "w-1", "bot_id": "b-1"}
        return httpx.Response(200, json=body)

    def handle(self, request: httpx.Request) -> httpx.Response:
        url, path = request.url, request.url.path
        if url.host == self.host:
            if path == f"/.well-known/oauth-protected-resource{self.path}":
                if not self.well_known:
                    return httpx.Response(404)
                return httpx.Response(
                    200,
                    json={
                        "resource": f"https://{self.host}{self.path}",
                        "authorization_servers": [AUTH],
                        "scopes_supported": ["read", "write"],
                    },
                )
            if path == self.path and request.method == "POST":
                if (
                    not self.requires_sign_in
                    or request.headers.get("authorization") == f"Bearer {self.access}"
                ):
                    body = json.loads(request.content)
                    if body.get("method") == "initialize":
                        info = {"serverInfo": {"name": "Docs", "version": "1"}}
                        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": info})
                    return httpx.Response(202)
                challenge = 'Bearer realm="OAuth"'
                if self.pointer:
                    where = f"https://{self.host}/.well-known/oauth-protected-resource{self.path}"
                    challenge += f', resource_metadata="{where}", scope="read"'
                return httpx.Response(401, headers={"www-authenticate": challenge})
        if url.host == "auth.example.test":
            if path == "/.well-known/oauth-authorization-server":
                meta = {
                    "issuer": AUTH,
                    "authorization_endpoint": f"{AUTH}/authorize",
                    "token_endpoint": self.token_endpoint,
                    "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["none"],
                }
                if self.registration:
                    meta["registration_endpoint"] = f"{AUTH}/register"
                return httpx.Response(200, json=meta)
            if path == "/register":
                self.registrations += 1
                sent = json.loads(request.content)
                assert (
                    sent["redirect_uris"] == [self.callback] and sent["token_endpoint_auth_method"] == "none"
                )
                return httpx.Response(201, json={"client_id": f"client-{self.registrations}"})
            if path == "/token":
                form = dict(parse_qsl(request.content.decode()))
                self.token_forms.append(form)
                if form["grant_type"] == "authorization_code":
                    code = self.codes.pop(form.get("code", ""), None)
                    digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
                    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
                    if (
                        code is None
                        or code["challenge"] != challenge
                        or code["client_id"] != form["client_id"]
                    ):
                        return httpx.Response(400, json={"error": "invalid_grant"})
                    assert form["redirect_uri"] == code["redirect_uri"]
                    return self._tokens(first=True)
                self.refreshes += 1
                if self.refresh_failure:
                    status, body = self.refresh_failure
                    return httpx.Response(status, json=body)
                if form["refresh_token"] != self.refresh:  # a rotated out token is no good
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return self._tokens(first=False)
        return httpx.Response(404)


@pytest.fixture
def service(monkeypatch):
    fake = FakeService()
    monkeypatch.setattr(
        connections, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handle))
    )
    monkeypatch.setattr(settings, "secret_key", "a-real-secret-key-for-tests-0123456789")
    return fake


async def make_tool(client, pid: int, name: str = "docs", url: str = MCP, **body) -> dict:
    return await make_server(client, pid, name=name, kind="http", url=url, auth="oauth", **body)


async def sign_in(
    client, fake: FakeService, server_id: int, return_to: str = "/projects/1"
) -> httpx.Response:
    started = await client.post(f"/api/mcp-servers/{server_id}/sign-in", json={"return_to": return_to})
    assert started.status_code == 200, started.text
    params = fake.approve(started.json()["url"])
    return await client.get("/api/mcp-auth/callback", params=params, follow_redirects=False)


async def logins(maker) -> list[McpLogin]:
    async with maker() as s:
        return list((await s.scalars(select(McpLogin).order_by(McpLogin.id))).all())


async def run_with(client, scheduler, maker, tool_id: int, pid: int, agent_name: str = "Researcher") -> dict:
    agent = await make_agent(client, pid, name=agent_name, mcp_servers=[tool_id])
    task = await make_task(client, pid, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    return (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]


# ----- signing in -----


async def test_signing_in_stores_the_tokens_and_says_who_signed_in(client, maker, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    assert tool["sign_in"]["state"] == "not_signed_in" and tool["auth"] == "oauth"

    done = await sign_in(client, service, tool["id"], return_to="/projects/1#tools")
    assert done.status_code == 303
    location = urlsplit(done.headers["location"])
    assert location.path == "/projects/1" and location.fragment == "tools"  # the page's own #fragment is kept
    assert parse_qs(location.query) == {"mcp_sign_in": ["ok"], "message": ["Acme"]}

    # what the person was sent to approve: the standard parameters, the server named as the resource
    query = service.authorizations[0]
    assert query["code_challenge_method"] == "S256" and query["response_type"] == "code"
    assert query["resource"] == MCP and query["redirect_uri"] == service.callback
    assert query["scope"] == "read"  # the server's challenge named a scope; no profile says otherwise
    assert service.token_forms[0]["resource"] == MCP

    shown = (await client.get(f"/api/projects/{pid}/mcp-servers")).json()[0]["sign_in"]
    assert shown["state"] == "signed_in" and shown["account"] == "Acme" and shown["expires_at"]
    (listed,) = (await client.get("/api/mcp-auth/logins")).json()
    assert listed["resource"] == MCP and listed["status"] == "active" and "access-1" not in json.dumps(listed)
    (stored,) = await logins(maker)
    assert stored.settings["workspace_id"] == "w-1"  # what the service said, for people
    assert "access-1" not in stored.credential_encrypted  # encrypted at rest
    assert unseal(stored)["access_token"] == "access-1" and unseal(stored)["refresh_token"] == "refresh-1"


async def test_a_declined_or_replayed_sign_in_stores_nothing(client, maker, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    started = await client.post(f"/api/mcp-servers/{tool['id']}/sign-in", json={"return_to": "/p"})
    state = parse_qs(urlsplit(started.json()["url"]).query)["state"][0]

    declined = await client.get(
        "/api/mcp-auth/callback", params={"error": "access_denied", "state": state}, follow_redirects=False
    )
    assert parse_qs(urlsplit(declined.headers["location"]).query)["mcp_sign_in"] == ["error"]
    again = await client.get(
        "/api/mcp-auth/callback", params={"code": "x", "state": state}, follow_redirects=False
    )
    assert "expired" in parse_qs(urlsplit(again.headers["location"]).query)["message"][0]
    unknown = await client.get(
        "/api/mcp-auth/callback", params={"code": "x", "state": "nope"}, follow_redirects=False
    )
    assert unknown.status_code == 303
    assert await logins(maker) == []


async def test_the_callback_can_only_send_the_browser_to_a_page_of_this_site(client, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    done = await sign_in(client, service, tool["id"], return_to="https://evil.example/steal")
    assert urlsplit(done.headers["location"]).netloc == "" and done.headers["location"].startswith("/?")
    done = await sign_in(client, service, tool["id"], return_to="//evil.example")
    assert done.headers["location"].startswith("/?")


async def test_a_tool_that_does_not_ask_for_a_sign_in_cannot_be_signed_in_to(client, service):
    await register(client)
    pid = (await make_project(client))["id"]
    plain = await make_server(client, pid, name="web", kind="http", url=MCP)
    r = await client.post(f"/api/mcp-servers/{plain['id']}/sign-in", json={})
    assert r.status_code == 409


async def test_a_server_that_does_not_ask_for_a_sign_in_is_said_so(client, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    service.requires_sign_in = False
    r = await client.post(f"/api/mcp-servers/{tool['id']}/sign-in", json={})
    assert r.status_code == 502 and "did not ask for a sign in" in r.json()["detail"]


async def test_a_server_that_cannot_register_apps_is_told_what_to_do(client, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    service.registration = False
    r = await client.post(f"/api/mcp-servers/{tool['id']}/sign-in", json={})
    assert r.status_code == 502 and "servers.yaml" in r.json()["detail"]


async def test_every_address_a_server_names_must_be_a_secure_web_address(client, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    service.token_endpoint = "http://10.0.0.5/token"
    r = await client.post(f"/api/mcp-servers/{tool['id']}/sign-in", json={})
    assert r.status_code == 502 and "secure web address" in r.json()["detail"]
    assert oauth_module._safe("http://localhost:9000/token", "x")  # a tool under development on this machine
    for bad in ("http://example.com/x", "ftp://example.com/x", "https://user:pw@example.com/x", "https:///x"):
        with pytest.raises(AuthProblem):
            oauth_module._safe(bad, "x")


async def test_signing_in_needs_a_real_secret_key_because_the_tokens_are_encrypted_with_it(client):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    r = await client.post(f"/api/mcp-servers/{tool['id']}/sign-in", json={})
    assert r.status_code == 409 and "THEMIS_SECRET_KEY" in r.json()["detail"]


# ----- runs -----


async def test_a_run_gets_the_token_as_a_secret_variable_and_the_tool_points_at_it(
    client, scheduler, cells, maker, service
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    attempt = await run_with(client, scheduler, maker, tool["id"], pid)
    assert attempt["status"] == "succeeded"
    spec = cells.specs[0]
    assert spec.secret_files["/run/themis-secrets/keys/MCP_DOCS_TOKEN"] == "access-1"
    config = tomllib.loads(spec.secret_files["/run/themis-secrets/codex/config.toml"])["mcp_servers"]
    assert config["docs"] == {"url": MCP, "bearer_token_env_var": "MCP_DOCS_TOKEN"}
    assert "access-1" not in spec.script and 'export MCP_DOCS_TOKEN="$(cat ' in spec.script


async def test_a_token_in_the_log_is_hidden(client, scheduler, cells, maker, service):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    cells.log_text = "Authorization: Bearer access-1\n"
    agent = await make_agent(client, pid, mcp_servers=[tool["id"]])
    task = await make_task(client, pid, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    log = (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    assert "access-1" not in log and f"Bearer {HIDDEN}" in log


async def test_a_run_stops_before_the_cell_when_the_tool_was_never_signed_in_to(
    client, scheduler, cells, maker, service
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    attempt = await run_with(client, scheduler, maker, tool["id"], pid)
    assert attempt["status"] == "failed" and cells.specs == []
    log = (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    assert "'docs' needs a sign in" in log


async def test_a_token_that_would_not_last_the_run_is_renewed_first_and_the_new_refresh_token_kept(
    client, scheduler, cells, maker, service
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    (before,) = await logins(maker)

    service.expires_in = 7200
    async with maker() as s:  # the token has 5 minutes left: less than the run's time limit and the margin
        row = await s.get(McpLogin, before.id)
        row.expires_at = utcnow() + timedelta(minutes=5)
        await s.commit()
    await run_with(client, scheduler, maker, tool["id"], pid)

    assert service.refreshes == 1
    assert cells.specs[0].secret_files["/run/themis-secrets/keys/MCP_DOCS_TOKEN"] == "access-2"
    (after,) = await logins(maker)
    assert after.expires_at > utcnow() + timedelta(hours=1) and after.refreshed_at > before.refreshed_at
    assert (
        after.account == "Acme" and after.settings["workspace_id"] == "w-1"
    )  # a renewal does not repeat these
    assert service.token_forms[-1]["refresh_token"] == "refresh-1"
    # and the next run finds the rotated refresh token, not the old one
    again = await scheduler.mcp_logins.bearer(after.id, need_seconds=10**6)
    assert again == "access-3" and service.refreshes == 2


async def test_a_token_that_lasts_long_enough_is_not_renewed(client, maker, scheduler, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    assert await scheduler.mcp_logins.bearer(row.id, need_seconds=60) == "access-1"
    assert service.refreshes == 0


async def test_runs_that_start_together_renew_a_token_once_and_never_reuse_a_rotated_refresh_token(
    client, maker, scheduler, service
):
    import asyncio

    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    async with maker() as s:  # 5 minutes left: every run below finds it too short
        (await s.get(McpLogin, row.id)).expires_at = utcnow() + timedelta(minutes=5)
        await s.commit()
    tokens = await asyncio.gather(*(scheduler.mcp_logins.bearer(row.id, 3600) for _ in range(5)))
    assert service.refreshes == 1 and set(tokens) == {
        "access-2"
    }  # the first renewed, the rest found it fresh

    # renewals that are all needed go one at a time, each with the refresh token the one before it produced: the
    # service refuses a token that was rotated out, so two at once with the same one would fail
    more = await asyncio.gather(*(scheduler.mcp_logins.bearer(row.id, 10**6) for _ in range(4)))
    assert len(set(more)) == 4 and service.refreshes == 5
    assert (await logins(maker))[0].status == ACTIVE


async def test_one_sign_in_serves_every_project_and_every_agent_of_its_owner(
    client, scheduler, cells, maker, service
):
    me = await register(client)
    await connect(maker, me["id"])
    alpha = (await make_project(client, "Alpha"))["id"]
    beta = (await make_project(client, "Beta"))["id"]
    in_alpha = await make_tool(client, alpha)
    in_beta = await make_tool(client, beta)  # tools belong to a project, so each project has its own
    assert in_beta["sign_in"]["state"] == "not_signed_in"

    await sign_in(client, service, in_alpha["id"])  # once, from one project

    shown = (await client.get(f"/api/projects/{beta}/mcp-servers")).json()[0]["sign_in"]
    assert shown["state"] == "signed_in" and shown["account"] == "Acme"
    assert len(await logins(maker)) == 1 and service.registrations == 1

    # several agents, in both projects, run with that one sign in
    for pid, tool, agent in ((alpha, in_alpha, "One"), (beta, in_beta, "Two"), (beta, in_beta, "Three")):
        assert (await run_with(client, scheduler, maker, tool["id"], pid, agent))["status"] == "succeeded"
    tokens = [s.secret_files["/run/themis-secrets/keys/MCP_DOCS_TOKEN"] for s in cells.specs]
    assert tokens == ["access-1"] * 3 and service.refreshes == 0


# ----- a sign in that stops working -----


async def test_a_refused_renewal_marks_the_sign_in_and_signing_in_again_keeps_the_same_client(
    client, scheduler, cells, maker, service
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    service.refresh_failure = (400, {"error": "invalid_grant"})
    with pytest.raises(SignInRequired):
        await scheduler.mcp_logins.bearer((await logins(maker))[0].id, need_seconds=10**6)

    (row,) = await logins(maker)
    assert row.status == NEEDS_SIGN_IN and row.expires_at is None and "ended" in row.error
    shown = (await client.get(f"/api/projects/{pid}/mcp-servers")).json()[0]["sign_in"]
    assert shown["state"] == "needs_sign_in" and shown["error"]
    attempt = await run_with(client, scheduler, maker, tool["id"], pid)
    assert attempt["status"] == "failed" and cells.specs == []

    service.refresh_failure = None
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    assert row.status == ACTIVE and row.error == "" and service.registrations == 1  # no second registration
    assert service.authorizations[-1]["client_id"] == "client-1"


async def test_a_service_that_is_down_keeps_a_token_that_still_works_and_fails_one_that_does_not(
    client, maker, scheduler, service
):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    service.refresh_failure = (503, {})
    assert (
        await scheduler.mcp_logins.bearer(row.id, need_seconds=10**6) == "access-1"
    )  # still valid for hours
    async with maker() as s:
        (await s.get(McpLogin, row.id)).expires_at = utcnow() - timedelta(minutes=1)
        await s.commit()
    with pytest.raises(AuthProblem) as e:
        await scheduler.mcp_logins.bearer(row.id)
    assert not isinstance(e.value, SignInRequired)
    assert (await logins(maker))[0].status == ACTIVE  # the service being down is not the end of the sign in


async def test_signing_out_makes_the_tool_ask_for_a_sign_in_again(client, maker, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    assert (await client.delete(f"/api/mcp-auth/logins/{row.id}")).status_code == 204
    assert (await client.get(f"/api/projects/{pid}/mcp-servers")).json()[0]["sign_in"][
        "state"
    ] == "not_signed_in"
    assert (await client.delete(f"/api/mcp-auth/logins/{row.id}")).status_code == 404


async def test_one_users_sign_in_is_not_seen_or_removable_by_another(client, maker, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    await register(client, "b@c.co", "Bob")
    assert (await client.get("/api/mcp-auth/logins")).json() == []
    assert (await client.delete(f"/api/mcp-auth/logins/{row.id}")).status_code == 404
    assert (await client.post(f"/api/mcp-servers/{tool['id']}/sign-in", json={})).status_code == 404


# ----- the numbers come from Settings -----


async def test_how_long_a_token_is_assumed_to_last_is_a_setting(client, maker, service):
    await register(client)
    async with maker() as s:
        await save_settings(s, AppSettings(mcp_auth=McpAuthPolicy(default_token_seconds=120)))
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    service.expires_in = None  # the service does not say
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    assert timedelta(seconds=100) < row.expires_at - utcnow() <= timedelta(seconds=120)


async def test_what_the_service_says_about_a_tokens_life_wins_over_the_setting(client, maker, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    service.expires_in = 86400
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    assert row.expires_at - utcnow() > timedelta(hours=23)


async def test_how_early_a_token_is_renewed_is_a_setting(client, maker, scheduler, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    service.expires_in = 1000
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    assert await scheduler.mcp_logins.bearer(row.id, need_seconds=0) == "access-1"  # margin 600 < 1000
    async with maker() as s:
        await save_settings(s, AppSettings(mcp_auth=McpAuthPolicy(refresh_margin_seconds=2000)))
    assert await scheduler.mcp_logins.bearer(row.id, need_seconds=0) == "access-2"  # now it is too short


async def test_a_sign_in_nobody_used_is_kept_alive_and_the_number_of_days_is_a_setting(
    client, maker, scheduler, service
):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    (row,) = await logins(maker)
    assert await scheduler.mcp_logins.keep_alive() == 0  # used just now
    async with maker() as s:
        (await s.get(McpLogin, row.id)).refreshed_at = utcnow() - timedelta(days=10)
        await s.commit()
    assert await scheduler.mcp_logins.keep_alive() == 1 and service.refreshes == 1
    async with maker() as s:
        (await s.get(McpLogin, row.id)).refreshed_at = utcnow() - timedelta(days=10)
        await save_settings(s, AppSettings(mcp_auth=McpAuthPolicy(keepalive_days=0)))
    assert await scheduler.mcp_logins.keep_alive() == 0  # switched off


def test_the_address_browsers_use_must_be_an_address_without_a_path():
    assert (
        McpAuthPolicy(public_url=" https://themis.example.com/ ").public_url == "https://themis.example.com"
    )
    for bad in ("themis.example.com", "https://themis.example.com/app", "ftp://x"):
        with pytest.raises(ValueError):
            McpAuthPolicy(public_url=bad)


async def test_the_public_address_is_what_the_service_is_told_to_come_back_to(client, maker, service):
    await register(client)
    async with maker() as s:
        await save_settings(s, AppSettings(mcp_auth=McpAuthPolicy(public_url="https://themis.example.com")))
    service.callback = "https://themis.example.com/api/mcp-auth/callback"
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    done = await sign_in(client, service, tool["id"])
    assert parse_qs(urlsplit(done.headers["location"]).query)["mcp_sign_in"] == ["ok"]
    assert service.authorizations[0]["redirect_uri"] == service.callback


# ----- servers that need a nudge -----


async def test_a_servers_profile_changes_what_is_asked_for_without_touching_the_code(
    client, service, monkeypatch, tmp_path
):
    file = tmp_path / "servers.yaml"
    file.write_text(
        yaml.safe_dump(
            {
                "servers": [
                    {
                        "match": "*.example.test",
                        "name": "Example",
                        "scopes": [],
                        "authorize_params": {"prompt": "consent"},
                        "send_resource": False,
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(profiles, "PROFILES_FILE", file)
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    await sign_in(client, service, tool["id"])
    query = service.authorizations[0]
    assert "scope" not in query and "resource" not in query and query["prompt"] == "consent"
    assert "resource" not in service.token_forms[0]


def test_a_profile_matches_by_host_and_a_broken_file_means_the_standard_one(tmp_path, monkeypatch):
    assert profiles.profile_for("https://mcp.notion.com/mcp").scopes == ()  # the bundled file
    assert profiles.profile_for("https://mcp.notion.com/mcp").authorize_params == {"prompt": "consent"}
    assert profiles.profile_for("https://other.example/mcp").scopes is None
    broken = tmp_path / "servers.yaml"
    broken.write_text("servers: [: not yaml")
    monkeypatch.setattr(profiles, "PROFILES_FILE", broken)
    assert profiles.profile_for("https://mcp.notion.com/mcp") == profiles.Profile()
    monkeypatch.setattr(profiles, "PROFILES_FILE", tmp_path / "missing.yaml")
    assert profiles.profile_for("https://mcp.notion.com/mcp") == profiles.Profile()


def test_a_servers_address_is_compared_in_one_form():
    assert resource_key("HTTPS://MCP.Example.test:443/mcp/") == "https://mcp.example.test/mcp"
    assert resource_key("https://mcp.example.test") == "https://mcp.example.test"
    assert resource_key("http://localhost:8080/x#frag") == "http://localhost:8080/x"


# ----- telling that a server wants a sign in -----


async def test_a_server_that_points_at_its_metadata_is_one_that_signs_people_in(service):
    policy = McpAuthPolicy()
    assert await detect(MCP, policy) == "oauth"
    service.pointer = False  # no pointer in the 401, but the metadata is where it is expected
    assert await detect(MCP, policy) == "oauth"
    service.well_known = False  # a bare 401 Bearer is what a server that wants an API key says
    assert await detect(MCP, policy) == ""
    service.requires_sign_in = False
    assert await detect(MCP, policy) == ""


@pytest.mark.usefixtures("fresh_caches")
async def test_prefilling_a_registry_tool_says_when_it_wants_a_sign_in(client, registry, monkeypatch):
    fake = FakeService("https://time.b77.ai/mcp")
    monkeypatch.setattr(
        connections, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handle))
    )
    await register(client)
    pid = (await make_project(client))["id"]
    registry.entries["ai.b77/time"] = entry("remote_open")
    r = await client.post(f"/api/projects/{pid}/mcp-registry/prefill", json={"name": "ai.b77/time"})
    assert (
        r.status_code == 200 and r.json()["auth"] == "oauth" and r.json()["url"] == "https://time.b77.ai/mcp"
    )
    fake.requires_sign_in = False
    r = await client.post(f"/api/projects/{pid}/mcp-registry/prefill", json={"name": "ai.b77/time"})
    assert r.json()["auth"] == ""


# ----- the tool itself -----


async def test_a_tool_says_it_signs_in_in_its_file_and_not_both_that_and_a_key(client, maker, service):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    file = config_dir(pid) / "mcp" / "docs.yaml"
    assert yaml.safe_load(file.read_text())["auth"] == "oauth"

    key = await client.post("/api/secrets", json={"name": "K", "kind": "x", "value": "abcdefgh12345"})
    both = await client.put(
        f"/api/mcp-servers/{tool['id']}",
        json={
            "name": "docs",
            "kind": "http",
            "url": MCP,
            "auth": "oauth",
            "bearer_secret_id": key.json()["id"],
        },
    )
    assert both.status_code == 422 and "not both" in json.dumps(both.json())
    unknown = await client.put(
        f"/api/mcp-servers/{tool['id']}", json={"name": "docs", "kind": "http", "url": MCP, "auth": "magic"}
    )
    assert unknown.status_code == 422


async def test_a_command_tool_has_no_sign_in(client):
    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_server(client, pid, name="files", auth="oauth")
    assert tool["auth"] == ""


async def test_testing_a_tool_that_signs_in_uses_its_token(client, monkeypatch, service):
    import app.features.tools.service as tools_router
    from app.features.tools.mcp import ProbeResult

    await register(client)
    pid = (await make_project(client))["id"]
    tool = await make_tool(client, pid)
    seen = []

    async def fake_probe(url, bearer):
        seen.append(bearer)
        return ProbeResult(True, "Connected to Docs 1. It offers 1 tool.", ("search",))

    monkeypatch.setattr(tools_router, "probe_http", fake_probe)
    first = (await client.post(f"/api/mcp-servers/{tool['id']}/test")).json()
    assert seen == [None] and "has not signed in" in first["message"]
    await sign_in(client, service, tool["id"])
    second = (await client.post(f"/api/mcp-servers/{tool['id']}/test")).json()
    assert seen == [None, "access-1"] and second["ok"] and second["tools"] == ["search"]


async def test_the_sign_in_store_is_what_the_app_and_the_scheduler_share(client, scheduler):
    from app.main import app

    assert isinstance(app.state.mcp_logins, McpLogins) and scheduler.mcp_logins is app.state.mcp_logins
