"""The MCP control plane: who gets in with which token, and that a tool never reaches outside its project."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.control import ControlPlane
from app.control_tools import NOT_FOUND
from app.crypto import encrypt
from app.main import app
from app.models import ControlToken
from tests.conftest import drain, login, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_approvals import gated, open_approvals, start
from tests.test_harness import connect
from tests.test_workflows import make_workflow as make_workflow_for

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

# the tools that change things. A "write" token may use the first set, only a "manage" token the second as well
WRITE_ACTIONS = {
    "create_task", "update_task", "move_task", "run_task", "cancel_task", "start_workflow_run",
    "cancel_workflow_run", "decide_approval", "halt_project", "resume_project", "halt_board", "resume_board",
}  # fmt: skip
MANAGE_ACTIONS = {
    "create_agent", "update_agent", "save_skill", "create_workflow", "update_workflow", "write_file",
    "make_folder", "move_file",
}  # fmt: skip
ACTIONS = WRITE_ACTIONS | MANAGE_ACTIONS
SKILL = "---\nname: {name}\ndescription: Checks copy before it goes out\n---\nRead the copy twice.\n"


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


async def rpc(http, secret: str | None, method: str, params: dict | None = None):
    headers = dict(HEADERS, **({"Authorization": f"Bearer {secret}"} if secret is not None else {}))
    return await http.post(
        "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    )


async def call(http, secret: str, tool: str, **arguments):
    """A tool's answer: the data it returned, or {'error': message} when it failed."""
    r = await rpc(http, secret, "tools/call", {"name": tool, "arguments": arguments})
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

    listed = (await rpc(agent_client, secret, "tools/list")).json()["result"]["tools"]
    names = {t["name"] for t in listed}
    assert {"get_project", "list_tasks", "get_task", "get_attempt", "get_usage"} <= names
    # every tool says whether it changes anything, so a client can wave the reading ones through
    changing = {t["name"] for t in listed if not t["annotations"]["readOnlyHint"]}
    assert changing == ACTIONS
    assert not {n for n in names - ACTIONS if n.startswith(("create", "update", "delete", "run", "cancel"))}

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


# ----- a connection for all of a user's projects -----


async def make_account_token(client, name: str = "Claude Code", scope: str = "read") -> dict:
    r = await client.post("/api/control/tokens", json={"name": name, "scope": scope})
    assert r.status_code == 201, r.text
    return r.json()


async def two_users_with_projects(client):
    """Ada (the administrator) with two projects and an all-projects key, then Bo with one project."""
    await register(client)
    mine, other = (await make_project(client, "Mine"))["id"], (await make_project(client, "Other"))["id"]
    secret = await secret_of(client, await make_account_token(client))
    await register(client, "bo@b.co", "Bo")
    bos = (await make_project(client, "Bo's"))["id"]
    await login(client, "a@b.co")
    return secret, mine, other, bos


async def test_an_account_connection_sees_all_of_its_users_projects_and_no_ones_elses(client, agent_client):
    secret, _, other, bos = await two_users_with_projects(client)

    assert {p["name"] for p in await call(agent_client, secret, "list_projects")} == {"Mine", "Other"}
    # it must say which project it means, and then reaches any of its user's
    assert "project_id" in (await call(agent_client, secret, "get_project"))["error"]
    assert (await call(agent_client, secret, "get_project", project_id=other))["name"] == "Other"
    missing = await call(agent_client, secret, "get_project", project_id=99999)
    assert "error" in missing
    # another user's project answers like one that is not there
    assert await call(agent_client, secret, "get_project", project_id=bos) == missing
    assert await call(agent_client, secret, "list_tasks", project_id=bos) == missing


async def test_a_connection_for_one_project_lists_only_it_and_never_reaches_a_sibling(client, agent_client):
    await register(client)
    mine = (await make_project(client, "Mine"))["id"]
    other = (await make_project(client, "Other"))["id"]
    secret = await secret_of(client, await make_token(client, mine))

    assert [p["name"] for p in await call(agent_client, secret, "list_projects")] == ["Mine"]
    assert (await call(agent_client, secret, "get_project"))["name"] == "Mine"  # no id needed
    missing = await call(agent_client, secret, "get_project", project_id=99999)
    for tool in ("get_project", "list_tasks", "list_agents", "list_boards", "get_project_overview"):
        assert await call(agent_client, secret, tool, project_id=other) == missing


