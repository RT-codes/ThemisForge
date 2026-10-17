"""The MCP control plane: who gets in with which token, and that a tool never reaches outside its project."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.control import ControlPlane
from app.crypto import encrypt
from app.main import app
from app.models import ControlToken
from tests.conftest import drain, login, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_harness import connect

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
async def control(maker, client):
    """The app's own control plane, on the test database (the lifespan that normally starts it does not run here).
    Its task group must be left by the task that entered it, so one task holds it open for the whole test."""
    plane = ControlPlane(maker)
    app.state.control = plane
    up, down = asyncio.Event(), asyncio.Event()

    async def hold() -> None:
        async with plane.running():
            up.set()
            await down.wait()

    holder = asyncio.create_task(hold())
    await up.wait()
    yield plane
    down.set()
    await holder


@pytest.fixture
async def agent_client(control):
    """What an outside agent is: a caller with no login cookie, only a token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def make_token(client, pid: int, name: str = "Claude Code", scope: str = "read") -> dict:
    r = await client.post(f"/api/projects/{pid}/control/tokens", json={"name": name, "scope": scope})
    assert r.status_code == 201, r.text
    return r.json()


async def secret_of(client, token: dict) -> str:
    return (await client.get(f"/api/control/tokens/{token['id']}/connect")).json()["token"]


