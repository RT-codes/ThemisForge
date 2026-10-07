"""The config folder: agents, skills and tools as files, and the rows that follow them (app/project_config.py)."""

import pytest
from sqlalchemy import select

from app import project_config as pc
from app.app_settings import AppSettings
from app.config import settings
from app.models import Agent, McpServer
from app.volumes import MountError, plan_mounts
from tests.conftest import login, make_project, register
from tests.test_agents import make_agent
from tests.test_skills import skill_md
from tests.test_tools import make_key, make_server


def config_dir(pid: int):
    return settings.data_dir / "projects" / str(pid) / "config"


async def config_volume(client, pid: int) -> int:
    return (await client.get(f"/api/projects/{pid}/config")).json()["id"]


def put(client, vid, path, text):
    return client.put(
        f"/api/volumes/{vid}/file", params={"path": path, "overwrite": True}, content=text.encode()
    )


@pytest.fixture
async def project(client):
    await register(client)
    return (await make_project(client))["id"]


# ----- the file formats -----


def test_an_agent_file_round_trips_with_awkward_text():
    af = pc.AgentFile(
        name="Researcher: the 2nd",
        role="finds # sources",
        description="Line one\n\nLine three: with a colon",
        model="gpt-5",
        reasoning_effort="high",
        cell=pc.ProfileOverrides(cpus=2, memory_mb=2048),
        folders=[pc.FolderRef(name="notes", mode="ro")],
        skills=["pdf-tips"],
        tools=["files"],
        keys=["GitHub token"],
        instructions="# Heading\n\n---\nNot a frontmatter line\n\n- be brief",
    )
    assert pc.parse_agent(pc.render_agent(af)) == af


def test_a_file_that_is_not_an_agent_is_refused_with_a_hint():
    cases = {
        "no frontmatter": "must start with",
        "---\nname: a\nno end": "never closed",
        "---\nname: [unclosed\n---\n": "cannot be read",
        "---\nrole: x\n---\n": "name",
        "---\nname: a\ncolour: red\n---\n": "'colour' is not a setting",
        "---\nname: a\ninstructions: x\n---\n": "text below the settings",
        "---\nname: a\nharness: pi\n---\n": "harness",
    }
    for text, hint in cases.items():
        with pytest.raises(pc.ConfigError, match=hint):
            pc.parse_agent(text)


def test_a_tool_file_is_read_in_both_kinds_and_numbers_become_text():
    web = pc.parse_mcp("kind: http\nurl: https://example.com/mcp\nbearer_key: Token\n")
    assert (web.kind, web.url, web.bearer_key) == ("http", "https://example.com/mcp", "Token")
    local = pc.parse_mcp("command: npx\nargs: [-y, pkg, 8080]\nenv: {PORT: 8080}\n")
    assert local.args == ["-y", "pkg", "8080"] and local.env == {"PORT": "8080"}
    with pytest.raises(pc.ConfigError, match="not a setting"):
        pc.parse_mcp("comand: npx\n")


# ----- the API writes the files -----


async def test_an_agent_made_through_the_api_gets_a_file_that_says_the_same(client, project):
    await client.put(f"/api/projects/{project}/skills/pdf-tips", json={"content": skill_md()})
    server = await make_server(client, project)
    agent = await make_agent(
        client,
        project,
        name="Code Reviewer",
        instructions="Be brief.",
        skills=["pdf-tips"],
        mcp_servers=[server["id"]],
    )
    assert agent["path"] == "agents/code-reviewer/agent.md" and agent["config_error"] == ""
    af = pc.parse_agent((config_dir(project) / agent["path"]).read_text())
    assert (af.name, af.instructions, af.skills, af.tools) == (
        "Code Reviewer",
        "Be brief.",
        ["pdf-tips"],
        ["files"],
    )
    assert (config_dir(project) / "mcp" / "files.yaml").is_file()
    assert (config_dir(project) / "skills" / "pdf-tips" / "SKILL.md").is_file()


async def test_renaming_an_agent_moves_its_folder_and_keeps_its_id(client, project):
    agent = await make_agent(client, project, name="Researcher")
    other = await make_agent(client, project, name="Researcher 2")  # slug researcher-2
    assert other["path"] == "agents/researcher-2/agent.md"
    renamed = (await client.patch(f"/api/agents/{agent['id']}", json={"name": "Archivist"})).json()
    assert renamed["id"] == agent["id"] and renamed["path"] == "agents/archivist/agent.md"
    assert not (config_dir(project) / "agents" / "researcher").exists()
    assert (config_dir(project) / "agents" / "archivist" / "agent.md").is_file()