async def test_account_keys_are_made_listed_and_removed_by_their_owner(client, agent_client):
    await register(client)
    pid = (await make_project(client))["id"]
    await make_token(client, pid)  # a key for one project is not an account key
    key = await make_account_token(client, "Laptop")
    assert key["project_id"] is None and [
        k["name"] for k in (await client.get("/api/control/tokens")).json()
    ] == ["Laptop"]
    info = (await client.get(f"/api/control/tokens/{key['id']}/connect")).json()
    assert info["claude_code"].startswith("claude mcp add --transport http themis http://test/mcp ")

    await register(client, "bo@b.co", "Bo")
    assert (await client.get("/api/control/tokens")).json() == []  # not Bo's
    assert (await client.get(f"/api/control/tokens/{key['id']}/connect")).status_code == 404
    assert (await client.delete(f"/api/control/tokens/{key['id']}")).status_code == 404
    await login(client, "a@b.co")
    assert (await client.delete(f"/api/control/tokens/{key['id']}")).status_code == 204
    assert (await rpc(agent_client, info["token"], "tools/list")).status_code == 401


# ----- knowing what is going on -----


async def test_the_overview_says_what_needs_a_person_and_what_happened(
    client, agent_client, scheduler, cells
):
    await register(client)
    pid = (await make_project(client, "Shop"))["id"]
    await make_task(client, pid, title="Ships tonight", status="backlog")
    await make_task(client, pid, title="Check the copy", status="review")
    await make_task(client, pid, title="This will fail", status="ready")
    await make_agent(client, pid, name="Writer")
    await client.post(f"/api/projects/{pid}/workflows", json={"name": "Daily"})
    await scheduler.tick()
    await drain(scheduler)
    secret = await secret_of(client, await make_token(client, pid))

    overview = await call(agent_client, secret, "get_project_overview")

    assert overview["project"]["name"] == "Shop" and overview["halted"] is False
    assert overview["project"]["task_counts"] == {"backlog": 1, "review": 1, "failed": 1}
    waiting = {t["title"]: t for t in overview["needs_attention"]}
    assert set(waiting) == {"Check the copy", "This will fail"}
    assert waiting["This will fail"]["status"] == "failed" and waiting["This will fail"]["reason"]
    assert overview["running"] == [] and overview["approvals"] == []
    assert [b["name"] for b in overview["boards"]] and overview["boards"][0]["task_counts"]["backlog"] == 1
    assert (overview["agents"], overview["workflows"]) == (1, 1)
    assert overview["recent_events"], "what happened lately is part of it"


async def test_a_board_comes_with_its_tasks_and_columns(client, agent_client):
    await register(client)
    mine = (await make_project(client, "Mine"))["id"]
    other = (await make_project(client, "Other"))["id"]
    await make_task(client, mine, title="On the board", status="ready")
    secret = await secret_of(client, await make_token(client, mine))
    board = (await call(agent_client, secret, "list_boards"))[0]["boards"][0]
    foreign = (await client.get(f"/api/projects/{other}/workspaces")).json()[0]["boards"][0]

    view = await call(agent_client, secret, "get_board", board_id=board["id"])
    assert [t["title"] for t in view["tasks"]] == ["On the board"]
    assert view["board"]["id"] == board["id"] and view["board"]["columns"] and view["workspace"]
    missing = await call(agent_client, secret, "get_board", board_id=99999)
    assert (
        "error" in missing
        and await call(agent_client, secret, "get_board", board_id=foreign["id"]) == missing
    )


