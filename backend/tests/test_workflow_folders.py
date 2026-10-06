from app.workflows import MOUNT, Graph
from tests.conftest import make_project, register
from tests.test_agents import make_agent
from tests.test_harness import connect
from tests.test_workflows import by_id, edge, make_workflow, node, run, runner, save, setup  # noqa: F401


def mount_edge(folder: str, agent: str) -> dict:
    return {
        "id": f"{folder}-{agent}-mount",
        "source": folder,
        "target": agent,
        "sourceHandle": MOUNT,
        "targetHandle": MOUNT,
    }


def folder(id_: str, volume_id: int | str = "", mode: str = "rw", label: str = "") -> dict:
    return node(id_, "volume", label or id_, volumeId=str(volume_id), mode=mode)


async def make_volume(client, pid: int, name: str, **body) -> dict:
    r = await client.post(f"/api/projects/{pid}/volumes", json={"name": name, **body})
    assert r.status_code == 201, r.text
    return r.json()


# ----- the graph -----


def test_a_folder_can_only_be_handed_to_an_agent():
    nodes = [node("s", "start"), node("t", "task"), node("a", "agent"), folder("f")]
    Graph.model_validate({"nodes": nodes, "edges": [mount_edge("f", "a")]})  # fine
    for bad in (mount_edge("f", "t"), mount_edge("s", "a")):
        try:
            Graph.model_validate({"nodes": nodes, "edges": [bad]})
        except ValueError as e:
            assert "Agent node" in str(e)
        else:
            raise AssertionError(f"{bad} should have been refused")


def test_a_folder_is_not_a_step():
    nodes = [node("s", "start"), node("a", "agent"), folder("f")]
    for bad in (edge("s", "f"), edge("f", "a")):  # an ordinary line to or from a folder
        try:
            Graph.model_validate({"nodes": nodes, "edges": [bad]})
        except ValueError as e:
            assert "not a step" in str(e)
        else:
            raise AssertionError("an ordinary line to a folder should have been refused")


def test_the_folders_of_an_agent_come_from_its_mount_lines_only():
    graph = Graph.model_validate(
        {
            "nodes": [
                node("s", "start"),
                node("a", "agent"),
                node("b", "agent"),
                folder("f1", 3, "ro"),
                folder("f2", 5),
            ],
            "edges": [edge("s", "a"), mount_edge("f1", "a"), mount_edge("f2", "a"), mount_edge("f2", "b")],
        }
    )
    assert graph.mounts_for("a") == [{"volume_id": 3, "mode": "ro"}, {"volume_id": 5, "mode": "rw"}]
    assert graph.mounts_for("b") == [{"volume_id": 5, "mode": "rw"}]
    assert graph.mounts_for("s") == []


async def test_the_mount_point_is_kept_when_a_workflow_is_saved(client):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    await save(client, wid, [node("a", "agent"), folder("f", 1)], [mount_edge("f", "a")])
    saved = (await client.get(f"/api/workflows/{wid}")).json()["graph"]["edges"][0]
    assert (saved["sourceHandle"], saved["targetHandle"]) == ("mount", "mount")
    bad = await client.patch(
        f"/api/workflows/{wid}",
        json={"graph": {"nodes": [node("s", "start"), folder("f")], "edges": [edge("s", "f")]}},
    )
    assert bad.status_code == 422


# ----- running -----


