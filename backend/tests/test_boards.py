from tests.conftest import drain, make_project, make_task, register


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


async def test_boards_report_their_task_counts(client):
    await register(client)
    pid = (await make_project(client))["id"]
    await make_task(client, pid, status="done")
    await make_task(client, pid, status="done")
    await make_task(client, pid)
    assert (await _board(client, pid))["task_counts"] == {"done": 2, "backlog": 1}


async def test_duplicating_a_board_copies_its_statuses_but_not_its_tasks(client):
    await register(client)
    pid = (await make_project(client))["id"]
    board = await _board(client, pid)
    board = await _add_status(client, board["id"], "Parked", color="#112233", index=2)
    await make_task(client, pid)

    r = await client.post(f"/api/boards/{board['id']}/duplicate")
    assert r.status_code == 201
    copy = r.json()
    assert copy["name"] == "Tasks copy" and copy["workspace_id"] == board["workspace_id"]
    assert copy["task_counts"] == {}
    assert [c["name"] for c in copy["columns"]] == [c["name"] for c in board["columns"]]
    # its own statuses, not the original's: renaming one must not touch the other
    assert _keys(copy) != _keys(board) and [k for k in _keys(copy) if not k.startswith("custom:")] == [
        k for k in _keys(board) if not k.startswith("custom:")
    ]
    custom = next(c for c in copy["columns"] if not c["builtin"])
    assert custom["color"] == "#112233"


# moving and spawning


async def _two_boards(client):
    pid = (await make_project(client))["id"]
    [workspace] = await _workspaces(client, pid)
    first = workspace["boards"][0]
    second = (await client.post(f"/api/workspaces/{workspace['id']}/boards", json={"name": "QA"})).json()
    return pid, first, second


async def _history(client, pid, **params):
    return (await client.get(f"/api/projects/{pid}/history", params=params)).json()


async def _of_kind(client, pid, kind):
    return await _history(client, pid, kind=kind)


async def test_a_moved_task_keeps_its_identity_and_the_move_is_recorded(client):
    await register(client)
    pid, first, second = await _two_boards(client)
    task = await make_task(client, pid, title="Ship it", status="review", properties={})
    r = await client.post(f"/api/tasks/{task['id']}/move", json={"board_id": second["id"]})
    assert r.status_code == 200
    moved = r.json()
    assert (moved["id"], moved["board_id"], moved["status"]) == (task["id"], second["id"], "review")
    assert [
        t["id"]
        for t in (await client.get(f"/api/projects/{pid}/tasks", params={"board_id": first["id"]})).json()
    ] == []

    [event] = await _of_kind(client, pid, "task_moved")
    assert (event["kind"], event["title"], event["actor"], event["task_id"], event["board_id"]) == (
        "task_moved",
        "Ship it",
        "Ada",
        task["id"],
        second["id"],
    )
    assert event["data"]["from"]["board"] == "Tasks" and event["data"]["to"]["board"] == "QA"


async def test_a_move_lands_in_the_asked_status_at_the_asked_place(client):
    await register(client)
    pid, _, second = await _two_boards(client)
    parked = (await _add_status(client, second["id"], "Verified"))["columns"][-1]["key"]
    keep = await make_task(client, pid, board_id=second["id"], status=parked)
    task = await make_task(client, pid, status="done")
    r = await client.post(
        f"/api/tasks/{task['id']}/move",
        json={"board_id": second["id"], "status": parked, "position": keep["position"] - 1},
    )
    assert (r.json()["status"], r.json()["position"]) == (parked, keep["position"] - 1)
    bad = await client.post(
        f"/api/tasks/{task['id']}/move", json={"board_id": second["id"], "status": "custom:999"}
    )
    assert bad.status_code == 422
    running = await client.post(
        f"/api/tasks/{task['id']}/move", json={"board_id": second["id"], "status": "running"}
    )
    assert running.status_code == 422


async def test_a_custom_status_the_target_lacks_falls_back_to_the_backlog(client):
    await register(client)
    pid, first, second = await _two_boards(client)
    mine = (await _add_status(client, first["id"], "Mine"))["columns"][-1]["key"]
    task = await make_task(client, pid, status=mine)
    moved = await client.post(f"/api/tasks/{task['id']}/move", json={"board_id": second["id"]})
    assert moved.json()["status"] == "backlog"