async def test_deleting_an_agent_takes_its_file_away_but_not_notes_kept_beside_it(client, project):
    gone = await make_agent(client, project, name="Gone")
    kept = await make_agent(client, project, name="Kept")
    (config_dir(project) / "agents" / "kept" / "notes.md").write_text("mine")
    for a in (gone, kept):
        assert (await client.delete(f"/api/agents/{a['id']}")).status_code == 204
    assert not (config_dir(project) / "agents" / "gone").exists()
    assert (config_dir(project) / "agents" / "kept" / "notes.md").is_file()
    assert not (config_dir(project) / "agents" / "kept" / "agent.md").exists()


async def test_agents_from_before_the_files_existed_get_theirs(client, maker, project):
    async with maker() as s:  # a row as the old version made it: no path
        s.add(Agent(project_id=project, name="Old Timer", instructions="Old ways."))
        s.add(McpServer(project_id=project, name="old-tool", command="npx", args=["-y", "x"]))
        await s.commit()
    agents = (await client.get(f"/api/projects/{project}/agents")).json()
    assert agents[0]["path"] == "agents/old-timer/agent.md"
    assert "Old ways." in (config_dir(project) / "agents" / "old-timer" / "agent.md").read_text()
    assert "command: npx" in (config_dir(project) / "mcp" / "old-tool.yaml").read_text()


async def test_skills_made_before_the_config_folder_are_moved_into_it(client, project):
    old = settings.data_dir / "projects" / str(project) / "skills" / "pdf-tips"
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text(skill_md())
    assert [s["name"] for s in (await client.get(f"/api/projects/{project}/skills")).json()] == ["pdf-tips"]
    assert (config_dir(project) / "skills" / "pdf-tips" / "SKILL.md").is_file()
    assert not old.exists()


# ----- editing the files is editing the agent -----


async def test_an_agent_file_saved_through_the_files_page_changes_the_agent(client, project):
    agent = await make_agent(client, project, name="Researcher")
    vid = await config_volume(client, project)
    text = (config_dir(project) / agent["path"]).read_text().replace("role: ''", "role: digs deep")
    assert (await put(client, vid, agent["path"], text + "\nNew words.\n")).status_code == 204
    fresh = (await client.get(f"/api/agents/{agent['id']}")).json()
    assert fresh["role"] == "digs deep" and fresh["instructions"] == "New words."


async def test_a_new_agent_file_makes_an_agent_and_a_moved_folder_keeps_its_id(client, project):
    vid = await config_volume(client, project)
    assert (await client.post(f"/api/volumes/{vid}/folder", json={"path": "agents/scout"})).status_code == 201
    assert (
        await put(client, vid, "agents/scout/agent.md", "---\nname: Scout\n---\nGo.\n")
    ).status_code == 204
    (scout,) = (await client.get(f"/api/projects/{project}/agents")).json()
    assert scout["name"] == "Scout" and scout["path"] == "agents/scout/agent.md"
    r = await client.post(
        f"/api/volumes/{vid}/move", json={"source": "agents/scout", "destination": "agents/ranger"}
    )
    assert r.status_code == 204
    (moved,) = (await client.get(f"/api/projects/{project}/agents")).json()
    assert (
        moved["id"] == scout["id"]
        and moved["path"] == "agents/ranger/agent.md"
        and moved["config_error"] == ""
    )


async def test_a_file_that_could_not_work_is_refused_with_a_reason_and_not_saved(client, project):
    agent = await make_agent(client, project)
    vid = await config_volume(client, project)
    path = agent["path"]
    before = (config_dir(project) / path).read_text()
    for text, reason in (
        ("no settings", "must start with"),
        (before.replace("skills: []", "skills: [nope]"), "skill 'nope' does not exist"),
        (before.replace("tools: []", "tools: [nope]"), "tool 'nope' does not exist"),
        (before.replace("folders: []", "folders: [{name: nope}]"), "folder 'nope' does not exist"),
    ):
        r = await put(client, vid, path, text)
        assert r.status_code == 422 and reason in r.json()["detail"], text
    assert (config_dir(project) / path).read_text() == before
    # a skill and a tool are checked the same way
    skill = await put(client, vid, "skills/pdf-tips/SKILL.md", "no frontmatter")
    assert skill.status_code == 404  # the folder is not there yet, but a bad file never gets that far
    r = await put(client, vid, "mcp/web.yaml", "kind: http\nurl: ftp://x\n")
    assert r.status_code == 422 and "http" in r.json()["detail"]


