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


# custom statuses


async def _board(client, project_id):
    return (await _workspaces(client, project_id))[0]["boards"][0]


async def _add_status(client, board_id, name, **body):
    r = await client.post(f"/api/boards/{board_id}/statuses", json={"name": name, **body})
    assert r.status_code == 201, r.text
    return r.json()


def _keys(board):
    return [c["key"] for c in board["columns"]]


async def test_a_board_adds_renames_places_and_deletes_its_own_statuses(client):
    await register(client)
    pid = (await make_project(client))["id"]
    board = await _board(client, pid)

    board = await _add_status(client, board["id"], "  Investigating ", color="#AABBCC", index=1)
    keys = _keys(board)
    assert keys[0] == "backlog" and keys[1].startswith("custom:") and keys[2] == "ready"
    investigating = board["columns"][1]
    assert (investigating["name"], investigating["color"], investigating["builtin"]) == (
        "Investigating",
        "#aabbcc",
        False,
    )
    sid = investigating["key"].removeprefix("custom:")

    # the built-ins stay in their fixed order whatever is done to the custom one
    r = await client.patch(
        f"/api/boards/{board['id']}/statuses/{sid}", json={"name": "Verified", "index": 99}
    )
    assert r.status_code == 200
    columns = r.json()["columns"]
    assert [c["key"] for c in columns if c["builtin"]] == [k for k in keys if not k.startswith("custom:")]
    assert columns[-1]["name"] == "Verified"

    cleared = await client.patch(f"/api/boards/{board['id']}/statuses/{sid}", json={"color": None})
    assert cleared.json()["columns"][-1]["color"] is None


async def test_status_names_are_unique_and_limited(client):
    await register(client)
    board = await _board(client, (await make_project(client))["id"])
    await _add_status(client, board["id"], "Waiting")
    for name in ("waiting", "Done", " "):  # twice, a built-in's name, nothing
        r = await client.post(f"/api/boards/{board['id']}/statuses", json={"name": name})
        assert r.status_code == 422, name
    bad_color = await client.post(f"/api/boards/{board['id']}/statuses", json={"name": "x", "color": "red"})
    assert bad_color.status_code == 422
    for n in range(19):
        await _add_status(client, board["id"], f"S{n}")
    assert (
        await client.post(f"/api/boards/{board['id']}/statuses", json={"name": "one more"})
    ).status_code == 409


async def test_tasks_can_sit_in_their_boards_custom_status_only(client):
    await register(client)
    pid = (await make_project(client))["id"]
    [workspace] = await _workspaces(client, pid)
    first = workspace["boards"][0]
    second = (await client.post(f"/api/workspaces/{workspace['id']}/boards", json={"name": "QA"})).json()
    mine = (await _add_status(client, first["id"], "Mine"))["columns"][-1]["key"]
    theirs = (await _add_status(client, second["id"], "Theirs"))["columns"][-1]["key"]

    task = await make_task(client, pid, status=mine)
    assert task["status"] == mine
    refused = await client.post(f"/api/projects/{pid}/tasks", json={"title": "t", "status": theirs})
    assert refused.status_code == 422
    assert (await client.patch(f"/api/tasks/{task['id']}", json={"status": theirs})).status_code == 422
    assert (await client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})).json()[
        "status"
    ] == "done"
    assert (
        await client.patch(f"/api/tasks/{task['id']}", json={"status": "custom:99999"})
    ).status_code == 422


async def test_deleting_a_status_moves_its_tasks_and_keeps_the_order(client):
    await register(client)
    pid = (await make_project(client))["id"]
    board = await _board(client, pid)
    key = (await _add_status(client, board["id"], "Parked"))["columns"][-1]["key"]
    sid = key.removeprefix("custom:")
    existing = await make_task(client, pid, title="already", status="review")
    a = await make_task(client, pid, title="a", status=key)
    b = await make_task(client, pid, title="b", status=key)

    for refused in ("ready", "running", key):
        r = await client.delete(f"/api/boards/{board['id']}/statuses/{sid}", params={"move_to": refused})
        assert r.status_code in (409, 422), refused
    r = await client.delete(f"/api/boards/{board['id']}/statuses/{sid}", params={"move_to": "review"})
    assert r.status_code == 200 and key not in _keys(r.json())

    tasks = {t["title"]: t for t in (await client.get(f"/api/projects/{pid}/tasks")).json()}
    assert {t["status"] for t in tasks.values()} == {"review"}
    assert tasks["already"]["position"] < tasks["a"]["position"] < tasks["b"]["position"]
    assert (existing["id"], a["id"], b["id"]) == (tasks["already"]["id"], tasks["a"]["id"], tasks["b"]["id"])
    assert (await client.delete(f"/api/boards/{board['id']}/statuses/{sid}")).status_code == 404  # gone


async def test_a_task_in_a_custom_status_is_never_started_by_the_scheduler(client, scheduler, cells):
    await register(client)
    pid = (await make_project(client))["id"]
    board = await _board(client, pid)
    key = (await _add_status(client, board["id"], "Parked"))["columns"][-1]["key"]
    task = await make_task(client, pid, status=key)
    await scheduler.tick()
    assert not cells.specs
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == key
    assert (await client.get(f"/api/tasks/{task['id']}/attempts")).json() == []


async def test_a_custom_status_does_not_follow_a_task_to_another_board(client):
    await register(client)
    pid = (await make_project(client))["id"]
    [workspace] = await _workspaces(client, pid)
    first = workspace["boards"][0]
    second = (await client.post(f"/api/workspaces/{workspace['id']}/boards", json={"name": "QA"})).json()
    key = (await _add_status(client, second["id"], "Parked"))["columns"][-1]["key"]
    await make_task(client, pid, board_id=second["id"], status=key)
    await make_task(client, pid, board_id=second["id"], status="done")

    assert (
        await client.delete(f"/api/boards/{second['id']}", params={"move_to": first["id"]})
    ).status_code == 204
    assert sorted(t["status"] for t in (await client.get(f"/api/projects/{pid}/tasks")).json()) == [
        "backlog",
        "done",
    ]