async def rpc(agent, secret: str | None, method: str, params: dict | None = None):
    headers = dict(HEADERS, **({"Authorization": f"Bearer {secret}"} if secret is not None else {}))
    return await agent.post(
        "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    )


async def call(agent, secret: str, tool: str, **arguments):
    """A tool's answer: the data it returned, or {'error': message} when it failed."""
    r = await rpc(agent, secret, "tools/call", {"name": tool, "arguments": arguments})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    if result["isError"]:  # the SDK puts "Error executing tool NAME: " before what the tool said
        return {"error": result["content"][0]["text"].partition(": ")[2]}
    data = result["structuredContent"]
    return data["result"] if set(data) == {"result"} else data  # a list comes wrapped, an object as it is


# ----- getting in -----


async def test_a_request_without_a_known_token_is_refused(client, agent_client):
    await register(client)
    pid = (await make_project(client))["id"]
    token = await make_token(client, pid)

    for secret in (None, "", "nonsense", token["token_hint"]):
        r = await rpc(agent_client, secret, "tools/list")
        assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Bearer")


async def test_a_token_gets_an_agent_in_until_it_is_deleted(client, agent_client):
    await register(client)
    pid = (await make_project(client))["id"]
    token = await make_token(client, pid)
    secret = await secret_of(client, token)

    names = {t["name"] for t in (await rpc(agent_client, secret, "tools/list")).json()["result"]["tools"]}
    assert {"get_project", "list_tasks", "get_task", "get_attempt", "get_usage"} <= names
    assert not {n for n in names if n.startswith(("create", "update", "delete", "run"))}  # v1 only looks

    assert (await client.delete(f"/api/control/tokens/{token['id']}")).status_code == 204
    assert (await rpc(agent_client, secret, "tools/list")).status_code == 401


async def test_using_a_token_is_noted(client, agent_client):
    await register(client)
    pid = (await make_project(client))["id"]
    token = await make_token(client, pid)
    assert token["last_used_at"] is None

    await rpc(agent_client, await secret_of(client, token), "tools/list")

    (listed,) = (await client.get(f"/api/projects/{pid}/control/tokens")).json()
    assert listed["last_used_at"] is not None


# ----- the owner handing out tokens -----


async def test_the_owner_can_get_the_connect_command_again_and_the_list_never_holds_the_secret(client):
    await register(client)
    pid = (await make_project(client, "Shop front"))["id"]
    token = await make_token(client, pid)
    assert "token" not in token and len(token["token_hint"]) == 6

    connect_info = (await client.get(f"/api/control/tokens/{token['id']}/connect")).json()
    again = (await client.get(f"/api/control/tokens/{token['id']}/connect")).json()
    assert connect_info == again  # whenever it is needed, not shown once
    assert connect_info["url"] == "http://test/mcp"
    assert connect_info["token"].endswith(token["token_hint"])
    assert connect_info["claude_code"].startswith(
        "claude mcp add --transport http themis-shop-front http://test/mcp"
    )
    assert f"Bearer {connect_info['token']}" in connect_info["config_json"]
    assert connect_info["token"] not in str((await client.get(f"/api/projects/{pid}/control/tokens")).json())


async def test_only_the_owner_sees_or_changes_a_projects_tokens(client):
    await register(client)
    pid = (await make_project(client))["id"]
    token = await make_token(client, pid)
    await register(client, "other@b.co", "Bo")

    assert (await client.get(f"/api/projects/{pid}/control/tokens")).status_code == 404
    assert (await client.post(f"/api/projects/{pid}/control/tokens", json={"name": "x"})).status_code == 404
    assert (await client.get(f"/api/control/tokens/{token['id']}/connect")).status_code == 404
    assert (await client.delete(f"/api/control/tokens/{token['id']}")).status_code == 404


async def test_a_token_that_can_no_longer_be_decrypted_says_so_instead_of_failing(client, maker, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    token = await make_token(client, pid)
    with monkeypatch.context() as other_key:  # what THEMIS_SECRET_KEY being changed leaves behind
        other_key.setattr(settings, "secret_key", "a-different-key-than-before-0123456789")
        old = encrypt("secret")
    async with maker() as s:
        (await s.get(ControlToken, token["id"])).token_encrypted = old
        await s.commit()

    r = await client.get(f"/api/control/tokens/{token['id']}/connect")
    assert r.status_code == 409 and "THEMIS_SECRET_KEY" in r.json()["detail"]


# ----- what the tools show -----


async def test_the_tools_describe_the_tokens_project(client, agent_client):
    await register(client)
    pid = (await make_project(client, "Alpha"))["id"]
    await make_task(client, pid, title="First", status="ready")
    await make_task(client, pid, title="Second", status="backlog")
    secret = await secret_of(client, await make_token(client, pid))

    assert (await call(agent_client, secret, "get_project"))["name"] == "Alpha"
    boards = await call(agent_client, secret, "list_boards")
    assert boards and boards[0]["boards"]
    assert {t["title"] for t in await call(agent_client, secret, "list_tasks")} == {"First", "Second"}
    assert [t["title"] for t in await call(agent_client, secret, "list_tasks", status="backlog")] == [
        "Second"
    ]
    assert len(await call(agent_client, secret, "list_tasks", limit=1)) == 1


async def test_a_token_never_reaches_another_project_even_one_of_the_same_owner(
    client, agent_client, scheduler, cells
):
    await register(client)
    mine = (await make_project(client, "Mine"))["id"]
    theirs = (await make_project(client, "Theirs"))["id"]
    other = await make_task(client, theirs, title="Not for you", status="ready")
    await scheduler.tick()
    await drain(scheduler)
    attempt = (await client.get(f"/api/tasks/{other['id']}/attempts")).json()[0]
    secret = await secret_of(client, await make_token(client, mine))

    assert (await call(agent_client, secret, "get_project"))["name"] == "Mine"
    assert await call(agent_client, secret, "list_tasks") == []
    missing = await call(agent_client, secret, "get_task", task_id=99999)
    assert "error" in missing
    for tool, arguments in (
        ("get_task", {"task_id": other["id"]}),
        ("list_attempts", {"task_id": other["id"]}),
        ("get_attempt", {"attempt_id": attempt["id"]}),
    ):
        # the same answer as for an id that does not exist at all, so ids tell nothing about other projects
        assert await call(agent_client, secret, tool, **arguments) == missing
    assert await call(agent_client, secret, "get_task", task_id=99999) == missing


async def test_an_attempt_is_read_with_the_end_of_its_log_and_what_it_used(
    client, agent_client, scheduler, cells, maker
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid, model="gpt-5-mini")
    task = await make_task(client, pid, title="Count words", status="ready", agent_id=agent["id"])
    cells.usage["Count words"] = {"input_tokens": 500, "output_tokens": 40}
    await scheduler.tick()
    await drain(scheduler)
    secret = await secret_of(client, await make_token(client, pid))

    (listed,) = await call(agent_client, secret, "list_attempts", task_id=task["id"])
    assert (
        listed["status"] == "succeeded" and listed["model"] == "gpt-5-mini" and listed["input_tokens"] == 500
    )
    short = await call(agent_client, secret, "get_attempt", attempt_id=listed["id"], log_chars=12)
    full = await call(agent_client, secret, "get_attempt", attempt_id=listed["id"], log_chars=50_000)
    assert len(short["log"]) == 12 and full["log"].endswith(short["log"]) and len(full["log"]) > 12
    assert (await call(agent_client, secret, "get_attempt", attempt_id=listed["id"], log_chars=0))[
        "log"
    ] == ""
    assert short["result"] == full["result"] != ""


async def test_usage_is_added_up_per_model_for_the_tokens_project_only(
    client, agent_client, scheduler, cells, maker
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client, "Mine"))["id"]
    other = (await make_project(client, "Other"))["id"]
    for project, title, spent in ((pid, "One", 100), (pid, "Two", 250), (other, "Elsewhere", 9999)):
        made = await make_agent(client, project, name=f"Agent {title}", model="gpt-5-mini")
        await make_task(client, project, title=title, status="ready", agent_id=made["id"])
        cells.usage[title] = {"input_tokens": spent, "output_tokens": 1}
    await scheduler.tick()
    await drain(scheduler)
    secret = await secret_of(client, await make_token(client, pid))

    (row,) = await call(agent_client, secret, "get_usage", days=7)
    assert (row["harness"], row["model"], row["billing"], row["attempts"]) == (
        "codex",
        "gpt-5-mini",
        "subscription",
        2,
    )
    assert (row["input_tokens"], row["output_tokens"]) == (350, 2)
    # the owner sees the same numbers in the web interface's API
    assert (await client.get(f"/api/projects/{pid}/usage")).json() == [row]


async def test_a_token_whose_owner_is_logged_out_still_works(client, agent_client):
    """The token is its own credential: the agent does not need the owner to be signed in anywhere."""
    me = await register(client)
    pid = (await make_project(client))["id"]
    secret = await secret_of(client, await make_token(client, pid))
    client.cookies.clear()

    assert (await call(agent_client, secret, "get_project"))["id"] == pid
    await login(client, me["email"])