async def test_a_queued_task_keeps_its_schedule_and_a_parked_one_is_paused(client):
    await register(client)
    pid, first, second = await _two_boards(client)
    task = await make_task(client, pid, status="ready", schedule_kind="cron", cron="0 9 * * *")
    assert task["next_run_at"]
    moved = (await client.post(f"/api/tasks/{task['id']}/move", json={"board_id": second["id"]})).json()
    assert moved["status"] == "ready" and moved["next_run_at"] == task["next_run_at"]
    parked = (
        await client.post(
            f"/api/tasks/{task['id']}/move", json={"board_id": first["id"], "status": "backlog"}
        )
    ).json()
    assert parked["next_run_at"] is None and parked["cron"] == "0 9 * * *"


async def test_a_running_task_cannot_be_moved(client, maker):
    from sqlalchemy import update

    from app.models import Task

    await register(client)
    pid, _, second = await _two_boards(client)
    task = await make_task(client, pid)
    async with maker() as s:
        await s.execute(update(Task).where(Task.id == task["id"]).values(status="running"))
        await s.commit()
    r = await client.post(f"/api/tasks/{task['id']}/move", json={"board_id": second["id"]})
    assert r.status_code == 409 and "Cancel" in r.json()["detail"]


async def test_a_task_cannot_be_sent_to_another_projects_board(client):
    await register(client)
    pid, _, _ = await _two_boards(client)
    other = await make_project(client, "Other")
    foreign = (await _workspaces(client, other["id"]))[0]["boards"][0]
    task = await make_task(client, pid)
    assert (
        await client.post(f"/api/tasks/{task['id']}/move", json={"board_id": foreign["id"]})
    ).status_code == 422
    assert (
        await client.post(f"/api/tasks/{task['id']}/spawn", json={"board_id": foreign["id"]})
    ).status_code == 422


async def test_a_follow_up_is_a_new_linked_task_and_the_original_stays(client):
    await register(client)
    pid, first, second = await _two_boards(client)
    await client.patch(
        f"/api/projects/{pid}",
        json={
            "properties": [
                {"key": "priority", "name": "Priority", "type": "select", "options": ["High", "Low"]}
            ]
        },
    )
    origin = await make_task(client, pid, title="Research", status="done", properties={"priority": "High"})

    r = await client.post(
        f"/api/tasks/{origin['id']}/spawn", json={"board_id": second["id"], "description": "Build it"}
    )
    assert r.status_code == 201
    child = r.json()
    assert child["id"] != origin["id"]
    assert (child["board_id"], child["status"], child["origin_task_id"]) == (
        second["id"],
        "backlog",
        origin["id"],
    )
    assert (child["title"], child["description"], child["properties"]) == (
        "Follow-up: Research",
        "Build it",
        {"priority": "High"},
    )
    assert child["schedule_kind"] == "none" and child["harness"] == ""

    same = (await client.get(f"/api/tasks/{origin['id']}")).json()
    assert (same["board_id"], same["status"]) == (first["id"], "done")
    [event] = await _of_kind(client, pid, "task_spawned")
    assert (event["kind"], event["task_id"]) == ("task_spawned", child["id"])
    assert event["data"]["origin"]["task_id"] == origin["id"]

    # the link survives the follow-up's move, and goes away quietly when the origin is deleted
    await client.post(f"/api/tasks/{child['id']}/move", json={"board_id": first["id"]})
    assert (await client.get(f"/api/tasks/{child['id']}")).json()["origin_task_id"] == origin["id"]
    await client.delete(f"/api/tasks/{origin['id']}")
    assert (await client.get(f"/api/tasks/{child['id']}")).json()["origin_task_id"] is None


async def test_deleting_a_task_records_where_it_was(client):
    await register(client)
    pid, first, _ = await _two_boards(client)
    task = await make_task(client, pid, title="Gone")
    await client.delete(f"/api/tasks/{task['id']}")
    [event] = await _of_kind(client, pid, "task_deleted")
    assert (event["kind"], event["board_id"], event["task_id"]) == ("task_deleted", first["id"], task["id"])


# history


