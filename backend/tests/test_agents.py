from tests.conftest import drain, login, make_project, make_task, register
from tests.test_harness import connect
from tests.test_workflows import by_id, edge, node, run, runner, setup  # noqa: F401


async def make_agent(client, pid: int, **body) -> dict:
    body.setdefault("name", "Researcher")
    r = await client.post(f"/api/projects/{pid}/agents", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_an_agent_is_created_with_its_defaults_and_listed_by_name(client):
    await register(client)
    pid = (await make_project(client))["id"]
    assert (await client.get(f"/api/projects/{pid}/agents")).json() == []  # nothing is made behind your back
    agent = await make_agent(client, pid, name="  Reviewer ", role=" checks the diffs ")
    assert agent["name"] == "Reviewer" and agent["role"] == "checks the diffs"
    assert (agent["harness"], agent["model"], agent["reasoning_effort"]) == ("codex", "", "")
    assert agent["cell_profile"] is None and agent["mounts"] == []
    await make_agent(client, pid, name="Archivist")
    assert [a["name"] for a in (await client.get(f"/api/projects/{pid}/agents")).json()] == [
        "Archivist",
        "Reviewer",
    ]


async def test_names_are_unique_per_project_and_checked(client):
    await register(client)
    p1, p2 = (await make_project(client, "One"))["id"], (await make_project(client, "Two"))["id"]
    await make_agent(client, p1)
    assert (await client.post(f"/api/projects/{p1}/agents", json={"name": "Researcher"})).status_code == 409
    await make_agent(client, p2)  # another project may reuse the name
    other = await make_agent(client, p1, name="Other")
    assert (await client.patch(f"/api/agents/{other['id']}", json={"name": "Researcher"})).status_code == 409
    for bad in (
        {"name": "  "},
        {"name": "x", "harness": "pi"},
        {"name": "x", "model": "a b"},
        {"name": "x", "model": "-m"},
        {"name": "x", "reasoning_effort": "max"},
    ):
        assert (await client.post(f"/api/projects/{p1}/agents", json=bad)).status_code == 422, bad


async def test_an_agent_can_be_edited_piece_by_piece(client):
    await register(client)
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid, instructions="Be brief.", cell_profile={"cpus": 2})
    r = await client.patch(
        f"/api/agents/{agent['id']}", json={"role": "writes the summary", "model": "gpt-6-sol"}
    )
    body = r.json()
    assert body["role"] == "writes the summary" and body["model"] == "gpt-6-sol"
    assert body["instructions"] == "Be brief." and body["cell_profile"] == {"cpus": 2}  # untouched
    assert (await client.patch(f"/api/agents/{agent['id']}", json={"cell_profile": None})).json()[
        "cell_profile"
    ] is None
    assert (
        await client.patch(f"/api/agents/{agent['id']}", json={"cell_profile": {"cpus": 0}})
    ).status_code == 422
    assert (await client.delete(f"/api/agents/{agent['id']}")).status_code == 204
    assert (await client.get(f"/api/agents/{agent['id']}")).status_code == 404


async def test_an_agents_folders_must_belong_to_its_project_and_asking_twice_keeps_the_last(client):
    await register(client)
    p1, p2 = (await make_project(client, "One"))["id"], (await make_project(client, "Two"))["id"]
    mine = (await client.post(f"/api/projects/{p1}/volumes", json={"name": "mine"})).json()
    theirs = (await client.post(f"/api/projects/{p2}/volumes", json={"name": "theirs"})).json()
    r = await client.post(
        f"/api/projects/{p1}/agents", json={"name": "A", "mounts": [{"volume_id": theirs["id"]}]}
    )
    assert r.status_code == 422
    agent = await make_agent(
        client, p1, mounts=[{"volume_id": mine["id"], "mode": "rw"}, {"volume_id": mine["id"], "mode": "ro"}]
    )
    assert agent["mounts"] == [{"volume_id": mine["id"], "mode": "ro"}]


async def test_agents_belong_to_their_projects_owner(client):
    await register(client)
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid)
    await register(client, "c@d.co", "Bob")
    assert (await client.get(f"/api/projects/{pid}/agents")).status_code == 404
    assert (await client.get(f"/api/agents/{agent['id']}")).status_code == 404
    assert (await client.patch(f"/api/agents/{agent['id']}", json={"name": "x"})).status_code == 404
    assert (await client.delete(f"/api/agents/{agent['id']}")).status_code == 404
    await login(client, "a@b.co")
    assert (await client.get(f"/api/agents/{agent['id']}")).status_code == 200


async def test_the_editor_can_ask_what_harnesses_exist(client):
    await register(client)
    harnesses = (await client.get("/api/harnesses")).json()
    assert [h["id"] for h in harnesses] == ["codex"] and harnesses[0]["label"] == "Codex"


async def test_deleting_an_agent_keeps_its_tasks(client):
    await register(client)
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid)
    task = await make_task(client, pid, agent_id=agent["id"])
    await client.delete(f"/api/agents/{agent['id']}")
    after = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert after["agent_id"] is None and after["harness"] == "codex"


# ----- tasks with an agent -----