async def test_how_a_project_is_set_up_can_be_read_without_its_secrets(client, agent_client):
    await register(client)
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid, name="Writer", instructions="Be brief.")
    wid = (await client.post(f"/api/projects/{pid}/workflows", json={"name": "Daily"})).json()["id"]
    hook = (await client.post(f"/api/projects/{pid}/webhooks", json={"name": "Orders"})).json()
    secret = await secret_of(client, await make_token(client, pid))
    other = (await make_project(client, "Other"))["id"]
    foreign = await make_agent(client, other, name="Foreign")

    assert [a["name"] for a in await call(agent_client, secret, "list_agents")] == ["Writer"]
    assert (await call(agent_client, secret, "get_agent", agent_id=agent["id"]))[
        "instructions"
    ] == "Be brief."
    assert "error" in await call(agent_client, secret, "get_agent", agent_id=foreign["id"])
    assert [w["name"] for w in await call(agent_client, secret, "list_workflows")] == ["Daily"]
    assert "nodes" in (await call(agent_client, secret, "get_workflow", workflow_id=wid))["graph"]
    assert await call(agent_client, secret, "list_workflow_runs", workflow_id=wid) == []
    assert "error" in await call(agent_client, secret, "get_workflow_run", run_id=99999)

    hooks = await call(agent_client, secret, "list_webhooks")
    assert [h["name"] for h in hooks] == ["Orders"]
    assert hook["path"].removeprefix("/api/hooks/") not in str(hooks)  # the address is a secret
    assert await call(agent_client, secret, "list_webhook_deliveries", webhook_id=hook["id"]) == []
    for empty in (
        "list_skills",
        "list_tool_servers",
        "list_notifications",
        "list_project_connections",
        "list_approvals",
    ):
        assert await call(agent_client, secret, empty) == [], empty


async def test_folders_can_be_listed_and_files_read_only_inside_their_folder(client, agent_client):
    await register(client)
    mine = (await make_project(client, "Mine"))["id"]
    other = (await make_project(client, "Other"))["id"]
    secret = await secret_of(client, await make_token(client, mine))
    foreign_secret = await secret_of(client, await make_token(client, other))
    shared = settings.data_dir / "projects" / str(mine) / "volumes" / "shared"
    (shared / "notes").mkdir(parents=True)
    (shared / "notes" / "plan.md").write_text("# Plan\n" + "x" * 100, encoding="utf-8")
    (shared / "logo.bin").write_bytes(b"\x00\x01\x02")

    folders = await call(agent_client, secret, "list_folders")
    assert {f["kind"] for f in folders} >= {"managed", "config"}  # the shared folders and the config folder
    fid = next(f["id"] for f in folders if f["is_default"])

    top = await call(agent_client, secret, "list_files", folder_id=fid)
    assert {e["name"] for e in top["entries"]} == {"notes", "logo.bin"}
    inside = await call(agent_client, secret, "list_files", folder_id=fid, path="notes")
    assert [e["name"] for e in inside["entries"]] == ["plan.md"]
    read = await call(agent_client, secret, "read_file", folder_id=fid, path="notes/plan.md")
    assert read["text"].startswith("# Plan") and read["truncated"] is False
    cut = await call(agent_client, secret, "read_file", folder_id=fid, path="notes/plan.md", max_chars=10)
    assert len(cut["text"]) == 10 and cut["truncated"] is True

    assert (
        "binary" in (await call(agent_client, secret, "read_file", folder_id=fid, path="logo.bin"))["error"]
    )
    assert "error" in await call(agent_client, secret, "read_file", folder_id=fid, path="../../../etc/passwd")
    missing = await call(agent_client, secret, "read_file", folder_id=fid, path="nothing.md")
    assert "error" in missing
    # another project's key cannot look into this folder, and is told what a missing folder is told
    assert await call(agent_client, foreign_secret, "list_files", folder_id=fid) == await call(
        agent_client, foreign_secret, "list_files", folder_id=99999
    )


# ----- the installation itself -----


async def test_global_settings_need_an_all_projects_connection_of_an_administrator(client, agent_client):
    secret, mine, *_ = await two_users_with_projects(client)
    one_project = await secret_of(client, await make_token(client, mine))

    settings_out = await call(agent_client, secret, "get_settings")
    assert settings_out["timezone"] and "cell_image" in settings_out
    assert any(h["id"] == "codex" for h in await call(agent_client, secret, "list_harnesses"))
    assert isinstance(await call(agent_client, secret, "list_keys"), list)
    status = await call(agent_client, secret, "get_system_status")
    assert status["version"] and "scheduler" in status and "cells_ready" in status

    for tool in ("get_settings", "get_system_status", "list_harnesses", "list_keys"):
        assert "all projects" in (await call(agent_client, one_project, tool))["error"]

    await login(client, "bo@b.co")  # Bo is no administrator
    bos_secret = await secret_of(client, await make_account_token(client, "Bo's"))
    assert "administrator" in (await call(agent_client, bos_secret, "get_settings"))["error"]
    assert {p["name"] for p in await call(agent_client, bos_secret, "list_projects")} == {"Bo's"}


