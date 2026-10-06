import tomllib

import pytest

from app import toolcheck
from app.config import settings
from app.harness import codex_script
from app.keys import HIDDEN, Redactor, key_env_name, unique_env_names
from app.mcp import McpSpec, config_toml
from app.models import Agent
from app.routers import agents as agents_router
from tests.conftest import drain, login, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_harness import connect

SECRET = "sk-live-9f8e7d6c5b4a"


async def make_key(client, name="GitHub token", value=SECRET) -> dict:
    r = await client.post("/api/secrets", json={"name": name, "kind": "github", "value": value})
    assert r.status_code == 201, r.text
    return r.json()


async def make_server(client, pid: int, **body) -> dict:
    body.setdefault("name", "files")
    body.setdefault("command", "npx -y @modelcontextprotocol/server-filesystem /workspace")
    r = await client.post(f"/api/projects/{pid}/mcp-servers", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ----- naming and redacting keys -----


def test_a_keys_variable_is_its_name_in_capitals():
    assert key_env_name("GitHub token") == "GITHUB_TOKEN"
    assert key_env_name("  my-api.key!! ") == "MY_API_KEY"
    assert key_env_name("1password") == "KEY_1PASSWORD"
    assert key_env_name("???") == "KEY"


def test_a_key_never_takes_the_place_of_a_variable_the_cell_relies_on():
    assert key_env_name("path") == "THEMIS_KEY_PATH"
    assert key_env_name("codex home") == "THEMIS_KEY_CODEX_HOME"
    assert key_env_name("themis secret") == "THEMIS_KEY_THEMIS_SECRET"


def test_two_keys_with_the_same_variable_get_different_ones():
    assert unique_env_names([(1, "GitHub"), (2, "github"), (3, "Other")]) == {
        1: "GITHUB",
        2: "GITHUB_2",
        3: "OTHER",
    }


def test_the_value_of_a_key_is_hidden_wherever_it_shows_up():
    hide = Redactor([SECRET, "abc", SECRET + "-longer"])
    assert hide(f"token={SECRET} and {SECRET}") == f"token={HIDDEN} and {HIDDEN}"
    assert hide(f"x {SECRET}-longer y") == f"x {HIDDEN} y"  # the longer value is hidden as a whole
    assert hide("abc stays: too short to be a key") == "abc stays: too short to be a key"
    assert Redactor([])("nothing to hide") == "nothing to hide"


def test_the_start_script_exports_keys_by_name_and_never_contains_a_value():
    script = codex_script("m", "low", ["GITHUB_TOKEN"])
    assert 'export GITHUB_TOKEN="$(cat /run/themis-secrets/keys/GITHUB_TOKEN)"' in script
    assert (
        "ignore_default_excludes=true" in script
    )  # or Codex hides variables named TOKEN from the agent's commands
    plain = codex_script("m", "low")
    assert "export GITHUB" not in plain and "ignore_default_excludes" not in plain
    with pytest.raises(ValueError):
        codex_script("m", "low", ["BAD NAME; rm -rf /"])


# ----- the config Codex reads -----


def test_the_tool_config_is_valid_toml_whatever_the_values_contain():
    nasty = 'quote " backslash \\ newline \n tab \t unicode é'
    servers = [
        McpSpec(
            "files",
            "stdio",
            command="npx",
            args=("-y", "pkg", nasty),
            env={"MODE": "fast"},
            secret_env={"API_KEY": 7},
        ),
        McpSpec("web", "http", url="https://example.com/mcp", bearer_secret_id=8),
    ]
    parsed = tomllib.loads(config_toml(servers, {7: nasty, 8: "bearer-value"}, {8: "WEB_TOKEN"}))[
        "mcp_servers"
    ]
    assert parsed["files"] == {
        "command": "npx",
        "args": ["-y", "pkg", nasty],
        "env": {"MODE": "fast", "API_KEY": nasty},
    }
    assert parsed["web"] == {"url": "https://example.com/mcp", "bearer_token_env_var": "WEB_TOKEN"}
    assert "bearer-value" not in config_toml(
        servers, {7: nasty, 8: "bearer-value"}, {8: "WEB_TOKEN"}
    )  # read from the environment


def test_a_stdio_server_without_env_has_no_env_table():
    text = config_toml([McpSpec("a", "stdio", command="node", args=("s.js",))], {}, {})
    assert tomllib.loads(text) == {"mcp_servers": {"a": {"command": "node", "args": ["s.js"]}}}


# ----- the keys list -----


async def test_anyone_can_see_the_names_of_the_keys_but_never_the_values(client):
    await register(client)
    key = await make_key(client)
    await register(client, "c@d.co", "Bob")
    listing = await client.get("/api/keys")
    assert listing.status_code == 200 and SECRET not in listing.text
    assert listing.json() == [
        {"id": key["id"], "name": "GitHub token", "kind": "github", "env_name": "GITHUB_TOKEN"}
    ]


# ----- tool servers: the API -----


async def test_a_tool_is_made_from_a_command_line_and_listed_by_name(client):
    await register(client)
    pid = (await make_project(client))["id"]
    server = await make_server(client, pid, name="  Files ")
    assert (server["name"], server["kind"], server["command"]) == ("files", "stdio", "npx")
    assert server["args"] == ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
    await make_server(client, pid, name="web", kind="http", url="https://example.com/mcp", command="ignored")
    listed = (await client.get(f"/api/projects/{pid}/mcp-servers")).json()
    assert [(s["name"], s["kind"], s["command"]) for s in listed] == [
        ("files", "stdio", "npx"),
        ("web", "http", ""),
    ]


async def test_a_tool_that_cannot_work_is_refused_with_the_reason(client):
    await register(client)
    pid = (await make_project(client))["id"]
    bad = (
        {"name": "x", "command": ""},
        {"name": "x", "kind": "http", "url": "ftp://nope"},
        {"name": "Bad Name", "command": "npx"},
        {"name": "x", "command": "npx", "env": {"bad name": "1"}},
        {"name": "x", "command": "npx", "secret_env": {"1BAD": 1}},
    )
    for body in bad:
        assert (await client.post(f"/api/projects/{pid}/mcp-servers", json=body)).status_code == 422, body
    await make_server(client, pid)
    assert (
        await client.post(f"/api/projects/{pid}/mcp-servers", json={"name": "files", "command": "npx"})
    ).status_code == 409


async def test_a_tool_can_be_changed_and_removed_and_leaves_its_agents(client):
    await register(client)
    pid = (await make_project(client))["id"]
    server = await make_server(client, pid)
    agent = await make_agent(client, pid, mcp_servers=[server["id"]])
    assert agent["mcp_servers"] == [server["id"]]
    r = await client.put(
        f"/api/mcp-servers/{server['id']}",
        json={"name": "files", "command": "uvx some-server", "env": {"A": "1"}},
    )
    assert r.status_code == 200 and (r.json()["command"], r.json()["args"], r.json()["env"]) == (
        "uvx",
        ["some-server"],
        {"A": "1"},
    )
    assert (await client.delete(f"/api/mcp-servers/{server['id']}")).status_code == 204
    assert (await client.get(f"/api/agents/{agent['id']}")).json()["mcp_servers"] == []
    assert (await client.delete(f"/api/mcp-servers/{server['id']}")).status_code == 404


async def test_an_agent_can_only_use_tools_of_its_own_project(client):
    await register(client)
    p1, p2 = (await make_project(client, "One"))["id"], (await make_project(client, "Two"))["id"]
    foreign = await make_server(client, p2)
    r = await client.post(f"/api/projects/{p1}/agents", json={"name": "A", "mcp_servers": [foreign["id"]]})
    assert r.status_code == 422


async def test_tools_belong_to_their_projects_owner(client):
    await register(client)
    pid = (await make_project(client))["id"]
    server = await make_server(client, pid)
    await register(client, "c@d.co", "Bob")
    assert (await client.get(f"/api/projects/{pid}/mcp-servers")).status_code == 404
    assert (
        await client.put(f"/api/mcp-servers/{server['id']}", json={"name": "x", "command": "y"})
    ).status_code == 404
    assert (await client.delete(f"/api/mcp-servers/{server['id']}")).status_code == 404


# ----- who may hand out keys -----


async def test_only_an_administrator_gives_agents_and_tools_keys(client):
    await register(client)
    key = await make_key(client)
    admin_pid = (await make_project(client, "Admins"))["id"]
    ok = await make_agent(client, admin_pid, secrets=[key["id"]])
    assert ok["secrets"] == [key["id"]]

    await register(client, "c@d.co", "Bob")
    pid = (await make_project(client, "Bobs"))["id"]
    assert (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "A", "secrets": [key["id"]]})
    ).status_code == 403
    mine = await make_agent(client, pid)
    assert (await client.patch(f"/api/agents/{mine['id']}", json={"secrets": [key["id"]]})).status_code == 403
    assert (await client.patch(f"/api/agents/{mine['id']}", json={"role": "fine"})).status_code == 200
    assert (
        await client.post(
            f"/api/projects/{pid}/mcp-servers",
            json={"name": "x", "command": "npx", "secret_env": {"K": key["id"]}},
        )
    ).status_code == 403
    plain = await make_server(client, pid)
    assert (
        await client.put(
            f"/api/mcp-servers/{plain['id']}",
            json={
                "name": "files",
                "command": "npx",
                "bearer_secret_id": key["id"],
                "kind": "http",
                "url": "https://x.io",
            },
        )
    ).status_code == 403
    await login(client, "a@b.co")
    assert (await client.patch(f"/api/agents/{ok['id']}", json={"secrets": []})).json()["secrets"] == []