async def test_two_agents_cannot_share_a_name_through_their_files(client, project):
    await make_agent(client, project, name="Researcher")
    vid = await config_volume(client, project)
    await client.post(f"/api/volumes/{vid}/folder", json={"path": "agents/copy"})
    r = await put(client, vid, "agents/copy/agent.md", "---\nname: Researcher\n---\n")
    assert r.status_code == 422 and "already called" in r.json()["detail"]


async def test_a_file_broken_on_disk_keeps_the_last_good_agent_and_stops_its_runs(client, project):
    agent = await make_agent(client, project, instructions="Fine.")
    file = config_dir(project) / agent["path"]
    file.write_text("garbage")  # out of band, past the Files page's checks
    (shown,) = (await client.get(f"/api/projects/{project}/agents")).json()
    assert shown["instructions"] == "Fine." and "must start with" in shown["config_error"]
    # saving the agent from the editor writes the file again and clears the problem
    ok = (await client.patch(f"/api/agents/{agent['id']}", json={"role": "back"})).json()
    assert ok["config_error"] == "" and pc.parse_agent(file.read_text()).role == "back"


async def test_a_missing_file_flags_the_agent_instead_of_deleting_it(client, project):
    agent = await make_agent(client, project)
    (config_dir(project) / agent["path"]).unlink()
    (shown,) = (await client.get(f"/api/projects/{project}/agents")).json()
    assert shown["id"] == agent["id"] and "missing" in shown["config_error"]


async def test_only_an_administrator_can_give_keys_through_a_file(client, project):
    key = await make_key(client)
    agent = await make_agent(client, project, name="Keeper", secrets=[key["id"]])
    assert agent["secrets"] == [key["id"]]
    assert "keys:\n  - GitHub token" in (config_dir(project) / agent["path"]).read_text()
    # a user who is not an administrator owns another project; their agent file may not name a key
    await register(client, "b@c.de", "Bob")
    other = (await make_project(client, "Bob's"))["id"]
    vid = await config_volume(client, other)
    await client.post(f"/api/volumes/{vid}/folder", json={"path": "agents/bob"})
    ok = await put(client, vid, "agents/bob/agent.md", "---\nname: Bob\n---\n")
    assert ok.status_code == 204
    r = await put(client, vid, "agents/bob/agent.md", "---\nname: Bob\nkeys: [GitHub token]\n---\n")
    assert r.status_code == 422 and "administrator" in r.json()["detail"]
    await login(client, "a@b.co")


async def test_deleting_what_an_agent_uses_rewrites_its_file(client, project):
    await client.put(f"/api/projects/{project}/skills/pdf-tips", json={"content": skill_md()})
    server = await make_server(client, project)
    key = await make_key(client)
    agent = await make_agent(
        client, project, skills=["pdf-tips"], mcp_servers=[server["id"]], secrets=[key["id"]]
    )
    file = config_dir(project) / agent["path"]
    assert (await client.delete(f"/api/projects/{project}/skills/pdf-tips")).status_code == 204
    assert pc.parse_agent(file.read_text()).skills == []
    assert (await client.delete(f"/api/secrets/{key['id']}")).status_code == 204
    assert pc.parse_agent(file.read_text()).keys == []
    assert (await client.delete(f"/api/mcp-servers/{server['id']}")).status_code == 204
    assert pc.parse_agent(file.read_text()).tools == []
    assert not (config_dir(project) / "mcp" / "files.yaml").exists()
    assert (await client.get(f"/api/agents/{agent['id']}")).json()["config_error"] == ""


async def test_renaming_a_tool_renames_its_file_and_the_agents_that_use_it(client, project):
    server = await make_server(client, project)
    agent = await make_agent(client, project, mcp_servers=[server["id"]])
    body = {k: server[k] for k in ("kind", "command", "args", "url", "env", "secret_env", "bearer_secret_id")}
    r = await client.put(f"/api/mcp-servers/{server['id']}", json={**body, "name": "disk"})
    assert r.status_code == 200 and r.json()["path"] == "mcp/disk.yaml"
    assert not (config_dir(project) / "mcp" / "files.yaml").exists()
    assert pc.parse_agent((config_dir(project) / agent["path"]).read_text()).tools == ["disk"]


