"""Webhooks: an address other programs post to, to make tasks. The sender supplies a message; everything about the task
that is made is set by the project's owner."""

from sqlalchemy import select

import app.features.webhooks.receiver as webhooks
from app.persistence.models import Task, WebhookDelivery
from app.security import hash_secret
from tests.conftest import login, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_workflows import (
    edge,
    make_workflow,
    node,
    save,
    setup,
    status_trigger,
    wait_for_runs,
)

ISSUE = {
    "action": "opened",
    "issue": {
        "title": "Button is cut off",
        "number": 12,
        "body": "On mobile it overflows.",
        "user": {"login": "bo"},
    },
    "repository": {"full_name": "acme/shop"},
}


async def make_hook(client, pid: int, **body) -> dict:
    body.setdefault("name", "GitHub issues")
    r = await client.post(f"/api/projects/{pid}/webhooks", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def post(client, hook: dict, payload=None, **kwargs):
    kwargs.setdefault("json", payload if payload is not None else {})
    return await client.post(hook["path"], **kwargs)


async def tasks_of(client, pid: int) -> list[dict]:
    return (await client.get(f"/api/projects/{pid}/tasks")).json()


async def deliveries(client, hook: dict) -> list[dict]:
    return (await client.get(f"/api/webhooks/{hook['id']}/deliveries")).json()


# the address


async def test_a_message_makes_a_task_in_the_backlog_from_its_title_and_description(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    assert hook["path"].startswith("/api/hooks/") and hook["status"] == "backlog"

    r = await post(client, hook, {"title": "Make 5 sword icons", "description": "Pixel art, 32x32"})
    assert r.status_code == 201, r.text
    (task,) = await tasks_of(client, pid)
    assert (task["title"], task["description"], task["status"]) == (
        "Make 5 sword icons",
        "Pixel art, 32x32",
        "backlog",
    )
    assert r.json() == {"outcome": "created", "detail": "", "task_id": task["id"]}


async def test_the_secret_is_shown_once_and_only_a_hash_is_kept(client, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    token = hook["path"].removeprefix("/api/hooks/")

    (listed,) = (await client.get(f"/api/projects/{pid}/webhooks")).json()
    assert "path" not in listed and listed["token_hint"] == token[-6:]
    assert token not in str(listed)
    async with maker() as s:
        stored = (await s.execute(select(webhooks.Webhook.token_hash))).scalar_one()
    assert stored == hash_secret(token) and token not in stored


async def test_a_wrong_address_is_not_found_and_a_new_secret_ends_the_old_one(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    assert (await client.post("/api/hooks/not-the-secret", json={})).status_code == 404

    fresh = (await client.post(f"/api/webhooks/{hook['id']}/token")).json()
    assert fresh["path"] != hook["path"]
    assert (await post(client, hook)).status_code == 404
    assert (await post(client, fresh, {"title": "Hello"})).status_code == 201


async def test_posting_needs_no_login(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    client.cookies.clear()  # the sender is another program
    assert (await post(client, hook, {"title": "From outside"})).status_code == 201


async def test_deleting_a_webhook_ends_its_address_and_a_deleted_project_takes_it_along(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    assert (await client.delete(f"/api/webhooks/{hook['id']}")).status_code == 204
    assert (await post(client, hook)).status_code == 404
    again = await make_hook(client, pid)
    assert (await client.delete(f"/api/projects/{pid}")).status_code == 204
    assert (await post(client, again)).status_code == 404


async def test_other_users_cannot_see_or_change_a_webhook(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    await register(client, "b@c.de", "Bob")
    assert (await client.get(f"/api/projects/{pid}/webhooks")).status_code == 404
    assert (await client.patch(f"/api/webhooks/{hook['id']}", json={"name": "mine"})).status_code == 404
    assert (await client.post(f"/api/webhooks/{hook['id']}/token")).status_code == 404
    assert (await client.delete(f"/api/webhooks/{hook['id']}")).status_code == 404
    assert (await client.get(f"/api/webhooks/{hook['id']}/deliveries")).status_code == 404
    await login(client, "a@b.co")
    assert (await post(client, hook, {"title": "still works"})).status_code == 201


# what the sender cannot choose


async def test_a_message_cannot_choose_how_its_task_runs(client):
    await register(client)
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid, name="Builder")
    hook = await make_hook(client, pid, status="backlog")
    message = {
        "title": "Sneaky",
        "status": "ready",
        "agent_id": agent["id"],
        "harness": "codex",
        "schedule_kind": "cron",
        "cron": "* * * * *",
        "max_hops": 100,
        "board_id": 99,
    }
    assert (await post(client, hook, message)).status_code == 201
    (task,) = await tasks_of(client, pid)
    assert task["status"] == "backlog" and task["agent_id"] is None and task["harness"] == ""
    assert task["schedule_kind"] == "none" and task["max_hops"] is None


async def test_the_webhook_decides_where_the_task_lands_and_what_runs_it(client):
    await register(client)
    pid = (await make_project(client))["id"]
    props = [{"key": "source", "name": "Source", "type": "select", "options": ["Shop", "Form"]}]
    assert (await client.patch(f"/api/projects/{pid}", json={"properties": props})).status_code == 200
    agent = await make_agent(client, pid, name="Builder", harness="codex")
    board_id = (await client.get(f"/api/projects/{pid}/workspaces")).json()[0]["boards"][0]["id"]
    hook = await make_hook(
        client,
        pid,
        board_id=board_id,
        status="review",
        agent_id=agent["id"],
        properties={"source": "Shop"},
        review_on_success=True,
    )
    await post(client, hook, {"title": "Order 1042"})
    (task,) = await tasks_of(client, pid)
    assert (task["status"], task["board_id"], task["agent_id"]) == ("review", board_id, agent["id"])
    assert task["harness"] == "codex" and task["properties"] == {"source": "Shop"}
    assert task["review_on_success"] is True


async def test_a_webhook_can_play_workflows_as_stages(client):
    await register(client)
    pid = (await make_project(client))["id"]
    first, second = await make_workflow(client, pid, "One"), await make_workflow(client, pid, "Two")
    hook = await make_hook(client, pid, harness="workflow", workflow_ids=[first, second])
    await post(client, hook, {"title": "Go"})
    (task,) = await tasks_of(client, pid)
    assert task["harness"] == "workflow" and [s["workflow_id"] for s in task["stages"]] == [first, second]


async def test_a_webhook_is_only_saved_when_it_could_make_a_task(client):
    await register(client)
    pid = (await make_project(client))["id"]
    other = (await make_project(client, "Beta"))["id"]
    foreign_agent = await make_agent(client, other, name="Elsewhere")
    for bad in (
        {"status": "custom:99"},
        {"status": "running"},
        {"board_id": 999},
        {"agent_id": foreign_agent["id"]},
        {"harness": "workflow", "workflow_ids": []},
        {"properties": {"missing": 1}, "harness": "workflow"},
        {"name": "  "},
        {"rules": [{"path": ""}]},
    ):
        r = await client.post(f"/api/projects/{pid}/webhooks", json={"name": "x", **bad})
        assert r.status_code == 422, bad
    assert (await client.get(f"/api/projects/{pid}/webhooks")).json() == []


async def test_a_ready_webhook_task_is_started_by_the_scheduler(client, scheduler, cells):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid, status="ready")
    await post(client, hook, {"title": "Run me"})
    await scheduler.tick()
    (task,) = await tasks_of(client, pid)
    assert task["status"] in ("running", "done")


# turning a message into a task


async def test_templates_fill_the_task_from_any_message(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(
        client,
        pid,
        title_template="{{repository.full_name}}#{{issue.number}}: {{issue.title}}",
        description_template="{{issue.user.login}} wrote ({{_event}}):\n{{issue.body}}\n{{nothing.here}}!",
    )
    await client.post(hook["path"], json=ISSUE, headers={"X-GitHub-Event": "issues"})
    (task,) = await tasks_of(client, pid)
    assert task["title"] == "acme/shop#12: Button is cut off"
    assert task["description"] == "bo wrote (issues):\nOn mobile it overflows.\n!"  # a missing value is empty


async def test_a_message_without_a_title_uses_the_webhooks_name_and_keeps_everything_it_said(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid, name="Shop orders")
    await post(client, hook, {"order": 1042, "items": ["mug", "mug"]})
    (task,) = await tasks_of(client, pid)
    assert task["title"] == "Shop orders"
    assert '"order": 1042' in task["description"] and '"mug"' in task["description"]


async def test_plain_text_and_forms_work_too(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid, title_template="{{_raw}}")
    await client.post(
        hook["path"], content=b"Backup finished\nin 12s", headers={"content-type": "text/plain"}
    )
    # GitHub's default: a form whose "payload" field holds the JSON
    form_hook = await make_hook(client, pid, name="Form", title_template="{{issue.title}}")
    await client.post(form_hook["path"], data={"payload": '{"issue": {"title": "From a form"}}'})
    titles = {t["title"] for t in await tasks_of(client, pid)}
    assert titles == {"Backup finished in 12s", "From a form"}  # a title is one line


async def test_lists_and_objects_in_a_message_can_be_reached_and_read(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(
        client, pid, title_template="{{commits.1.id}}", description_template="{{head}} {{ok}} {{n}}"
    )
    await post(
        client, hook, {"commits": [{"id": "a1"}, {"id": "b2"}], "head": {"x": 1}, "ok": True, "n": 2.5}
    )
    (task,) = await tasks_of(client, pid)
    assert task["title"] == "b2" and task["description"] == '{"x": 1} true 2.5'


async def test_long_text_is_cut_to_what_a_task_holds(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    await post(client, hook, {"title": "t" * 500, "description": "d" * 30_000})
    (task,) = await tasks_of(client, pid)
    assert len(task["title"]) == 200 and len(task["description"]) == 20_000


# rules, pings, repeats


async def test_rules_decide_which_messages_make_a_task(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid, rules=[{"path": "action", "equals": ["opened", "reopened"]}])
    assert (await post(client, hook, ISSUE)).json()["outcome"] == "created"
    r = await post(client, hook, {**ISSUE, "action": "labeled"})
    assert r.status_code == 200 and r.json()["outcome"] == "skipped"
    assert "action is 'labeled'" in r.json()["detail"]
    assert len(await tasks_of(client, pid)) == 1


async def test_a_rule_without_values_only_asks_that_the_value_is_there(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(
        client, pid, rules=[{"path": "issue.title"}, {"path": "_event", "equals": ["issues"]}]
    )
    assert (await post(client, hook, {"issue": {}}, headers={"X-GitHub-Event": "issues"})).json()[
        "outcome"
    ] == "skipped"
    assert (await post(client, hook, ISSUE, headers={"X-GitHub-Event": "push"})).json()[
        "outcome"
    ] == "skipped"
    assert (await post(client, hook, ISSUE, headers={"X-GitHub-Event": "issues"})).json()[
        "outcome"
    ] == "created"


async def test_a_ping_is_answered_but_makes_no_task(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    r = await post(client, hook, {"zen": "Keep it logically awesome."}, headers={"X-GitHub-Event": "ping"})
    assert r.status_code == 200 and r.json()["outcome"] == "skipped"
    assert await tasks_of(client, pid) == []


async def test_the_same_delivery_sent_again_makes_one_task(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    sent = {"headers": {"X-GitHub-Delivery": "abc-123"}}
    assert (await post(client, hook, {"title": "Once"}, **sent)).json()["outcome"] == "created"
    again = await post(client, hook, {"title": "Once"}, **sent)
    assert again.status_code == 200 and again.json()["outcome"] == "duplicate"
    assert (
        await post(client, hook, {"title": "Another"}, headers={"X-GitHub-Delivery": "def-456"})
    ).status_code == 201
    assert len(await tasks_of(client, pid)) == 2


# safety


async def test_a_switched_off_webhook_refuses_and_says_so(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    assert (await client.patch(f"/api/webhooks/{hook['id']}", json={"enabled": False})).status_code == 200
    r = await post(client, hook, {"title": "No"})
    assert r.status_code == 409 and "switched off" in r.json()["detail"]
    assert await tasks_of(client, pid) == []
    (delivery,) = await deliveries(client, hook)
    assert delivery["outcome"] == "refused"
    await client.patch(f"/api/webhooks/{hook['id']}", json={"enabled": True})
    assert (await post(client, hook, {"title": "Yes"})).status_code == 201


async def test_a_message_that_is_too_big_is_not_read(client, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    monkeypatch.setattr(webhooks, "MAX_BODY", 100)
    assert (await post(client, hook, {"title": "x" * 500})).status_code == 413
    assert await tasks_of(client, pid) == []


async def test_a_flood_is_slowed_down_per_webhook(client, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    hook, other = await make_hook(client, pid), await make_hook(client, pid, name="Quiet")
    monkeypatch.setattr(webhooks, "RATE_LIMIT", 3)
    codes = [(await post(client, hook, {"title": f"n{i}"})).status_code for i in range(5)]
    assert codes == [201, 201, 201, 429, 429]
    assert (await post(client, hook, {"title": "n"})).headers["retry-after"] == "60"
    assert (await post(client, other, {"title": "fine"})).status_code == 201
    assert len(await tasks_of(client, pid)) == 4


async def test_a_halted_project_still_receives_and_the_task_waits(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid, status="ready")
    assert (await client.post(f"/api/projects/{pid}/halt", json={})).status_code == 200
    assert (await post(client, hook, {"title": "Held"})).status_code == 201
    await scheduler.tick()
    (task,) = await tasks_of(client, pid)
    assert task["status"] == "ready"  # nothing starts until it is resumed


# when the setup changes under it


async def test_a_deleted_board_leaves_the_webhook_refusing_until_another_is_chosen(client):
    await register(client)
    pid = (await make_project(client))["id"]
    ws = (await client.get(f"/api/projects/{pid}/workspaces")).json()[0]
    kept = ws["boards"][0]["id"]
    extra = (await client.post(f"/api/workspaces/{ws['id']}/boards", json={"name": "Extra"})).json()
    hook = await make_hook(client, pid, board_id=extra["id"])
    assert (await client.delete(f"/api/boards/{extra['id']}")).status_code == 204

    (listed,) = (await client.get(f"/api/projects/{pid}/webhooks")).json()
    assert listed["board_id"] is None and "board was deleted" in listed["problem"]
    r = await post(client, hook, {"title": "Lost"})
    assert r.status_code == 409 and await tasks_of(client, pid) == []
    fixed = await client.patch(f"/api/webhooks/{hook['id']}", json={"board_id": kept})
    assert fixed.status_code == 200 and fixed.json()["problem"] == ""
    assert (await post(client, hook, {"title": "Found"})).status_code == 201


async def test_deleting_a_custom_status_moves_the_webhook_to_where_its_tasks_went(client):
    await register(client)
    pid = (await make_project(client))["id"]
    board = (await client.get(f"/api/projects/{pid}/workspaces")).json()[0]["boards"][0]
    sid = (await client.post(f"/api/boards/{board['id']}/statuses", json={"name": "Inbox"})).json()["id"]
    hook = await make_hook(client, pid, board_id=board["id"], status=f"custom:{sid}")
    await post(client, hook, {"title": "Parked"})
    assert (await tasks_of(client, pid))[0]["status"] == f"custom:{sid}"

    assert (
        await client.delete(f"/api/boards/{board['id']}/statuses/{sid}", params={"move_to": "review"})
    ).status_code == 200
    (listed,) = (await client.get(f"/api/projects/{pid}/webhooks")).json()
    assert listed["status"] == "review" and listed["problem"] == ""


async def test_a_deleted_workflow_shows_as_a_problem_and_refuses_messages(client):
    await register(client)
    pid = (await make_project(client))["id"]
    wid = await make_workflow(client, pid)
    hook = await make_hook(client, pid, harness="workflow", workflow_ids=[wid])
    assert (await client.delete(f"/api/workflows/{wid}")).status_code == 204
    (listed,) = (await client.get(f"/api/projects/{pid}/webhooks")).json()
    assert f"Workflow {wid} does not exist" in listed["problem"]
    r = await post(client, hook, {"title": "x"})
    assert r.status_code == 422 and "does not exist" in r.json()["detail"]
    assert await tasks_of(client, pid) == []


# the log


async def test_every_message_is_logged_with_what_became_of_it_and_the_log_stays_short(client, monkeypatch):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid, rules=[{"path": "action", "equals": ["opened"]}])
    monkeypatch.setattr(webhooks, "KEEP_DELIVERIES", 3)
    await post(client, hook, ISSUE, headers={"X-GitHub-Event": "issues"})
    await post(client, hook, {"action": "labeled"})
    first = await deliveries(client, hook)
    assert [d["outcome"] for d in first] == ["skipped", "created"]  # newest first
    assert first[1]["event"] == "issues" and '"Button is cut off"' in first[1]["payload"]
    assert first[1]["task_id"] is not None
    for _ in range(4):
        await post(client, hook, {"action": "labeled"})
    assert len(await deliveries(client, hook)) == 3
    (listed,) = (await client.get(f"/api/projects/{pid}/webhooks")).json()
    assert listed["last_received_at"] is not None


async def test_the_tasks_history_names_the_webhook(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid, name="Shop")
    await post(client, hook, {"title": "Order"})
    events = (await client.get(f"/api/projects/{pid}/history")).json()
    created = next(e for e in events if e["kind"] == "task_created")
    assert created["actor"] == "Webhook Shop" and created["cause"] == f"webhook:{hook['id']}"


async def test_try_it_makes_a_real_task_from_a_message_of_your_own(client):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid, title_template="{{_event}}: {{issue.title}}")
    r = await client.post(
        f"/api/webhooks/{hook['id']}/test", json={"payload": '{"issue": {"title": "Try"}}', "event": "issues"}
    )
    assert r.status_code == 200 and r.json()["outcome"] == "created"
    assert (await tasks_of(client, pid))[0]["title"] == "issues: Try"
    bad = await client.post(f"/api/webhooks/{hook['id']}/test", json={"payload": "{nope"})
    assert bad.status_code == 422


# automation


async def test_a_webhook_task_starts_workflows_like_any_task(client, runner):
    _, pid = await setup(client)
    wid = await make_workflow(client, pid)
    await save(client, wid, [status_trigger("review"), node("e", "end")], [edge("t", "e")])
    hook = await make_hook(client, pid, status="review")
    await post(client, hook, {"title": "From outside"})
    assert len(await wait_for_runs(client, wid, 1)) == 1
    assert (await tasks_of(client, pid))[0][
        "hops"
    ] == 0  # a person-made task or a webhook's: nothing counted yet


async def test_the_task_helper_keeps_working_for_people(client):
    """The webhook receiver and the task endpoint make tasks the same way."""
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="By hand")
    assert task["status"] == "backlog"
    r = await client.post(f"/api/projects/{pid}/tasks", json={"title": "x", "status": "custom:5"})
    assert r.status_code == 422


async def test_deliveries_are_removed_with_their_webhook(client, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    hook = await make_hook(client, pid)
    await post(client, hook, {"title": "x"})
    await client.delete(f"/api/webhooks/{hook['id']}")
    async with maker() as s:
        assert (await s.scalars(select(WebhookDelivery))).all() == []
        assert len((await s.scalars(select(Task))).all()) == 1  # the task it made stays
