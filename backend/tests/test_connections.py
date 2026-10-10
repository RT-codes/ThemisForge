import asyncio

import httpx
import pytest
from sqlalchemy import select

from app import connections
from app.app_settings import AppSettings, save_settings
from app.config import settings
from app.connections import DeviceLogins
from app.github import CREDENTIAL_HELPER, GitHub
from app.keys import HIDDEN
from app.main import app
from app.models import Connection
from tests.conftest import drain, login, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_harness import connect

TOKEN = "github_pat_11AAAAAAA0123456789abcdef"
OAUTH_TOKEN = "gho_oauthtoken0123456789abcdef"


class FakeGitHub:
    """Stands in for github.com and api.github.com, so nothing in the tests goes to the internet."""

    def __init__(self) -> None:
        self.polls = 0
        self.decline = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        path, auth = request.url.path, request.headers.get("authorization", "")
        if request.url.host == "api.github.com":
            if auth not in (f"Bearer {TOKEN}", f"Bearer {OAUTH_TOKEN}"):
                return httpx.Response(401, json={"message": "Bad credentials"})
            if path == "/user":
                return httpx.Response(
                    200,
                    json={"login": "octocat", "id": 583231, "name": "The  Octocat\n"},
                    headers={"x-oauth-scopes": "repo, workflow"},
                )
            if path == "/repos/octocat/hello-world":
                return httpx.Response(200, json={"full_name": "octocat/Hello-World"})
            return httpx.Response(404, json={"message": "Not Found"})
        if path == "/login/device/code":
            return httpx.Response(
                200,
                json={
                    "device_code": "dc-1",
                    "user_code": "ABCD-1234",
                    "verification_uri": "https://github.com/login/device",
                    "expires_in": 900,
                    "interval": 0,
                },
            )
        if path == "/login/oauth/access_token":
            self.polls += 1
            if self.decline:
                return httpx.Response(200, json={"error": "access_denied"})
            if self.polls < 3:
                return httpx.Response(200, json={"error": "authorization_pending"})
            return httpx.Response(200, json={"access_token": OAUTH_TOKEN, "token_type": "bearer"})
        return httpx.Response(404)


@pytest.fixture
def github(monkeypatch, maker):
    fake = FakeGitHub()
    monkeypatch.setattr(app.state, "device_logins", DeviceLogins(maker))
    monkeypatch.setattr(
        connections, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handle))
    )
    monkeypatch.setattr(connections, "MIN_POLL_SECONDS", 0)
    monkeypatch.setattr(settings, "secret_key", "a-real-secret-key-for-tests-0123456789")
    return fake


async def connect_github(client, token=TOKEN) -> dict:
    r = await client.post("/api/connections", json={"provider": "github", "token": token})
    assert r.status_code == 201, r.text
    return r.json()


async def use_github(client, pid: int, conn_id: int, repo: str = "") -> dict:
    r = await client.put(
        f"/api/projects/{pid}/connections/github", json={"connection_id": conn_id, "config": {"repo": repo}}
    )
    assert r.status_code == 200, r.text
    return r.json()


# ----- the list of services -----


async def test_the_list_offers_github_and_a_sign_in_only_once_the_app_id_is_set(client, maker, github):
    await register(client)
    body = (await client.get("/api/connections")).json()
    (gh,) = body["providers"]
    assert (gh["id"], gh["category"], gh["name"]) == ("github", "service", "GitHub")
    methods = {m["id"]: m for m in gh["methods"]}
    assert methods["token"]["available"] and not methods["oauth"]["available"]
    assert "client id" in methods["oauth"]["reason"]
    assert gh["config_fields"][0]["key"] == "repo"
    async with maker() as s:
        await save_settings(s, AppSettings(github_client_id="Iv1.abc123"))
    methods = {m["id"]: m for m in (await client.get("/api/connections")).json()["providers"][0]["methods"]}
    assert methods["oauth"]["available"]


# ----- connecting with a token -----


