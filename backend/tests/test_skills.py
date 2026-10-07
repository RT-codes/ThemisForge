import pytest

from app import skills as store
from app.cells import CellSpec, DockerCellManager
from app.config import settings
from tests.conftest import drain, login, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_harness import connect

SKILL = "---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nDo the thing carefully.\n"


def skill_md(name="pdf-tips", description="Use when a task involves PDF files") -> str:
    return SKILL.format(name=name, description=description)


# ----- the file format -----


def test_the_frontmatter_is_read_in_its_plain_quoted_and_block_forms():
    assert store.parse_frontmatter(skill_md()) == {
        "name": "pdf-tips",
        "description": "Use when a task involves PDF files",
    }
    quoted = store.parse_frontmatter("---\nname: 'a'\ndescription: \"b: with a colon\"\n---\nbody")
    assert quoted == {"name": "a", "description": "b: with a colon"}
    block = store.parse_frontmatter("---\nname: a\ndescription: >\n  first part\n  second part\n---\nbody")
    assert block["description"] == "first part second part"
    assert store.parse_frontmatter("﻿---\nname: a\n---\n") == {"name": "a"}  # a byte order mark is fine


def test_a_file_without_proper_frontmatter_is_refused_with_a_hint():
    for bad, hint in (("no frontmatter", "must start with"), ("---\nname: a\nno end", "never closed")):
        with pytest.raises(store.SkillError, match=hint):
            store.parse_frontmatter(bad)


def test_a_skill_is_validated_against_its_name():
    assert store.validate("pdf-tips", skill_md()) == "Use when a task involves PDF files"
    with pytest.raises(store.SkillError, match="must be pdf-tips"):
        store.validate("pdf-tips", skill_md(name="other"))
    with pytest.raises(store.SkillError, match="description"):
        store.validate("a", "---\nname: a\n---\nbody")
    with pytest.raises(store.SkillError, match="at most"):
        store.validate("a", skill_md("a") + "x" * store.MAX_SKILL_BYTES)


def test_a_name_cannot_lead_out_of_the_skills_folder():
    for bad in ("../up", "a/b", "A", "-x", "", "x" * 41, ".hidden"):
        with pytest.raises(store.SkillError):
            store.skill_dir(1, bad)


# ----- the API -----


async def test_skills_are_made_listed_read_changed_and_removed(client):
    await register(client)
    pid = (await make_project(client))["id"]
    assert (await client.get(f"/api/projects/{pid}/skills")).json() == []
    r = await client.put(f"/api/projects/{pid}/skills/pdf-tips", json={"content": skill_md()})
    assert r.status_code == 200 and r.json() == {
        "name": "pdf-tips",
        "description": "Use when a task involves PDF files",
        "files": 1,
    }
    assert (
        settings.data_dir / "projects" / str(pid) / "config" / "skills" / "pdf-tips" / "SKILL.md"
    ).is_file()
    detail = (await client.get(f"/api/projects/{pid}/skills/pdf-tips")).json()
    assert detail["content"] == skill_md() and detail["description"].startswith("Use when")
    await client.put(
        f"/api/projects/{pid}/skills/pdf-tips", json={"content": skill_md(description="Changed")}
    )
    assert [s["description"] for s in (await client.get(f"/api/projects/{pid}/skills")).json()] == ["Changed"]
    assert (await client.delete(f"/api/projects/{pid}/skills/pdf-tips")).status_code == 204
    assert (await client.get(f"/api/projects/{pid}/skills/pdf-tips")).status_code == 404
    assert (await client.delete(f"/api/projects/{pid}/skills/pdf-tips")).status_code == 404


async def test_a_skill_with_a_wrong_file_or_name_is_refused_with_the_reason(client):
    await register(client)
    pid = (await make_project(client))["id"]
    r = await client.put(f"/api/projects/{pid}/skills/pdf-tips", json={"content": skill_md(name="other")})
    assert r.status_code == 422 and "must be pdf-tips" in r.text
    assert (
        await client.put(f"/api/projects/{pid}/skills/Bad_Name", json={"content": skill_md("x")})
    ).status_code == 422
    assert (
        await client.put(f"/api/projects/{pid}/skills/ok", json={"content": "just text"})
    ).status_code == 422
    assert (await client.get(f"/api/projects/{pid}/skills")).json() == []


