import json

from app import connections
from app.app_settings import AppSettings
from app.cells import CellResult, CellSpec, DockerCellManager, prepare_dirs
from app.claude import API_KEY_ENV, SUBSCRIPTION_ENV
from app.config import settings
from app.harness import CLAUDE_MCP, ClaudeRenderer, TokenUsage, plan_for, renderer_for
from app.keys import key_path
from app.mcp import CONFIG_PATH, McpSpec, config_file
from tests.conftest import API_KEY, SUBSCRIPTION, drain, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_claude_connection import connect
from tests.test_harness import run_one
from tests.test_volumes import bind_mounts


def ev(**kw) -> str:
    return json.dumps(kw) + "\n"


def assistant(*blocks) -> str:
    return ev(type="assistant", message={"content": list(blocks)})


# ----- plan -----


def test_plan_for_claude_uses_its_own_image_model_and_effort():
    cfg = AppSettings(claude_image="my/claude:1", claude_model="claude-opus-5-5")
    plan = plan_for("claude", cfg, key_envs=[SUBSCRIPTION_ENV])
    assert plan and plan.image == "my/claude:1" and plan.model == "claude-opus-5-5"
    assert plan.writeback == ()  # the token does not rotate, so there is nothing to store afterwards
    assert "claude -p" in plan.script and "--output-format stream-json" in plan.script
    assert "--model claude-opus-5-5" in plan.script and "--effort high" in plan.script
    assert f"export {SUBSCRIPTION_ENV}=" in plan.script and key_path(SUBSCRIPTION_ENV) in plan.script
    assert "SECRET" not in plan.script


def test_an_effort_the_claude_model_does_not_accept_falls_back_to_its_default():
    plan = plan_for("claude", AppSettings(), model="claude-haiku-5-5", effort="max")
    assert plan and "--effort medium" in plan.script


# ----- the log -----