async def test_a_key_that_does_not_exist_is_refused(client):
    await register(client)
    pid = (await make_project(client))["id"]
    assert (
        await client.post(f"/api/projects/{pid}/agents", json={"name": "A", "secrets": [99]})
    ).status_code == 422
    r = await client.post(
        f"/api/projects/{pid}/mcp-servers", json={"name": "x", "command": "npx", "secret_env": {"K": 99}}
    )
    assert r.status_code == 422


async def test_deleting_a_key_takes_it_away_from_agents_and_tools(client, maker):
    await register(client)
    key = await make_key(client)
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid, secrets=[key["id"]])
    server = await make_server(client, pid, name="a", secret_env={"API_KEY": key["id"]})
    web = await make_server(
        client, pid, name="b", kind="http", url="https://x.io/mcp", bearer_secret_id=key["id"]
    )
    assert (await client.delete(f"/api/secrets/{key['id']}")).status_code == 204
    assert (await client.get(f"/api/agents/{agent['id']}")).json()["secrets"] == []
    servers = {s["name"]: s for s in (await client.get(f"/api/projects/{pid}/mcp-servers")).json()}
    assert servers["a"]["secret_env"] == {} and servers["b"]["bearer_secret_id"] is None
    assert server["id"] and web["id"]


# ----- running with keys and tools -----