async def test_a_folder_handed_to_an_agent_is_mounted_and_changes_nothing_else(client, runner, cells, maker):  # noqa: F811
    me, pid = await setup(client)
    await connect(maker, me["id"])
    out = await make_volume(client, pid, "out")
    docs = await make_volume(client, pid, "docs")
    agent = await make_agent(client, pid, name="Writer")
    detail = await run(
        client, pid,
        [node("s", "start"), node("a", "agent", "Draft", agentId=str(agent["id"]), instructions="Write it"), node("e", "end"),
         folder("f1", out["id"], "rw", "Out folder"), folder("f2", docs["id"], "ro", "Docs folder")],
        [edge("s", "a"), edge("a", "e"), mount_edge("f1", "a"), mount_edge("f2", "a")],
    )  # fmt: skip
    assert detail["status"] == "succeeded", detail
    spec = next(s for s in cells.specs if s.harness == "codex")
    assert {(m.name, m.read_only) for m in spec.mounts} == {("out", False), ("docs", True), ("shared", False)}
    assert [n["node_id"] for n in detail["nodes"]] == [
        "s",
        "a",
        "e",
    ]  # the folders are not steps, run or skipped
    assert "/workspace/docs (read only)" in spec.prompt


async def test_a_folder_node_that_is_not_connected_is_simply_ignored(client, runner, cells):  # noqa: F811
    _, pid = await setup(client)
    out = await make_volume(client, pid, "out")
    detail = await run(
        client, pid, [node("s", "start"), node("e", "end"), folder("f", out["id"])], [edge("s", "e")]
    )
    assert detail["status"] == "succeeded" and [n["node_id"] for n in detail["nodes"]] == ["s", "e"]


async def test_a_nodes_own_folder_list_wins_over_a_connected_folder(client, runner, cells, maker):  # noqa: F811
    me, pid = await setup(client)
    await connect(maker, me["id"])
    a, b = await make_volume(client, pid, "alpha"), await make_volume(client, pid, "beta")
    agent = await make_agent(client, pid, name="Writer")
    await run(
        client, pid,
        [node("s", "start"), node("a", "agent", agentId=str(agent["id"]), instructions="x", mounts=f"{b['id']}:ro,{a['id']}:ro"),
         folder("fa", a["id"], "rw"), folder("fb", b["id"], "rw")],
        [edge("s", "a"), mount_edge("fa", "a"), mount_edge("fb", "a")],
    )  # fmt: skip
    spec = next(s for s in cells.specs if s.harness == "codex")
    modes = {m.name: m.read_only for m in spec.mounts}
    assert (
        modes["alpha"] is True and modes["beta"] is True
    )  # both lines said read and write; the node's list said read only


async def test_a_folder_node_with_no_folder_chosen_stops_the_agent_with_the_reason(client, runner, cells):  # noqa: F811
    _, pid = await setup(client)
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("a", "agent", instructions="x"), folder("f", "", label="Empty folder")],
        [edge("s", "a"), mount_edge("f", "a")],
    )
    assert detail["status"] == "failed" and not cells.specs
    assert "no folder chosen" in by_id(detail)["a"]["error"] and "Empty folder" in by_id(detail)["a"]["error"]


async def test_a_folder_that_was_removed_fails_the_agents_run_with_the_reason(client, runner, cells, maker):  # noqa: F811
    me, pid = await setup(client)
    await connect(maker, me["id"])
    gone = await make_volume(client, pid, "gone")
    await client.delete(f"/api/volumes/{gone['id']}")
    agent = await make_agent(client, pid, name="Writer")
    detail = await run(
        client,
        pid,
        [
            node("s", "start"),
            node("a", "agent", agentId=str(agent["id"]), instructions="x"),
            folder("f", gone["id"]),
        ],
        [edge("s", "a"), mount_edge("f", "a")],
    )
    assert (
        detail["status"] == "failed"
        and "no longer exists" in by_id(detail)["a"]["error"] + by_id(detail)["a"]["log"]
    )


async def test_the_same_workflow_without_folders_runs_as_before(client, runner, cells, maker):  # noqa: F811
    me, pid = await setup(client)
    await connect(maker, me["id"])
    detail = await run(
        client,
        pid,
        [node("s", "start"), node("a", "agent", harness="codex", instructions="x"), node("e", "end")],
        [edge("s", "a"), edge("a", "e")],
    )
    assert detail["status"] == "succeeded"
    assert [m.name for m in next(s for s in cells.specs if s.harness == "codex").mounts] == ["shared"]
    assert make_project and register  # imported for the shared helpers