async def test_a_token_is_checked_with_github_and_stored_encrypted(client, maker, github):
    await register(client)
    conn = await connect_github(client)
    assert (conn["provider"], conn["method"], conn["account"]) == ("github", "token", "octocat")
    assert conn["settings"]["login"] == "octocat" and conn["settings"]["name"] == "The Octocat"
    assert TOKEN not in str((await client.get("/api/connections")).json())  # never handed back
    async with maker() as s:
        row = (await s.scalars(select(Connection))).one()
    assert TOKEN not in row.credential_encrypted and connections.unseal(row) == {"token": TOKEN}


async def test_a_rejected_token_is_not_stored(client, github):
    await register(client)
    r = await client.post("/api/connections", json={"provider": "github", "token": "nope"})
    assert r.status_code == 422 and "rejected" in r.json()["detail"]
    assert (await client.get("/api/connections")).json()["connections"] == []


async def test_nothing_is_stored_under_the_development_secret_key(client, monkeypatch):
    await register(client)
    r = await client.post("/api/connections", json={"provider": "github", "token": TOKEN})
    assert r.status_code == 409 and "THEMIS_SECRET_KEY" in r.json()["detail"]


async def test_connecting_the_same_account_again_replaces_the_credential(client, github):
    await register(client)
    first = await connect_github(client)
    second = await connect_github(client, OAUTH_TOKEN)
    assert second["id"] == first["id"] and second["method"] == "token"
    assert len((await client.get("/api/connections")).json()["connections"]) == 1


async def test_a_connection_can_be_tested_and_removed(client, github):
    await register(client)
    conn = await connect_github(client)
    tested = await client.post(f"/api/connections/{conn['id']}/test")
    assert tested.status_code == 200 and tested.json()["checked_at"]
    assert (await client.delete(f"/api/connections/{conn['id']}")).status_code == 204
    assert (await client.get("/api/connections")).json()["connections"] == []


async def test_a_credential_that_stopped_working_is_reported_when_tested(client, github, monkeypatch):
    await register(client)
    conn = await connect_github(client)
    monkeypatch.setattr(github, "handle", lambda request: httpx.Response(401))
    r = await client.post(f"/api/connections/{conn['id']}/test")
    assert r.status_code == 422 and "rejected" in r.json()["detail"]


async def test_a_credential_written_under_another_secret_key_asks_to_connect_again(
    client, github, monkeypatch
):
    await register(client)
    await connect_github(client)
    monkeypatch.setattr(settings, "secret_key", "a-different-secret-key-0123456789abcdef")
    await login(client, "a@b.co")  # sessions are signed with the same key
    (conn,) = (await client.get("/api/connections")).json()["connections"]
    assert conn["needs_reconnect"]
    r = await client.post(f"/api/connections/{conn['id']}/test")
    assert r.status_code == 422 and "Connect again" in r.json()["detail"]


async def test_connections_belong_to_their_owner_alone(client, github):
    await register(client)
    mine = await connect_github(client)
    await register(client, "b@b.co", "Bob")
    assert (await client.get("/api/connections")).json()["connections"] == []
    assert (await client.post(f"/api/connections/{mine['id']}/test")).status_code == 404
    assert (await client.delete(f"/api/connections/{mine['id']}")).status_code == 404


# ----- signing in with a code -----


async def test_signing_in_with_a_code_ends_in_a_connection(client, maker, github):
    await register(client)
    async with maker() as s:
        await save_settings(s, AppSettings(github_client_id="Iv1.abc123"))
    started = await client.post("/api/connection-logins/github")
    assert started.status_code == 201
    assert (started.json()["code"], started.json()["status"]) == ("ABCD-1234", "waiting")
    for _ in range(100):
        state = (await client.get("/api/connection-logins/github")).json()
        if state["status"] != "waiting":
            break
        await asyncio.sleep(0.02)
    assert state["status"] == "connected", state
    (conn,) = (await client.get("/api/connections")).json()["connections"]
    assert (conn["account"], conn["method"]) == ("octocat", "oauth")