def test_a_handler_that_needs_an_administrator_is_checked_by_hand_in_its_tool():
    """The tools call route handlers as plain functions, so a route's `AdminUser` dependency does not run for them. Every
    handler a tool calls that has one must be named here, and its tool must make the check itself."""
    import inspect
    import re

    from app import control_tools
    from app.deps import require_admin
    from app.routers import (
        agents,
        connections,
        notifications,
        projects,
        skills,
        system,
        tools,
        volumes,
        webhooks,
        workflows,
        workspaces,
    )

    modules = {
        "agents": agents, "connections": connections, "notifications": notifications, "projects": projects,
        "skills": skills, "system": system, "tools": tools, "volumes": volumes, "webhooks": webhooks,
        "workflows": workflows, "workspaces_router": workspaces,
    }  # fmt: skip
    source = inspect.getsource(control_tools)
    needing_admin = set()
    for module_name, function_name in set(re.findall(r"\b(\w+)\.(\w+)\(", source)):
        handler = getattr(modules.get(module_name), function_name, None)
        if not inspect.iscoroutinefunction(handler):
            continue
        for parameter in inspect.signature(handler).parameters.values():
            depends = [
                m for m in getattr(parameter.annotation, "__metadata__", ()) if hasattr(m, "dependency")
            ]
            if any(d.dependency is require_admin for d in depends):
                needing_admin.add(f"{module_name}.{function_name}")
    assert needing_admin == {"system.get_settings"}
    assert "require_admin(owner)" in source


# ----- actions: they need a token that may change things -----


async def test_a_token_that_only_reads_cannot_use_any_action_and_nothing_changes(client, agent_client):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="Keep me", status="backlog")
    board = (await call(agent_client, await secret_of(client, await make_token(client, pid)), "list_boards"))[
        0
    ]
    secret = await secret_of(client, await make_token(client, pid))  # scope: read

    arguments = {
        "create_task": {"task": {"title": "New"}},
        "update_task": {"task_id": task["id"], "changes": {"title": "Changed"}},
        "move_task": {"task_id": task["id"], "board_id": board["boards"][0]["id"]},
        "run_task": {"task_id": task["id"]},
        "cancel_task": {"task_id": task["id"]},
        "start_workflow_run": {"workflow_id": 1},
        "cancel_workflow_run": {"run_id": 1},
        "decide_approval": {"approval_id": 1, "approved": True},
        "halt_project": {},
        "resume_project": {},
        "halt_board": {"board_id": board["boards"][0]["id"]},
        "resume_board": {"board_id": board["boards"][0]["id"]},
    }
    folder = (await call(agent_client, secret, "list_folders"))[0]["id"]
    arguments |= {
        "create_agent": {"agent": {"name": "Sneak"}},
        "update_agent": {"agent_id": 1, "changes": {"role": "x"}},
        "save_skill": {"name": "sneak", "content": SKILL.format(name="sneak")},
        "create_workflow": {"workflow": {"name": "Sneak"}},
        "update_workflow": {"workflow_id": 1, "changes": {"name": "x"}},
        "write_file": {"folder_id": folder, "path": "sneak.txt", "text": "x"},
        "make_folder": {"folder_id": folder, "path": "sneak"},
        "move_file": {"folder_id": folder, "source": "a", "destination": "b"},
    }
    assert set(arguments) == ACTIONS, "every action is tried here"
    for name, args in arguments.items():
        wanted = "can only read" if name in WRITE_ACTIONS else "cannot set things up"
        assert wanted in (await call(agent_client, secret, name, **args))["error"], name

    assert [t["title"] for t in await call(agent_client, secret, "list_tasks")] == ["Keep me"]
    assert (await call(agent_client, secret, "get_project_overview"))["halted"] is False


