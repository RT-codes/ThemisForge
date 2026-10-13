"""The Themis package: the rules in every prompt and the themis-cell skill in every cell, readable and editable in
Settings, empty text meaning the built-in one."""

from app.cell_package import DEFAULT_RULES, DEFAULT_SKILL, SKILLS_MOUNT_AT, skills_root
from app.cells import CellSpec, DockerCellManager, prepare_dirs
from tests.conftest import drain, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_harness import connect


async def put_package(client, **fields) -> None:
    settings = (await client.get("/api/settings")).json()
    settings["cell_package"].update(fields)
    r = await client.put("/api/settings", json=settings)
    assert r.status_code == 200, r.text


async def codex_agent(client, maker) -> tuple[int, dict]:
    """A signed in administrator with Codex connected, and a project with an agent."""
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    return pid, await make_agent(client, pid)


async def run_task(client, scheduler, cells, pid: int, agent: dict, title: str) -> CellSpec:
    await make_task(client, pid, title=title, status="ready", agent_id=agent["id"])
    await scheduler.tick()
    await drain(scheduler)
    return cells.specs[-1]


def spec(**kw) -> CellSpec:
    base = {
        "attempt_id": 7, "task_id": 1, "project_id": 1, "title": "t", "description": "", "properties": {},
        "image": "img", "cpus": 1, "memory_mb": 256, "timeout_seconds": 60,
    }  # fmt: skip
    return CellSpec(**{**base, **kw})


async def test_the_built_in_package_is_in_every_codex_run(client, scheduler, cells, maker):
    pid, agent = await codex_agent(client, maker)
    run = await run_task(client, scheduler, cells, pid, agent, "Anything")
    assert DEFAULT_RULES in run.prompt
    assert run.package_skill == DEFAULT_SKILL


async def test_edited_rules_replace_the_built_in_ones_and_switching_them_off_removes_them(
    client, scheduler, cells, maker
):
    pid, agent = await codex_agent(client, maker)
    await put_package(client, rules="Ask before you delete anything.")
    run = await run_task(client, scheduler, cells, pid, agent, "First")
    assert "Ask before you delete anything." in run.prompt and DEFAULT_RULES not in run.prompt

    await put_package(client, rules_enabled=False)
    run = await run_task(client, scheduler, cells, pid, agent, "Second")
    assert "Ask before you delete anything." not in run.prompt and "/cell/blocked.md" not in run.prompt
    assert "/run/themis-secrets" in run.prompt  # the line about credentials is not a setting


async def test_the_skill_can_be_edited_and_switched_off(client, scheduler, cells, maker):
    pid, agent = await codex_agent(client, maker)
    edited = DEFAULT_SKILL.replace("# This cell", "# This cell, with our own notes")
    await put_package(client, skill=edited)
    assert (await run_task(client, scheduler, cells, pid, agent, "First")).package_skill == edited

    await put_package(client, skill_enabled=False)
    assert (await run_task(client, scheduler, cells, pid, agent, "Second")).package_skill == ""


async def test_the_skill_is_staged_once_and_mounted_read_only_outside_the_cell_folder(tmp_path):
    first = spec(package_skill=DEFAULT_SKILL)
    prepare_dirs(first)
    staged = skills_root() / "themis-cell" / "SKILL.md"
    assert staged.read_text() == DEFAULT_SKILL
    assert first.cell_dir not in staged.parents  # /cell is writable by the agent, this must not be

    args = DockerCellManager().build_args(first)
    mount = next(a for a in args if f"target={SKILLS_MOUNT_AT}" in a)
    assert "readonly" in mount and str(skills_root()) in mount

    prepare_dirs(spec(package_skill=DEFAULT_SKILL + "\nMore.\n"))  # an edit replaces it for the next run
    assert staged.read_text().endswith("More.\n")

    plain = spec()
    prepare_dirs(plain)
    assert not any(f"target={SKILLS_MOUNT_AT}" in a for a in DockerCellManager().build_args(plain))


async def test_settings_validate_the_skill_and_the_retry_waits(client):
    await register(client)
    settings = (await client.get("/api/settings")).json()

    async def put(**fields):
        return await client.put(
            "/api/settings", json={**settings, "cell_package": {**settings["cell_package"], **fields}}
        )

    assert (await put(skill="no front matter")).status_code == 422
    assert (await put(skill="---\nname: other\ndescription: x\n---\n")).status_code == 422
    assert (await put(skill="---\nname: themis-cell\ndescription:\n---\n")).status_code == 422
    assert (await put(retry_waits=[10] * 11)).status_code == 422
    assert (await put(retry_waits=[-1])).status_code == 422
    assert (await put(retry_waits=[])).status_code == 200  # never retry
    assert (await put(skill="  ")).json()["cell_package"]["skill"] == ""  # empty means the built-in one


async def test_only_an_administrator_sees_the_built_in_text(client):
    await register(client)
    shown = (await client.get("/api/settings/cell-package")).json()
    assert shown == {"rules": DEFAULT_RULES, "skill": DEFAULT_SKILL}

    other = await register(client, email="second@example.com")  # an invited user, now signed in
    assert other["is_admin"] is False
    assert (await client.get("/api/settings/cell-package")).status_code == 403


async def test_every_user_can_read_the_package_agents_get(client):
    await register(client)
    shown = (await client.get("/api/cell-package")).json()
    assert shown["skill_name"] == "themis-cell" and shown["skill"] == DEFAULT_SKILL
    assert shown["rules"] == DEFAULT_RULES and shown["skill_enabled"] and shown["description"]

    await put_package(
        client, skill="---\nname: themis-cell\ndescription: Mine\n---\nbody", rules_enabled=False
    )
    shown = (await client.get("/api/cell-package")).json()
    assert shown["description"] == "Mine" and "body" in shown["skill"]
    assert shown["rules"] == "" and shown["rules_enabled"] is False  # what agents get: nothing

    other = await register(client, email="second@example.com")  # not an administrator
    assert other["is_admin"] is False
    assert (await client.get("/api/cell-package")).status_code == 200