async def test_extra_files_in_a_skill_folder_are_kept_and_counted(client):
    await register(client)
    pid = (await make_project(client))["id"]
    await client.put(f"/api/projects/{pid}/skills/pdf-tips", json={"content": skill_md()})
    folder = settings.data_dir / "projects" / str(pid) / "config" / "skills" / "pdf-tips"
    (folder / "scripts").mkdir()
    (folder / "scripts" / "extract.py").write_text("print('hi')")
    assert (await client.get(f"/api/projects/{pid}/skills")).json()[0]["files"] == 2
    await client.put(f"/api/projects/{pid}/skills/pdf-tips", json={"content": skill_md(description="New")})
    assert (
        folder / "scripts" / "extract.py"
    ).read_text() == "print('hi')"  # editing SKILL.md leaves the rest alone


async def test_skills_belong_to_their_projects_owner(client):
    await register(client)
    pid = (await make_project(client))["id"]
    await client.put(f"/api/projects/{pid}/skills/pdf-tips", json={"content": skill_md()})
    await register(client, "c@d.co", "Bob")
    assert (await client.get(f"/api/projects/{pid}/skills")).status_code == 404
    assert (await client.get(f"/api/projects/{pid}/skills/pdf-tips")).status_code == 404
    assert (
        await client.put(f"/api/projects/{pid}/skills/x", json={"content": skill_md("x")})
    ).status_code == 404
    assert (await client.delete(f"/api/projects/{pid}/skills/pdf-tips")).status_code == 404
    await login(client, "a@b.co")


async def test_an_agent_can_only_be_given_skills_that_exist_and_loses_them_when_they_are_deleted(client):
    await register(client)
    pid = (await make_project(client))["id"]
    r = await client.post(f"/api/projects/{pid}/agents", json={"name": "A", "skills": ["nope"]})
    assert r.status_code == 422 and "nope" in r.text
    await client.put(f"/api/projects/{pid}/skills/pdf-tips", json={"content": skill_md()})
    await client.put(f"/api/projects/{pid}/skills/web", json={"content": skill_md("web")})
    agent = await make_agent(client, pid, skills=["pdf-tips", "web", "web"])
    assert agent["skills"] == ["pdf-tips", "web"]  # asked for twice, given once
    await client.delete(f"/api/projects/{pid}/skills/web")
    assert (await client.get(f"/api/agents/{agent['id']}")).json()["skills"] == ["pdf-tips"]
    assert (await client.patch(f"/api/agents/{agent['id']}", json={"skills": ["gone"]})).status_code == 422


# ----- giving them to a cell -----


async def test_only_the_agents_skills_are_copied_into_its_cell_and_mounted_read_only(
    client, scheduler, cells, maker
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    for name in ("pdf-tips", "web"):
        await client.put(f"/api/projects/{pid}/skills/{name}", json={"content": skill_md(name)})
    (settings.data_dir / "projects" / str(pid) / "config" / "skills" / "pdf-tips" / "notes.txt").write_text(
        "extra"
    )
    agent = await make_agent(client, pid, skills=["pdf-tips"])
    await make_task(client, pid, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    spec = cells.specs[0]
    assert spec.skills == ["pdf-tips"]
    assert (spec.skills_dir / "pdf-tips" / "SKILL.md").is_file() and (
        spec.skills_dir / "pdf-tips" / "notes.txt"
    ).is_file()
    assert not (spec.skills_dir / "web").exists()  # the agent was not given it
    assert (spec.workspace_dir / ".agents" / "skills").is_dir()  # the mountpoint, made by us


def test_docker_mounts_the_staged_skills_read_only_where_codex_looks(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    spec = CellSpec(
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
        skills=["a"],
    )
    args = DockerCellManager().build_args(spec)
    assert f"{spec.skills_dir}:/workspace/.agents/skills:ro" in args
    none = DockerCellManager().build_args(
        CellSpec(
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
        )
    )
    assert not any(".agents" in a for a in none)


async def test_a_run_fails_with_the_reason_when_a_skill_was_removed_from_disk(client, scheduler):
    me = await register(client)
    await connect(scheduler.maker, me["id"])
    pid = (await make_project(client))["id"]
    await client.put(f"/api/projects/{pid}/skills/pdf-tips", json={"content": skill_md()})
    agent = await make_agent(client, pid, skills=["pdf-tips"])
    import shutil

    shutil.rmtree(settings.data_dir / "projects" / str(pid) / "config" / "skills" / "pdf-tips")
    task = await make_task(client, pid, status="ready", agent_id=agent["id"])
    assert await scheduler.tick() == 0
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "failed"
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    assert "does not exist" in (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