async def test_a_task_with_an_agent_takes_the_agents_harness(client):
    await register(client)
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid)
    task = await make_task(client, pid, agent_id=agent["id"])
    assert task["agent_id"] == agent["id"] and task["harness"] == "codex"
    plain = await make_task(client, pid, title="plain")
    assert plain["agent_id"] is None and plain["harness"] == ""
    patched = (await client.patch(f"/api/tasks/{plain['id']}", json={"agent_id": agent["id"]})).json()
    assert patched["agent_id"] == agent["id"] and patched["harness"] == "codex"
    cleared = (await client.patch(f"/api/tasks/{plain['id']}", json={"agent_id": None, "harness": ""})).json()
    assert cleared["agent_id"] is None and cleared["harness"] == ""


async def test_a_task_cannot_use_an_agent_of_another_project(client):
    await register(client)
    p1, p2 = (await make_project(client, "One"))["id"], (await make_project(client, "Two"))["id"]
    foreign = await make_agent(client, p2)
    r = await client.post(f"/api/projects/{p1}/tasks", json={"title": "t", "agent_id": foreign["id"]})
    assert r.status_code == 422
    task = await make_task(client, p1)
    assert (
        await client.patch(f"/api/tasks/{task['id']}", json={"agent_id": foreign["id"]})
    ).status_code == 422


async def test_an_agent_runs_with_its_own_words_model_cell_and_folders(client, scheduler, cells, maker):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (
        await client.post("/api/projects", json={"name": "P", "cell_profile": {"memory_mb": 2048, "cpus": 2}})
    ).json()["id"]
    docs = (await client.post(f"/api/projects/{pid}/volumes", json={"name": "docs"})).json()
    agent = await make_agent(
        client, pid, name="Archivist", role="files the reports", instructions="Always name files by date.",
        model="gpt-6-sol", reasoning_effort="low", cell_profile={"cpus": 1, "timeout_seconds": 120},
        mounts=[{"volume_id": docs["id"], "mode": "ro"}],
    )  # fmt: skip
    await make_task(
        client, pid, title="File it", description="File today's report.", status="ready", agent_id=agent["id"]
    )
    await scheduler.tick()
    await drain(scheduler)
    spec = cells.specs[0]
    assert spec.harness == "codex" and spec.image == "themisforge/cell-codex:latest"
    assert "-m gpt-6-sol" in spec.script and "model_reasoning_effort=low" in spec.script
    assert (spec.cpus, spec.memory_mb, spec.timeout_seconds) == (
        1,
        2048,
        120,
    )  # project, then the agent on top
    assert [(m.name, m.read_only) for m in spec.mounts] == [("docs", True), ("shared", False)]
    prompt = spec.prompt
    assert prompt.startswith("You are Archivist, files the reports.\n\nAlways name files by date.")
    assert "/workspace/docs (read only)" in prompt and "/workspace/shared (read and write)" in prompt
    assert "File today's report." in prompt


async def test_without_an_agent_the_prompt_and_model_are_what_they_were(client, scheduler, cells, maker):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    await make_task(client, pid, title="Plain", status="ready", harness="codex")
    await scheduler.tick()
    await drain(scheduler)
    spec = cells.specs[0]
    assert spec.prompt.startswith("# Plain") and "-m gpt-6-luna" in spec.script


# ----- the workflow Agent node -----


async def test_an_agent_node_runs_the_chosen_agent_with_node_level_extras(client, runner, cells, maker):  # noqa: F811
    me, pid = await setup(client)
    await connect(maker, me["id"])
    out = (await client.post(f"/api/projects/{pid}/volumes", json={"name": "out"})).json()
    agent = await make_agent(
        client, pid, name="Writer", instructions="Write like a poet.", cell_profile={"memory_mb": 512}
    )
    detail = await run(
        client, pid,
        [node("s", "start"), node("a", "agent", "Draft", agentId=str(agent["id"]), instructions="Write the intro",
              cellCpus="2", mounts=f'{out["id"]}:rw'), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )  # fmt: skip
    assert detail["status"] == "succeeded", detail
    spec = next(s for s in cells.specs if s.harness == "codex")
    assert (spec.cpus, spec.memory_mb) == (2, 512)  # the node's cpus, the agent's memory
    assert [m.name for m in spec.mounts] == ["out", "shared"]
    assert "Write like a poet." in spec.prompt and "Write the intro" in spec.prompt
    task = next(t for t in (await client.get(f"/api/projects/{pid}/tasks")).json() if t["title"] == "Draft")
    assert task["agent_id"] == agent["id"]


async def test_an_agent_node_whose_agent_was_deleted_fails_with_the_reason(client, runner):  # noqa: F811
    _, pid = await setup(client)
    agent = await make_agent(client, pid)
    await client.delete(f"/api/agents/{agent['id']}")
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("a", "agent", agentId=str(agent["id"]), instructions="x")],
        [edge("s", "a")],
    )
    assert detail["status"] == "failed"
    assert "no longer exists" in by_id(detail)["a"]["error"]


async def test_an_agent_node_with_an_agent_from_another_project_is_refused(client, runner):  # noqa: F811
    _, pid = await setup(client)
    other = (await make_project(client, "Other"))["id"]
    foreign = await make_agent(client, other)
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("a", "agent", agentId=str(foreign["id"]), instructions="x")],
        [edge("s", "a")],
    )
    assert "no longer exists" in by_id(detail)["a"]["error"]


async def test_an_agent_node_with_unusable_cell_settings_fails_before_running_anything(client, runner, cells):  # noqa: F811
    _, pid = await setup(client)
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("a", "agent", instructions="x", cellCpus="-1")],
        [edge("s", "a")],
    )
    assert "not valid" in by_id(detail)["a"]["error"] and not cells.specs