async def test_the_history_records_what_happens_to_workspaces_boards_and_statuses(client):
    await register(client)
    pid = (await make_project(client))["id"]
    [main] = await _workspaces(client, pid)
    assert await _history(client, pid) == []  # a new project's own workspace and board are not events

    space = (await client.post(f"/api/projects/{pid}/workspaces", json={"name": "Ops"})).json()
    await client.patch(f"/api/workspaces/{space['id']}", json={"name": "Operations", "purpose": "Run things"})
    board = (await client.post(f"/api/workspaces/{space['id']}/boards", json={"name": "Incidents"})).json()
    await client.patch(
        f"/api/boards/{board['id']}", json={"name": "Alerts", "position": 9}
    )  # a move alone is not recorded
    parked = await _add_status(client, board["id"], "Triage")
    sid = parked["columns"][-1]["key"].removeprefix("custom:")
    await client.patch(
        f"/api/boards/{board['id']}/statuses/{sid}", json={"name": "Sorting", "color": "#112233"}
    )
    await client.delete(f"/api/boards/{board['id']}/statuses/{sid}")
    copy = (await client.post(f"/api/boards/{board['id']}/duplicate")).json()
    await client.delete(f"/api/boards/{copy['id']}")
    await client.delete(f"/api/boards/{board['id']}", params={"move_to": main["boards"][0]["id"]})
    await client.delete(f"/api/workspaces/{space['id']}")

    events = list(reversed(await _history(client, pid)))
    assert [(e["kind"], e["title"]) for e in events] == [
        ("workspace_created", "Ops"),
        ("workspace_renamed", "Operations"),
        ("board_created", "Incidents"),
        ("board_renamed", "Alerts"),
        ("status_added", "Triage"),
        ("status_renamed", "Sorting"),
        ("status_removed", "Sorting"),
        ("board_created", "Alerts copy"),
        ("board_deleted", "Alerts copy"),
        ("board_deleted", "Alerts"),
        ("workspace_deleted", "Operations"),
    ]
    assert {e["actor"] for e in events} == {"Ada"}
    assert events[1]["data"]["was"] == "Ops" and events[7]["data"]["copy_of"] == "Alerts"
    assert events[5]["data"]["board"] == "Alerts"  # a status event names its board


async def test_people_moving_a_task_between_columns_is_recorded_but_the_scheduler_is_not(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready")
    await scheduler.tick()
    await drain(scheduler)  # it ran and finished: Running and Done were the scheduler's doing
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "review"})
    await client.patch(
        f"/api/tasks/{task['id']}", json={"position": 5}
    )  # a place in the same column is not a move

    kinds = [
        (e["kind"], e["data"].get("to", {}).get("status")) for e in reversed(await _history(client, pid))
    ]
    assert kinds == [("task_created", "ready"), ("task_status", "review")]


async def test_history_can_be_looked_at_per_workspace_board_and_task(client):
    await register(client)
    pid, first, second = await _two_boards(client)
    workspace = (await _workspaces(client, pid))[0]
    other = (await client.post(f"/api/projects/{pid}/workspaces", json={"name": "Other"})).json()
    third = (await client.post(f"/api/workspaces/{other['id']}/boards", json={"name": "Far"})).json()
    a = await make_task(client, pid, title="A")
    await make_task(client, pid, title="B", board_id=second["id"])
    await client.post(f"/api/tasks/{a['id']}/move", json={"board_id": third["id"]})
    child = (await client.post(f"/api/tasks/{a['id']}/spawn", json={"board_id": second["id"]})).json()

    def titles(events):
        return sorted((e["kind"], e["title"]) for e in events)

    # the board a task left still remembers it left
    assert ("task_moved", "A") in titles(await _history(client, pid, board_id=first["id"]))
    assert ("task_moved", "A") in titles(await _history(client, pid, board_id=third["id"]))
    assert ("task_moved", "A") not in titles(await _history(client, pid, board_id=second["id"]))
    # the same goes for workspaces
    assert ("task_moved", "A") in titles(await _history(client, pid, workspace_id=workspace["id"]))
    assert ("task_moved", "A") in titles(await _history(client, pid, workspace_id=other["id"]))
    # a task's own history includes the follow-up made from it, and a follow-up's own creation
    assert ("task_spawned", "Follow-up: A") in titles(await _history(client, pid, task_id=a["id"]))
    assert titles(await _history(client, pid, task_id=child["id"])) == [("task_spawned", "Follow-up: A")]
    assert [e["title"] for e in await _history(client, pid, kind="task_created", board_id=second["id"])] == [
        "B"
    ]


async def test_history_is_paged_newest_first_and_survives_deleted_boards(client):
    await register(client)
    pid, first, second = await _two_boards(client)
    for n in range(5):
        await make_task(client, pid, title=f"T{n}")
    page = await _history(client, pid, limit=2, kind="task_created")
    assert [e["title"] for e in page] == ["T4", "T3"]
    nxt = await _history(client, pid, limit=2, kind="task_created", before=page[-1]["id"])
    assert [e["title"] for e in nxt] == ["T2", "T1"]

    await client.delete(f"/api/boards/{second['id']}")
    assert any(
        e["kind"] == "board_created" and e["title"] == "QA" for e in await _history(client, pid, limit=200)
    )
    assert first["id"]