async def test_an_agent_with_permission_makes_runs_changes_and_moves_tasks(
    client, agent_client, scheduler, cells
):
    await register(client)
    pid = (await make_project(client))["id"]
    secret = await secret_of(client, await make_token(client, pid, scope="write"))

    made = await call(
        agent_client, secret, "create_task", task={"title": "Write notes", "description": "Short"}
    )
    assert made["title"] == "Write notes" and made["status"] == "backlog" and made["project_id"] == pid
    assert [t["id"] for t in (await client.get(f"/api/projects/{pid}/tasks")).json()] == [
        made["id"]
    ]  # for real

    changed = await call(
        agent_client, secret, "update_task", task_id=made["id"], changes={"title": "Write more"}
    )
    assert changed["title"] == "Write more" and changed["description"] == "Short"  # only what was given

    ran = await call(agent_client, secret, "run_task", task_id=made["id"])
    assert ran["status"] == "ready"
    await scheduler.tick()
    await drain(scheduler)
    assert (await call(agent_client, secret, "get_task", task_id=made["id"]))["status"] in ("done", "review")
    assert len(await call(agent_client, secret, "list_attempts", task_id=made["id"])) == 1

    board = (await call(agent_client, secret, "list_boards"))[0]["boards"][0]
    moved = await call(
        agent_client, secret, "move_task", task_id=made["id"], board_id=board["id"], status="backlog"
    )
    assert moved["status"] == "backlog"
    assert "not running" in (await call(agent_client, secret, "cancel_task", task_id=made["id"]))["error"]
    # the history says an agent did it, so it is not taken for the person's own doing
    history = await call(agent_client, secret, "get_history")
    assert any(e["kind"] == "task_created" and e["actor"] == "Ada via Claude Code" for e in history)
    web = (await client.get(f"/api/projects/{pid}/history")).json()
    assert {e["actor"] for e in web if e["task_id"] == made["id"]} == {"Ada via Claude Code"}


async def test_halting_holds_work_back_until_it_is_resumed_for_a_project_and_for_a_board(
    client, agent_client, scheduler, cells
):
    await register(client)
    pid = (await make_project(client))["id"]
    secret = await secret_of(client, await make_token(client, pid, scope="write"))
    task = await make_task(client, pid, title="Waits", status="backlog")
    board_id = (await call(agent_client, secret, "list_boards"))[0]["boards"][0]["id"]

    assert (await call(agent_client, secret, "halt_project"))["halted_at"] is not None
    assert "halted" in (await call(agent_client, secret, "run_task", task_id=task["id"]))["error"]
    assert (await call(agent_client, secret, "resume_project"))["halted_at"] is None

    halted = await call(agent_client, secret, "halt_board", board_id=board_id, stop_running=False)
    assert halted["halted_at"] is not None
    assert "halted" in (await call(agent_client, secret, "run_task", task_id=task["id"]))["error"]
    assert (await call(agent_client, secret, "resume_board", board_id=board_id))["halted_at"] is None
    assert (await call(agent_client, secret, "run_task", task_id=task["id"]))["status"] == "ready"


async def test_workflow_runs_are_started_and_cancelled_and_approvals_answered(client, agent_client, runner):
    await register(client)
    pid = (await make_project(client))["id"]
    secret = await secret_of(client, await make_token(client, pid, scope="write"))
    run_id = await start(client, pid, *gated())  # parks at its approval gate
    [approval] = await open_approvals(client)
    assert approval["run_id"] == run_id

    cancelled = await call(agent_client, secret, "cancel_workflow_run", run_id=run_id)
    assert cancelled["status"] == "cancelled"
    assert (
        "no longer going"
        in (await call(agent_client, secret, "decide_approval", approval_id=approval["id"], approved=True))[
            "error"
        ]
    )

    run_id = await start(client, pid, *gated("Ship it?"))
    [approval] = [a for a in await open_approvals(client) if a["run_id"] == run_id]
    answered = await call(
        agent_client,
        secret,
        "decide_approval",
        approval_id=approval["id"],
        approved=True,
        note="from an agent",
    )
    assert answered["id"] == run_id
    assert (await call(agent_client, secret, "decide_approval", approval_id=approval["id"], approved=False))[
        "error"
    ]  # the first answer stands

    flow = (await call(agent_client, secret, "list_workflows"))[0]["id"]
    started = await call(agent_client, secret, "start_workflow_run", workflow_id=flow)
    assert started["workflow_id"] == flow