async def test_a_declined_sign_in_says_so(client, maker, github):
    await register(client)
    async with maker() as s:
        await save_settings(s, AppSettings(github_client_id="Iv1.abc123"))
    github.decline = True
    await client.post("/api/connection-logins/github")
    for _ in range(100):
        state = (await client.get("/api/connection-logins/github")).json()
        if state["status"] != "waiting":
            break
        await asyncio.sleep(0.02)
    assert state["status"] == "failed" and "declined" in state["error"]
    assert (await client.get("/api/connections")).json()["connections"] == []


async def test_a_sign_in_without_an_app_id_is_refused_with_a_reason(client, github):
    await register(client)
    r = await client.post("/api/connection-logins/github")
    assert r.status_code == 409 and "client id" in r.json()["detail"]


# ----- a project's connection -----


async def test_a_project_picks_a_connection_and_its_repository_is_checked(client, github):
    await register(client)
    pid = (await make_project(client))["id"]
    conn = await connect_github(client)
    bound = await use_github(client, pid, conn["id"], "https://github.com/octocat/hello-world.git")
    assert (bound["account"], bound["config"]) == ("octocat", {"repo": "octocat/Hello-World"})
    assert (await client.get(f"/api/projects/{pid}/connections")).json() == [bound]
    missing = await client.put(
        f"/api/projects/{pid}/connections/github",
        json={"connection_id": conn["id"], "config": {"repo": "octocat/secret"}},
    )
    assert missing.status_code == 422 and "cannot find" in missing.json()["detail"]
    bad = await client.put(
        f"/api/projects/{pid}/connections/github",
        json={"connection_id": conn["id"], "config": {"repo": "not a repo"}},
    )
    assert bad.status_code == 422 and "owner/name" in bad.json()["detail"]
    assert (await client.get(f"/api/projects/{pid}/connections")).json() == [bound]  # unchanged


async def test_a_project_can_only_use_a_connection_of_its_owner(client, github):
    await register(client)
    mine = await connect_github(client)
    await register(client, "b@b.co", "Bob")
    pid = (await make_project(client))["id"]
    r = await client.put(f"/api/projects/{pid}/connections/github", json={"connection_id": mine["id"]})
    assert r.status_code == 404


async def test_removing_a_connection_removes_it_from_the_project(client, github):
    await register(client)
    pid = (await make_project(client))["id"]
    conn = await connect_github(client)
    await use_github(client, pid, conn["id"])
    await client.delete(f"/api/connections/{conn['id']}")
    assert (await client.get(f"/api/projects/{pid}/connections")).json() == []


async def test_a_project_can_stop_using_its_connection(client, github):
    await register(client)
    pid = (await make_project(client))["id"]
    await use_github(client, pid, (await connect_github(client))["id"])
    assert (await client.delete(f"/api/projects/{pid}/connections/github")).status_code == 204
    assert (await client.get(f"/api/projects/{pid}/connections")).json() == []


# ----- agents -----


async def test_an_agent_opts_in_by_provider_and_it_lands_in_its_file(client, github):
    await register(client)
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid, connections=["github"])
    assert agent["connections"] == ["github"]
    text = (settings.data_dir / "projects" / str(pid) / "config" / agent["path"]).read_text()
    assert "connections:" in text and "- github" in text
    unknown = await client.post(f"/api/projects/{pid}/agents", json={"name": "X", "connections": ["nope"]})
    assert unknown.status_code == 422
    cleared = await client.patch(f"/api/agents/{agent['id']}", json={"connections": []})
    assert cleared.json()["connections"] == []


# ----- running -----


