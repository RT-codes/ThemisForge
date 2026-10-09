from tests.conftest import make_project, make_task, register


async def _workspaces(client, project_id):
    return (await client.get(f"/api/projects/{project_id}/workspaces")).json()


async def test_a_new_project_starts_with_a_workspace_and_a_board(client):
    await register(client)
    project = await make_project(client)
    [workspace] = await _workspaces(client, project["id"])
    assert workspace["name"] == "Main"
    [board] = workspace["boards"]
    assert board["name"] == "Tasks"
    assert [c["key"] for c in board["columns"]] == [
        "backlog",
        "ready",
        "running",
        "review",
        "done",
        "blocked",
        "failed",
    ]
    assert all(c["builtin"] for c in board["columns"])

    task = await make_task(client, project["id"])
    assert task["board_id"] == board["id"]


async def test_tasks_land_on_the_chosen_board_and_lists_can_be_filtered(client):
    await register(client)
    project = await make_project(client)
    pid = project["id"]
    [workspace] = await _workspaces(client, pid)
    first = workspace["boards"][0]
    second = (await client.post(f"/api/workspaces/{workspace['id']}/boards", json={"name": "QA"})).json()

    on_first = await make_task(client, pid, title="a")
    on_second = await make_task(client, pid, title="b", board_id=second["id"])
    assert (on_first["board_id"], on_second["board_id"]) == (first["id"], second["id"])

    listed = (await client.get(f"/api/projects/{pid}/tasks", params={"board_id": second["id"]})).json()
    assert [t["title"] for t in listed] == ["b"]
    assert len((await client.get(f"/api/projects/{pid}/tasks")).json()) == 2


async def test_a_board_of_another_project_is_refused(client):
    await register(client)
    one, two = await make_project(client, "One"), await make_project(client, "Two")
    foreign = (await _workspaces(client, two["id"]))[0]["boards"][0]
    r = await client.post(f"/api/projects/{one['id']}/tasks", json={"title": "t", "board_id": foreign["id"]})
    assert r.status_code == 422


async def test_workspaces_and_boards_can_be_renamed_and_reordered(client):
    await register(client)
    pid = (await make_project(client))["id"]
    [main] = await _workspaces(client, pid)
    extra = (await client.post(f"/api/projects/{pid}/workspaces", json={"name": "  Ops  "})).json()
    assert extra["name"] == "Ops" and extra["boards"] == []

    r = await client.patch(f"/api/workspaces/{extra['id']}", json={"purpose": "Run things", "position": 0.5})
    assert r.status_code == 200
    assert [w["name"] for w in await _workspaces(client, pid)] == ["Ops", "Main"]

    board = main["boards"][0]
    moved = await client.patch(f"/api/boards/{board['id']}", json={"workspace_id": extra["id"], "name": "Q"})
    assert moved.json()["workspace_id"] == extra["id"] and moved.json()["name"] == "Q"
    assert (await client.patch(f"/api/boards/{board['id']}", json={"name": "  "})).status_code == 422


async def test_deleting_a_board_hands_its_tasks_to_another_board(client):
    await register(client)
    pid = (await make_project(client))["id"]
    [workspace] = await _workspaces(client, pid)
    first = workspace["boards"][0]
    second = (await client.post(f"/api/workspaces/{workspace['id']}/boards", json={"name": "QA"})).json()
    keep = await make_task(client, pid, title="keep", status="done")
    moved_a = await make_task(client, pid, title="a", board_id=second["id"], status="done")
    moved_b = await make_task(client, pid, title="b", board_id=second["id"], status="done")

    assert (await client.delete(f"/api/boards/{second['id']}")).status_code == 409  # its tasks need a home
    assert (
        await client.delete(f"/api/boards/{second['id']}", params={"move_to": second["id"]})
    ).status_code == 409

    assert (
        await client.delete(f"/api/boards/{second['id']}", params={"move_to": first["id"]})
    ).status_code == 204
    tasks = {t["title"]: t for t in (await client.get(f"/api/projects/{pid}/tasks")).json()}
    assert {t["board_id"] for t in tasks.values()} == {first["id"]}
    # they join the end of their column, in the order they had
    assert tasks["keep"]["position"] < tasks["a"]["position"] < tasks["b"]["position"]
    assert (moved_a["id"], moved_b["id"]) == (tasks["a"]["id"], tasks["b"]["id"])

    last = await client.delete(f"/api/boards/{first['id']}", params={"move_to": first["id"]})
    assert last.status_code == 409  # a project keeps a board
    assert keep["id"] == tasks["keep"]["id"]


async def test_deleting_a_workspace_moves_the_tasks_of_all_its_boards(client):
    await register(client)
    pid = (await make_project(client))["id"]
    [main] = await _workspaces(client, pid)
    other = (await client.post(f"/api/projects/{pid}/workspaces", json={"name": "Other"})).json()
    board = (await client.post(f"/api/workspaces/{other['id']}/boards", json={"name": "B"})).json()
    await make_task(client, pid, board_id=board["id"])

    assert (await client.delete(f"/api/workspaces/{other['id']}")).status_code == 409
    done = await client.delete(f"/api/workspaces/{other['id']}", params={"move_to": main["boards"][0]["id"]})
    assert done.status_code == 204
    assert [t["board_id"] for t in (await client.get(f"/api/projects/{pid}/tasks")).json()] == [
        main["boards"][0]["id"]
    ]
    assert (await client.delete(f"/api/workspaces/{main['id']}")).status_code == 409  # the last one stays


async def test_other_users_cannot_see_or_change_boards(client):
    await register(client)
    pid = (await make_project(client))["id"]
    [workspace] = await _workspaces(client, pid)
    board = workspace["boards"][0]
    await register(client, "c@d.co", "Bob")
    assert (await client.get(f"/api/projects/{pid}/workspaces")).status_code == 404
    assert (await client.patch(f"/api/boards/{board['id']}", json={"name": "x"})).status_code == 404
    assert (await client.delete(f"/api/workspaces/{workspace['id']}")).status_code == 404