async def test_an_action_never_reaches_outside_its_project_and_a_connection_for_all_must_name_one(
    client, agent_client, scheduler, cells, runner
):
    await register(client)
    mine = (await make_project(client, "Mine"))["id"]
    theirs = (await make_project(client, "Theirs"))["id"]
    other = await make_task(client, theirs, title="Not for you", status="backlog")
    other_board = (await client.get(f"/api/projects/{theirs}/workspaces")).json()[0]["boards"][0]["id"]
    other_run = await start(client, theirs, *gated())
    [other_approval] = await open_approvals(client)
    secret = await secret_of(client, await make_token(client, mine, scope="write"))

    missing = await call(agent_client, secret, "run_task", task_id=99999)
    assert "error" in missing
    for name, args in (
        ("update_task", {"task_id": other["id"], "changes": {"title": "Mine now"}}),
        ("move_task", {"task_id": other["id"], "board_id": other_board}),
        ("run_task", {"task_id": other["id"]}),
        ("cancel_task", {"task_id": other["id"]}),
        ("cancel_workflow_run", {"run_id": other_run}),
        ("decide_approval", {"approval_id": other_approval["id"], "approved": True}),
        ("halt_board", {"board_id": other_board}),
        ("resume_board", {"board_id": other_board}),
        ("halt_project", {"project_id": theirs}),
        ("create_task", {"project_id": theirs, "task": {"title": "Planted"}}),
    ):
        # the same answer as for an id that does not exist at all, so ids tell nothing about other projects
        assert await call(agent_client, secret, name, **args) == missing, name
    assert (await client.get(f"/api/tasks/{other['id']}")).json()["title"] == "Not for you"
    assert (await client.get(f"/api/projects/{theirs}")).json()["halted_at"] is None
    assert [t["title"] for t in (await client.get(f"/api/projects/{theirs}/tasks")).json()] == ["Not for you"]

    everywhere = await secret_of(client, await make_account_token(client, scope="write"))
    assert (
        "project_id"
        in (await call(agent_client, everywhere, "create_task", task={"title": "Where?"}))["error"]
    )
    made = await call(agent_client, everywhere, "create_task", project_id=theirs, task={"title": "Here"})
    assert made["project_id"] == theirs


# ----- setting a project up: agents, skills, workflows and files need a token that may manage -----


async def test_a_token_that_may_run_work_still_cannot_set_the_project_up(client, agent_client):
    await register(client)
    pid = (await make_project(client))["id"]
    secret = await secret_of(client, await make_token(client, pid, scope="write"))

    refused = await call(agent_client, secret, "create_agent", agent={"name": "Sneak"})
    assert "cannot set things up" in refused["error"]
    assert await call(agent_client, secret, "list_agents") == []
    assert (await call(agent_client, secret, "create_task", task={"title": "Fine"}))[
        "title"
    ] == "Fine"  # write works


async def test_an_agent_that_may_manage_sets_up_skills_agents_and_workflows(client, agent_client, runner):
    await register(client)
    pid = (await make_project(client))["id"]
    secret = await secret_of(client, await make_token(client, pid, scope="manage"))

    skill = await call(
        agent_client, secret, "save_skill", name="copy-check", content=SKILL.format(name="copy-check")
    )
    assert skill["description"] == "Checks copy before it goes out"
    assert (
        "description"
        in (await call(agent_client, secret, "save_skill", name="bad", content="no front matter"))["error"]
    )

    agent = await call(
        agent_client,
        secret,
        "create_agent",
        agent={"name": "Editor", "instructions": "Be brief.", "skills": ["copy-check"]},
    )
    assert agent["name"] == "Editor" and agent["skills"] == ["copy-check"] and agent["project_id"] == pid
    assert "already" in (await call(agent_client, secret, "create_agent", agent={"name": "Editor"}))["error"]
    assert (
        "does not exist"
        in (await call(agent_client, secret, "create_agent", agent={"name": "X", "skills": ["nope"]}))[
            "error"
        ]
    )

    changed = await call(
        agent_client, secret, "update_agent", agent_id=agent["id"], changes={"role": "Copy editor"}
    )
    assert changed["role"] == "Copy editor" and changed["instructions"] == "Be brief."  # only what was given
    assert (await client.get(f"/api/agents/{agent['id']}")).json()["role"] == "Copy editor"  # for real

    flow = await call(agent_client, secret, "create_workflow", workflow={"name": "Daily"})
    assert [n["kind"] for n in flow["graph"]["nodes"]] == ["start"]  # a new workflow can be tried at once
    graph = flow["graph"] | {"nodes": flow["graph"]["nodes"] + [
        {"id": "n2", "kind": "end", "label": "End", "config": {}, "position": {"x": 200, "y": 0}}
    ], "edges": [{"id": "e1", "source": "n1", "target": "n2"}]}  # fmt: skip
    saved = await call(
        agent_client, secret, "update_workflow", workflow_id=flow["id"], changes={"graph": graph}
    )
    assert [n["id"] for n in saved["graph"]["nodes"]] == ["n1", "n2"] and saved["name"] == "Daily"
    assert (await call(agent_client, secret, "start_workflow_run", workflow_id=flow["id"]))[
        "workflow_id"
    ] == flow["id"]