async def run_with_github(client, scheduler, maker, *, bind=True, repo="octocat/hello-world"):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    if bind:
        await use_github(client, pid, (await connect_github(client))["id"], repo)
    agent = await make_agent(client, pid, connections=["github"])
    task = await make_task(client, pid, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    return task


async def test_an_agent_with_github_gets_the_token_as_a_hidden_variable_and_git_set_up(
    client, scheduler, cells, maker, github
):
    task = await run_with_github(client, scheduler, maker)
    spec = cells.specs[0]
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        assert spec.secret_files[f"/run/themis-secrets/keys/{name}"] == TOKEN
        assert f'export {name}="$(cat /run/themis-secrets/keys/{name})"' in spec.script
    assert TOKEN not in spec.script and TOKEN not in str(spec.env)  # both are visible on the host
    assert spec.env["GIT_CONFIG_VALUE_0"] == CREDENTIAL_HELPER
    assert spec.env["GH_REPO"] == "octocat/Hello-World"
    assert spec.env["GIT_AUTHOR_NAME"] == "The Octocat"
    assert spec.env["GIT_AUTHOR_EMAIL"] == "583231+octocat@users.noreply.github.com"
    assert (
        "signed in as @octocat" in spec.prompt
        and "git clone https://github.com/octocat/Hello-World.git" in spec.prompt
    )
    assert task["id"]


async def test_the_token_is_hidden_in_the_log(client, scheduler, cells, maker, github):
    cells.log_text = f"debug: Authorization: Bearer {TOKEN}\n"
    task = await run_with_github(client, scheduler, maker)
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    log = (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    assert TOKEN not in log and f"Bearer {HIDDEN}" in log


async def test_an_agent_without_the_opt_in_gets_nothing_even_when_the_project_has_github(
    client, scheduler, cells, maker, github
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    await use_github(client, pid, (await connect_github(client))["id"])
    agent = await make_agent(client, pid)
    await make_task(client, pid, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    spec = cells.specs[0]
    assert not any("keys/" in p for p in spec.secret_files) and "GH_TOKEN" not in spec.script
    assert "GIT_CONFIG_COUNT" not in spec.env


async def test_a_run_fails_with_the_reason_when_the_project_has_no_connection(
    client, scheduler, cells, maker, github
):
    task = await run_with_github(client, scheduler, maker, bind=False)
    assert cells.specs == []
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    log = (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    assert attempt["status"] == "failed" and "no GitHub connection" in log


async def test_a_run_fails_with_the_reason_when_the_credential_cannot_be_read(
    client, scheduler, cells, maker, github, monkeypatch
):
    me = await register(client)
    pid = (await make_project(client))["id"]
    await use_github(client, pid, (await connect_github(client))["id"])
    agent = await make_agent(client, pid, connections=["github"])
    task = await make_task(client, pid, status="ready", agent_id=agent["id"])
    monkeypatch.setattr(settings, "secret_key", "a-different-secret-key-0123456789abcdef")
    await connect(maker, me["id"])  # Codex is signed in again under the new key, GitHub is not
    await scheduler.tick()
    await drain(scheduler)
    await login(client, "a@b.co")  # sessions are signed with the same key
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    log = (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    assert attempt["status"] == "failed" and "can no longer be read" in log


async def test_a_key_that_takes_the_name_of_a_connection_variable_stops_the_run(
    client, scheduler, cells, maker, github
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    await use_github(client, pid, (await connect_github(client))["id"])
    key = (
        await client.post(
            "/api/secrets", json={"name": "GitHub token", "kind": "custom", "value": "other-key-123456"}
        )
    ).json()
    agent = await make_agent(client, pid, connections=["github"], secrets=[key["id"]])
    task = await make_task(client, pid, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    assert attempt["status"] == "failed" and cells.specs == []


# ----- the provider on its own -----


def test_github_leaves_the_author_out_when_it_does_not_know_who_the_token_is():
    env = GitHub().plain_env({}, {})
    assert "GIT_AUTHOR_NAME" not in env and "GH_REPO" not in env and env["GIT_TERMINAL_PROMPT"] == "0"


async def test_github_reads_a_repository_written_as_a_link(github):
    assert await GitHub().check_config(TOKEN, {"repo": "github.com/octocat/hello-world/"}) == {
        "repo": "octocat/Hello-World"
    }
    assert await GitHub().check_config(TOKEN, {"repo": "  "}) == {}


async def test_a_second_user_cannot_use_the_first_users_login(client, github):
    await register(client)
    await connect_github(client)
    await register(client, "b@b.co", "Bob")
    await login(client, "b@b.co")
    assert (await client.get("/api/connections")).json()["connections"] == []