def test_the_stream_becomes_a_readable_log():
    r = ClaudeRenderer()
    out = r.feed(
        ev(type="system", subtype="init", session_id="s1", model="claude-sonnet-5-5")
        + assistant({"type": "thinking", "thinking": "plan it"})
        + assistant({"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}})
        + ev(type="user", message={"content": [{"type": "tool_result", "content": "a.txt\nb.txt"}]})
        + assistant({"type": "tool_use", "name": "Read", "input": {"file_path": "/workspace/a.txt"}})
        + assistant({"type": "text", "text": "Found two files."})
        + ev(
            type="result",
            subtype="success",
            is_error=False,
            result="Found two files.",
            usage={
                "input_tokens": 5,
                "cache_creation_input_tokens": 20,
                "cache_read_input_tokens": 75,
                "output_tokens": 9,
            },
        )
    )
    assert "[claude] session s1, model claude-sonnet-5-5" in out
    assert "[thinking] plan it" in out and "$ ls -la\n" in out and "a.txt\nb.txt" in out
    assert "[tool] Read /workspace/a.txt" in out and "Found two files." in out
    assert "[claude] done - 100 tokens in, 9 out" in out and '"type"' not in out
    # cached input is part of the input, like Codex's numbers
    assert r.usage == TokenUsage(input_tokens=100, cached_input_tokens=75, output_tokens=9)
    assert not r.error


def test_a_tool_error_is_marked_and_a_failed_run_keeps_its_reason():
    r = ClaudeRenderer()
    out = r.feed(
        ev(type="user", message={"content": [{"type": "tool_result", "content": "boom", "is_error": True}]})
        + ev(
            type="result", subtype="error_during_execution", is_error=True, result="API Error: 529 overloaded"
        )
    )
    assert "boom\n[error]" in out and "[claude] error: API Error: 529 overloaded" in out
    assert r.error == "API Error: 529 overloaded" and r.transient_error and not r.login_rejected


def test_a_refused_login_is_recognised_and_not_retried():
    r = ClaudeRenderer()
    r.feed(ev(type="result", subtype="success", is_error=True, result="Invalid API key · Please run /login"))
    assert r.login_rejected and not r.transient_error


def test_the_real_clis_message_for_a_rejected_token_is_a_refused_login():
    # copied from running `claude -p` with a made-up token
    message = "Failed to authenticate. API Error: 401 OAuth access token is invalid."
    r = ClaudeRenderer()
    out = r.feed(ev(type="result", subtype="success", is_error=True, result=message, api_error_status=401))
    assert r.login_rejected and not r.transient_error and f"[claude] error: {message}" in out


def test_the_clis_own_retries_show_in_the_log():
    out = ClaudeRenderer().feed(
        ev(type="system", subtype="api_retry", attempt=2, max_retries=10, error="authentication_failed")
    )
    assert out == "[claude] retrying (2 of 10): authentication_failed\n"


def test_lines_split_across_chunks_and_plain_text_are_kept():
    r = ClaudeRenderer()
    line = assistant({"type": "text", "text": "hi"})
    assert r.feed(line[:10]) == "" and "hi" in r.feed(line[10:])
    assert r.feed("a warning\n") == "a warning\n"


def test_renderer_for_picks_the_harness_renderer():
    assert isinstance(renderer_for("claude"), ClaudeRenderer) and renderer_for("") is None


# ----- a run -----


async def test_a_claude_task_without_a_connection_fails_clearly(client, scheduler, cells):
    _, t, detail = await run_one(client, scheduler, title="agent job", harness="claude")
    assert not cells.specs
    assert "Claude Code is not connected" in detail["failure"]["reason"]
    assert (await client.get(f"/api/tasks/{t['id']}")).json()["status"] == "failed"


async def test_a_claude_task_runs_with_the_owners_token_and_its_own_log(client, scheduler, cells, anthropic):
    await register(client)
    assert (await connect(client, SUBSCRIPTION)).status_code == 201
    pid = (await make_project(client))["id"]
    t = await make_task(client, pid, title="agent job", description="do it", status="ready", harness="claude")
    cells.log_text = assistant({"type": "text", "text": "all done"}) + ev(
        type="result", is_error=False, result="all done", usage={"input_tokens": 4, "output_tokens": 2}
    )
    await scheduler.tick()
    await drain(scheduler)

    spec = cells.specs[0]
    assert spec.image == "themisforge/cell-claude:latest" and spec.harness == "claude"
    assert spec.secret_files[key_path(SUBSCRIPTION_ENV)] == SUBSCRIPTION
    assert "claude -p" in spec.script and f'export {SUBSCRIPTION_ENV}="$(cat' in spec.script
    assert SUBSCRIPTION not in repr(spec.script) and settings.secret_key not in spec.script
    attempt = (await client.get(f"/api/tasks/{t['id']}/attempts")).json()[0]
    detail = (await client.get(f"/api/attempts/{attempt['id']}")).json()
    assert "all done" in detail["log"] and '"type"' not in detail["log"] and SUBSCRIPTION not in detail["log"]
    assert detail["harness"] == "claude" and detail["model"] == "claude-sonnet-5-5"
    assert (await client.get(f"/api/tasks/{t['id']}")).json()["status"] == "done"


def test_the_login_helper_is_the_connections_module():
    assert connections.get_provider("claude").harness == "claude"


# ----- skills and tools -----


def spec_for(**kw):
    return CellSpec(
        attempt_id=3,
        task_id=1,
        project_id=1,
        title="t",
        description="",
        properties={},
        image="x",
        cpus=1,
        memory_mb=64,
        timeout_seconds=30,
        **kw,
    )


def test_claude_gets_the_agents_skills_and_the_cell_skill_in_one_read_only_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    (tmp_path / "projects" / "1" / "config" / "skills" / "pdf-tips").mkdir(parents=True)
    (tmp_path / "projects" / "1" / "config" / "skills" / "pdf-tips" / "SKILL.md").write_text("x")
    spec = spec_for(harness="claude", skills=["pdf-tips"], package_skill="THE CELL SKILL")
    prepare_dirs(spec)
    assert (spec.skills_dir / "pdf-tips" / "SKILL.md").is_file()
    assert (spec.skills_dir / "themis-cell" / "SKILL.md").read_text() == "THE CELL SKILL"
    assert (spec.workspace_dir / ".claude" / "skills").is_dir()
    mounts = bind_mounts(DockerCellManager().build_args(spec))
    skills = next(m for m in mounts if m["target"] == "/workspace/.claude/skills")
    assert skills["source"] == str(spec.skills_dir) and skills["readonly"] is True
    assert not any(m["target"] in ("/etc/codex/skills", "/workspace/.agents/skills") for m in mounts)


def test_claude_without_skills_still_gets_the_cell_skill():
    spec = spec_for(harness="claude", package_skill="THE CELL SKILL")
    assert spec.mounts_skills
    assert not spec_for(harness="claude").mounts_skills  # no skill text, nothing to mount


def test_claudes_tool_servers_are_a_json_file_and_tokens_stay_out_of_it():
    servers = [
        McpSpec("fs", "stdio", command="node", args=("s.js",), env={"A": "1"}, secret_env={"KEY": 7}),
        McpSpec("web", "http", url="https://x.test/mcp", bearer_secret_id=8),
        McpSpec("signed", "http", url="https://y.test/mcp", login_env="MCP_SIGNED_TOKEN"),
    ]
    path, text = config_file("claude", servers, {7: 'a"quote', 8: "bearer-value"}, {8: "WEB_TOKEN"})
    assert path == CLAUDE_MCP
    parsed = json.loads(text)["mcpServers"]
    assert parsed["fs"] == {
        "type": "stdio",
        "command": "node",
        "args": ["s.js"],
        "env": {"A": "1", "KEY": 'a"quote'},
    }
    assert parsed["web"]["headers"] == {"Authorization": "Bearer ${WEB_TOKEN}"}
    assert parsed["signed"]["headers"] == {"Authorization": "Bearer ${MCP_SIGNED_TOKEN}"}
    assert "bearer-value" not in text
    assert config_file("codex", servers, {7: "k", 8: "b"}, {8: "W"})[0] == CONFIG_PATH


async def test_a_claude_task_with_tools_gets_the_json_config_as_a_secret_file(
    client, scheduler, cells, anthropic
):
    await register(client)
    await connect(client, SUBSCRIPTION)
    pid = (await make_project(client))["id"]
    tool = await client.post(
        f"/api/projects/{pid}/mcp-servers", json={"name": "fs", "kind": "stdio", "command": "node s.js"}
    )
    assert tool.status_code in (200, 201), tool.text
    agent = await make_agent(client, pid, harness="claude", mcp_servers=[tool.json()["id"]])
    await make_task(client, pid, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    spec = cells.specs[0]
    assert json.loads(spec.secret_files[CLAUDE_MCP])["mcpServers"]["fs"]["command"] == "node"
    assert CONFIG_PATH not in spec.secret_files


# ----- billing, usage and trouble -----


async def claude_task(client, title: str, token: str = SUBSCRIPTION) -> dict:
    await register(client)
    assert (await connect(client, token)).status_code == 201
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid, harness="claude")
    return await make_task(client, pid, title=title, status="ready", agent_id=agent["id"])


async def attempt_of(client, task: dict) -> dict:
    first = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    return (await client.get(f"/api/attempts/{first['id']}")).json()


async def test_a_subscription_run_is_billed_to_the_plan_and_an_api_key_run_to_the_key(
    client, scheduler, cells, anthropic
):
    task = await claude_task(client, "On the plan")
    await scheduler.tick()
    await drain(scheduler)
    assert (await attempt_of(client, task))["billing"] == "subscription"

    # a newer connection (an API key) is the one runs sign in with from then on
    assert (await connect(client, API_KEY)).status_code == 201
    pid = task["project_id"]
    agent = await make_agent(client, pid, harness="claude", name="Keyed")
    keyed = await make_task(client, pid, title="On the key", status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    got = await attempt_of(client, keyed)
    assert (got["harness"], got["billing"]) == ("claude", "api")
    assert cells.specs[-1].secret_files[key_path(API_KEY_ENV)] == API_KEY
    assert key_path(SUBSCRIPTION_ENV) not in cells.specs[-1].secret_files


async def test_claude_usage_is_recorded_and_runs_started_again_are_all_counted(
    client, scheduler, cells, anthropic
):
    task = await claude_task(client, "Upgrade a component")
    settings = (await client.get("/api/settings")).json()
    settings["cell_package"]["retry_waits"] = [0, 0]
    assert (await client.put("/api/settings", json=settings)).status_code == 200
    cells.capacity_errors["Upgrade a component"] = 2  # two runs end in an overloaded API, the third works
    cells.usage["Upgrade a component"] = {"input_tokens": 100, "output_tokens": 10}

    await scheduler.tick()
    await drain(scheduler)

    attempt = await attempt_of(client, task)
    assert len(cells.specs) == 3 and attempt["status"] == "succeeded"
    assert (attempt["input_tokens"], attempt["output_tokens"]) == (300, 30)


async def test_a_refused_claude_login_fails_the_run_with_a_reason_and_no_retry(
    client, scheduler, cells, anthropic
):
    task = await claude_task(client, "Needs a login")

    async def run(spec, on_log):
        await on_log(ev(type="result", is_error=True, result="Invalid API key · Please run /login"))
        return CellResult(exit_code=1)

    cells.run = run
    await scheduler.tick()
    await drain(scheduler)

    attempt = await attempt_of(client, task)
    assert attempt["status"] == "failed"
    assert attempt["failure"]["reason"].startswith("Claude Code refused the saved login")
    assert "Connect Claude Code again" in attempt["failure"]["action"]