async def test_files_are_written_made_and_moved_with_the_rules_of_the_files_page(client, agent_client):
    await register(client)
    pid = (await make_project(client))["id"]
    secret = await secret_of(client, await make_token(client, pid, scope="manage"))
    folders = {f["kind"]: f["id"] for f in await call(agent_client, secret, "list_folders")}
    shared = folders["managed"]

    await call(agent_client, secret, "make_folder", folder_id=shared, path="notes")
    await call(agent_client, secret, "write_file", folder_id=shared, path="notes/a.md", text="first")
    read = await call(agent_client, secret, "read_file", folder_id=shared, path="notes/a.md")
    assert read["text"] == "first"
    assert (
        "already exists"
        in (await call(agent_client, secret, "write_file", folder_id=shared, path="notes/a.md", text="x"))[
            "error"
        ]
    )
    await call(
        agent_client, secret, "write_file", folder_id=shared, path="notes/a.md", text="second", overwrite=True
    )
    await call(
        agent_client, secret, "move_file", folder_id=shared, source="notes/a.md", destination="notes/b.md"
    )
    assert (await call(agent_client, secret, "read_file", folder_id=shared, path="notes/b.md"))[
        "text"
    ] == "second"
    assert (await call(agent_client, secret, "read_file", folder_id=shared, path="notes/a.md"))[
        "error"
    ] == NOT_FOUND

    # a path cannot climb out of its folder, and nothing is written where there is no folder
    assert "error" in await call(
        agent_client, secret, "write_file", folder_id=shared, path="../out.txt", text="x"
    )
    assert "error" in await call(
        agent_client, secret, "write_file", folder_id=shared, path="missing/a.md", text="x"
    )

    # the config folder holds agents as files: a file that could not work is refused, as in the Files page
    agent = await call(agent_client, secret, "create_agent", agent={"name": "Filed"})
    broken = await call(
        agent_client,
        secret,
        "write_file",
        folder_id=folders["config"],
        path=agent["path"],
        text="---\n",
        overwrite=True,
    )
    assert "error" in broken
    assert (await client.get(f"/api/agents/{agent['id']}")).json()[
        "config_error"
    ] == ""  # the agent is still fine


async def test_setting_up_never_reaches_another_project_and_is_answered_like_a_missing_id(
    client, agent_client
):
    await register(client)
    mine = (await make_project(client, "Mine"))["id"]
    theirs = (await make_project(client, "Theirs"))["id"]
    other_agent = await make_agent(client, theirs, name="Theirs")
    other_flow = await make_workflow_for(client, theirs)
    other_folder = (await client.get(f"/api/projects/{theirs}/volumes")).json()[0]["id"]
    secret = await secret_of(client, await make_token(client, mine, scope="manage"))

    missing = await call(agent_client, secret, "update_agent", agent_id=99999, changes={"role": "x"})
    assert "error" in missing
    for name, args in (
        ("update_agent", {"agent_id": other_agent["id"], "changes": {"role": "Mine now"}}),
        ("update_workflow", {"workflow_id": other_flow, "changes": {"name": "Mine now"}}),
        ("write_file", {"folder_id": other_folder, "path": "planted.txt", "text": "x"}),
        ("make_folder", {"folder_id": other_folder, "path": "planted"}),
        ("move_file", {"folder_id": other_folder, "source": "a", "destination": "b"}),
        ("create_agent", {"project_id": theirs, "agent": {"name": "Planted"}}),
        ("save_skill", {"project_id": theirs, "name": "planted", "content": SKILL.format(name="planted")}),
        ("create_workflow", {"project_id": theirs, "workflow": {"name": "Planted"}}),
    ):
        # the same answer as for an id that does not exist at all, so ids tell nothing about other projects
        assert await call(agent_client, secret, name, **args) == missing, name
    assert (await client.get(f"/api/agents/{other_agent['id']}")).json()["role"] == other_agent["role"]
    assert [a["name"] for a in (await client.get(f"/api/projects/{theirs}/agents")).json()] == ["Theirs"]
    assert (await client.get(f"/api/projects/{theirs}/skills")).json() == []