async def test_a_tool_file_edited_in_the_files_page_changes_the_tool(client, project):
    server = await make_server(client, project, description="before")
    vid = await config_volume(client, project)
    text = (config_dir(project) / server["path"]).read_text().replace("before", "after")
    assert (await put(client, vid, server["path"], text)).status_code == 204
    (shown,) = (await client.get(f"/api/projects/{project}/mcp-servers")).json()
    assert shown["id"] == server["id"] and shown["description"] == "after"


# ----- the config folder is never a shared folder -----


async def test_the_config_folder_is_hidden_from_pickers_and_cannot_be_mounted(client, maker, project):
    shared = (await client.get(f"/api/projects/{project}/volumes")).json()
    assert [v["name"] for v in shared] == ["shared"]  # the pickers see only what can be mounted
    everything = (await client.get(f"/api/projects/{project}/volumes?include_config=true")).json()
    config = everything[-1]  # the config folder comes last
    assert config["kind"] == "config" and everything[0]["name"] == "shared"
    r = await client.post(
        f"/api/projects/{project}/agents",
        json={"name": "x", "mounts": [{"volume_id": config["id"], "mode": "ro"}]},
    )
    assert r.status_code == 422
    async with maker() as s:  # even a mount that got into a row by other means cannot reach a cell
        with pytest.raises(MountError, match="cannot be mounted"):
            await plan_mounts(s, project, [{"volume_id": config["id"], "mode": "ro"}], AppSettings())
    assert (await client.patch(f"/api/volumes/{config['id']}", json={"mode": "ro"})).status_code == 409
    assert (await client.delete(f"/api/volumes/{config['id']}")).status_code == 409


async def test_themis_own_folders_cannot_be_renamed_or_deleted(client, project):
    vid = await config_volume(client, project)
    for name in ("agents", "skills", "mcp"):
        assert (await client.delete(f"/api/volumes/{vid}/file", params={"path": name})).status_code == 422
    r = await client.post(f"/api/volumes/{vid}/move", json={"source": "agents", "destination": "people"})
    assert r.status_code == 422
    assert {e["name"] for e in (await client.get(f"/api/volumes/{vid}/files")).json()["entries"]} == {
        "agents",
        "skills",
        "mcp",
    }


async def test_a_host_folder_cannot_be_the_config_folder(client, project):
    r = await client.post(
        f"/api/projects/{project}/volumes",
        json={"name": "sneaky", "kind": "host", "host_path": str(config_dir(project))},
    )
    assert r.status_code == 422


# ----- trying a tool -----


async def test_a_command_tool_is_checked_against_the_image_and_the_result_is_remembered(client, project):
    server = await make_server(client, project)
    r = await client.post(f"/api/mcp-servers/{server['id']}/test")
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["tools"] == []
    (shown,) = (await client.get(f"/api/projects/{project}/mcp-servers")).json()
    assert shown["last_test"]["ok"] is True


async def test_a_web_tool_is_tried_with_its_key_for_an_administrator_only(client, project, monkeypatch):
    seen = []

    async def fake_probe(url, bearer):
        seen.append((url, bearer))
        from app.mcp import ProbeResult

        return ProbeResult(True, "Connected to demo 1. It offers 2 tools.", ("a", "b"))

    monkeypatch.setattr("app.routers.tools.probe_http", fake_probe)
    key = await make_key(client, value="sk-the-secret-value-1234")
    server = await make_server(
        client,
        project,
        name="web",
        kind="http",
        url="https://example.com/mcp",
        bearer_secret_id=key["id"],
        command="",
    )
    r = await client.post(f"/api/mcp-servers/{server['id']}/test")
    assert r.json()["tools"] == ["a", "b"] and seen == [
        ("https://example.com/mcp", "sk-the-secret-value-1234")
    ]
    assert "sk-the-secret-value-1234" not in r.text


async def test_the_probe_reads_json_and_event_stream_answers():
    from app.mcp import _reply

    body = b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'
    assert _reply("application/json", body, 1)["result"] == {"ok": True}
    sse = b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n\n'
    assert _reply("text/event-stream", sse, 2)["result"] == {"tools": []}
    assert _reply("application/json", b"not json", 1) is None
    assert _reply("application/json", body, 9) is None  # an answer to some other request


async def test_every_project_is_synced_at_startup(client, maker, project):
    async with maker() as s:
        s.add(Agent(project_id=project, name="Sleeper"))
        await s.commit()
    await pc.sync_all_configs(maker)
    async with maker() as s:
        assert (
            await s.scalar(select(Agent.path).where(Agent.name == "Sleeper"))
        ) == "agents/sleeper/agent.md"