async def test_keys_and_tools_reach_the_cell_without_showing_up_in_the_start_script(
    client, scheduler, cells, maker
):
    me = await register(client)
    await connect(maker, me["id"])
    key = await make_key(client)
    other = await make_key(client, "Search api", "search-key-1234567")
    pid = (await make_project(client))["id"]
    files = await make_server(
        client, pid, name="files", secret_env={"SEARCH_KEY": other["id"]}, env={"MODE": "ro"}
    )
    web = await make_server(
        client, pid, name="web", kind="http", url="https://x.io/mcp", bearer_secret_id=key["id"]
    )
    agent = await make_agent(client, pid, secrets=[key["id"]], mcp_servers=[files["id"], web["id"]])
    await make_task(client, pid, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    spec = cells.specs[0]
    assert spec.secret_files["/run/themis-secrets/keys/GITHUB_TOKEN"] == SECRET
    assert 'export GITHUB_TOKEN="$(cat /run/themis-secrets/keys/GITHUB_TOKEN)"' in spec.script
    assert (
        SECRET not in spec.script and "search-key-1234567" not in spec.script
    )  # the script shows on the host
    config = tomllib.loads(spec.secret_files["/run/themis-secrets/codex/config.toml"])["mcp_servers"]
    assert config["files"]["env"] == {"MODE": "ro", "SEARCH_KEY": "search-key-1234567"}
    assert config["web"] == {"url": "https://x.io/mcp", "bearer_token_env_var": "GITHUB_TOKEN"}
    assert "SEARCH_KEY" not in spec.script  # only the agent's own keys are exported to its commands


async def test_a_keys_value_is_hidden_in_the_log_and_the_result(client, scheduler, cells, maker):
    me = await register(client)
    await connect(maker, me["id"])
    key = await make_key(client)
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid, secrets=[key["id"]])
    task = await make_task(client, pid, status="ready", agent_id=agent["id"])
    cells.log_text = f"env dump: GITHUB_TOKEN={SECRET}\nheader: Bearer {SECRET}\n"
    await scheduler.tick()
    await drain(scheduler)
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    log = (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    assert SECRET not in log and f"GITHUB_TOKEN={HIDDEN}" in log and f"Bearer {HIDDEN}" in log


async def test_an_agent_without_keys_or_tools_runs_exactly_as_before(client, scheduler, cells, maker):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid)
    await make_task(client, pid, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    spec = cells.specs[0]
    assert not any("keys/" in p or p.endswith("config.toml") for p in spec.secret_files)
    assert "export GITHUB" not in spec.script and spec.skills == [] and spec.mcp == []


async def test_a_run_fails_with_the_reason_when_a_key_or_tool_is_gone(client, scheduler, maker):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid)
    async with maker() as s:  # references that were never cleaned up, as if edited by hand
        row = await s.get(Agent, agent["id"])
        row.secrets = [999]
        await s.commit()
    task = await make_task(client, pid, status="ready", agent_id=agent["id"])
    assert await scheduler.tick() == 0
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    assert "no longer exists" in (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    async with maker() as s:
        row = await s.get(Agent, agent["id"])
        row.secrets, row.mcp_servers = [], [998]
        await s.commit()
    await client.post(f"/api/tasks/{task['id']}/run")
    assert await scheduler.tick() == 0
    attempts = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()
    assert "tool server" in (await client.get(f"/api/attempts/{attempts[0]['id']}")).json()["log"]


# ----- checking tools before saving -----


async def test_tools_missing_from_the_image_are_reported(monkeypatch):
    monkeypatch.setattr(settings, "cell_backend", "docker")
    calls = []

    async def fake(args, env, timeout):
        calls.append(args)
        if args[1:3] == ["image", "inspect"]:
            return (0 if args[3] == "have:1" else 1), "", ""
        return (0 if args[-1] == "node" else 1), "", ""  # `... sh <command>`

    monkeypatch.setattr(toolcheck, "run_command", fake)
    warnings = await toolcheck.missing_commands("have:1", {"a": "node", "b": "uvx", "c": "uvx"})
    assert len(warnings) == 2 and all("'uvx' is not in the image have:1" in w for w in warnings)
    assert sum(1 for c in calls if c[1] == "run") == 2  # each command is looked up once
    assert "not on this machine yet" in (await toolcheck.missing_commands("absent:1", {"a": "node"}))[0]


async def test_nothing_is_checked_for_simulated_cells_or_without_tools(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("docker must not be called")

    monkeypatch.setattr(toolcheck, "run_command", boom)
    monkeypatch.setattr(settings, "cell_backend", "fake")
    assert (
        await toolcheck.missing_commands("x", {"a": "node"}) == []
    )  # simulated cells have no image to look in
    monkeypatch.setattr(settings, "cell_backend", "docker")
    assert await toolcheck.missing_commands("x", {}) == []


async def test_the_check_looks_in_the_image_the_agent_will_use(client, monkeypatch):
    await register(client)
    pid = (
        await client.post("/api/projects", json={"name": "P", "cell_profile": {"image": "project:1"}})
    ).json()["id"]
    server = await make_server(client, pid)
    seen = {}

    async def fake(image, commands, host=""):
        seen["image"], seen["commands"] = image, commands
        return ["a warning"]

    monkeypatch.setattr(agents_router, "missing_commands", fake)
    body = {"harness": "codex", "mcp_servers": [server["id"]]}
    r = await client.post(f"/api/projects/{pid}/agents/check", json=body)
    assert r.json() == {"image": "project:1", "warnings": ["a warning"]} and seen["commands"] == {
        "files": "npx"
    }
    r = await client.post(
        f"/api/projects/{pid}/agents/check", json={**body, "cell_profile": {"image": "agent:2"}}
    )
    assert r.json()["image"] == "agent:2"
    other = (await make_project(client, "Plain"))["id"]
    r = await client.post(f"/api/projects/{other}/agents/check", json={"harness": "codex"})
    assert r.json()["image"] == "themisforge/cell-codex:latest"  # a Codex agent's own image by default


async def test_the_harness_says_what_it_supports(client):
    await register(client)
    codex = (await client.get("/api/harnesses")).json()[0]
    assert (codex["supports_skills"], codex["supports_mcp"], codex["supports_keys"]) == (True, True, True)
