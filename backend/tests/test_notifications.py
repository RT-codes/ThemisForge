"""Notifications out: a project's targets hear about failures, reviews, approvals and finished tasks. The service
itself (Discord) is replaced by a recorder; what matters here is who is told what, and that a broken chat never
touches the work."""

import asyncio

import pytest

import app.features.notifications.delivery as notifications
from app.persistence.models import Task
from tests.conftest import drain, login, make_project, make_task, register
from tests.test_approvals import gated, open_approvals, start
from tests.test_workflows import setup

DISCORD = "https://discord.com/api/webhooks/123456/abc_DEF-ghi"


@pytest.fixture
def sent(monkeypatch) -> list[tuple[str, dict]]:
    """Every message that would have gone out, as (address, payload)."""
    calls: list[tuple[str, dict]] = []

    async def record(url: str, payload: dict) -> None:
        calls.append((url, payload))

    monkeypatch.setattr(notifications, "_post", record)
    return calls


async def heard(sent: list, count: int) -> None:
    """Wait until `count` messages went out: they are sent in the background, so a test must not look too early."""
    async with asyncio.timeout(10):
        while len(sent) < count:
            await asyncio.gather(*notifications.pending)
            await asyncio.sleep(0.01)


async def quiet() -> None:
    await asyncio.gather(*notifications.pending)


async def make_target(client, pid: int, **body) -> dict:
    body.setdefault("name", "My phone")
    body.setdefault("kind", "discord")
    body.setdefault("config", {"url": DISCORD})
    r = await client.post(f"/api/projects/{pid}/notifications", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# setting up


async def test_the_options_list_the_services_and_events(client):
    await register(client)
    options = (await client.get("/api/notification-options")).json()
    [discord] = options["kinds"]
    assert discord["key"] == "discord" and [f["name"] for f in discord["fields"]] == ["url"]
    assert {e["key"] for e in options["events"]} == {"failed", "attention", "done"}


async def test_a_target_never_gives_its_secret_back(client, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    target = await make_target(client, pid)
    assert target["hint"].endswith("ghi") and target["events"] == ["failed", "attention"]
    assert DISCORD not in str((await client.get(f"/api/projects/{pid}/notifications")).json())
    async with maker() as s:
        row = await s.get(notifications.NotificationTarget, target["id"])
    assert DISCORD not in row.config_encrypted  # stored encrypted


@pytest.mark.parametrize(
    "body",
    [
        {"config": {"url": "https://evil.example.com/api/webhooks/1/x"}},
        {"config": {"url": "http://discord.com/api/webhooks/1/x"}},
        {"config": {}},
        {"kind": "carrier-pigeon"},
        {"events": ["exploded"]},
    ],
)
async def test_a_target_that_could_not_work_is_refused(client, body):
    await register(client)
    pid = (await make_project(client))["id"]
    r = await client.post(
        f"/api/projects/{pid}/notifications",
        json={"name": "x", "kind": "discord", "config": {"url": DISCORD}, **body},
    )
    assert r.status_code == 422


async def test_a_target_can_be_changed_and_removed(client):
    await register(client)
    pid = (await make_project(client))["id"]
    target = await make_target(client, pid)
    other = "https://discord.com/api/webhooks/9/zzzzzz"
    r = await client.patch(
        f"/api/notifications/{target['id']}",
        json={"name": "Laptop", "events": ["done", "failed"], "config": {"url": other}, "enabled": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Laptop" and body["events"] == ["failed", "done"]
    assert not body["enabled"] and body["hint"].endswith("zzzzzz")
    bad = await client.patch(f"/api/notifications/{target['id']}", json={"config": {"url": "nope"}})
    assert bad.status_code == 422
    assert (await client.delete(f"/api/notifications/{target['id']}")).status_code == 204
    assert (await client.get(f"/api/projects/{pid}/notifications")).json() == []


async def test_only_the_owner_reaches_a_target(client):
    await register(client)
    pid = (await make_project(client))["id"]
    target = await make_target(client, pid)
    await register(client, "b@c.de", "Bob")
    assert (await client.get(f"/api/projects/{pid}/notifications")).status_code == 404
    assert (
        await client.post(
            f"/api/projects/{pid}/notifications",
            json={"name": "x", "kind": "discord", "config": {"url": DISCORD}},
        )
    ).status_code == 404
    assert (
        await client.patch(f"/api/notifications/{target['id']}", json={"name": "mine"})
    ).status_code == 404
    assert (await client.post(f"/api/notifications/{target['id']}/test")).status_code == 404
    assert (await client.delete(f"/api/notifications/{target['id']}")).status_code == 404
    await login(client, "a@b.co")
    assert len((await client.get(f"/api/projects/{pid}/notifications")).json()) == 1


# what is told


async def test_a_failed_task_is_told_to_the_channel(client, scheduler, sent):
    await register(client)
    pid = (await make_project(client, "Shop"))["id"]
    await make_target(client, pid)
    await make_task(client, pid, title="Sync will fail", status="ready")
    await scheduler.tick()
    await drain(scheduler)
    await heard(sent, 1)
    [(url, payload)] = sent
    assert url == DISCORD
    assert (
        "Failed" in payload["content"]
        and "Shop" in payload["content"]
        and "Sync will fail" in payload["content"]
    )
    assert payload["allowed_mentions"] == {"parse": []}  # a title that says @everyone pings nobody


async def test_a_task_in_review_needs_attention(client, scheduler, sent):
    await register(client)
    pid = (await make_project(client))["id"]
    await make_target(client, pid)
    await make_task(client, pid, title="Listing", status="ready", review_on_success=True)
    await scheduler.tick()
    await drain(scheduler)
    await heard(sent, 1)
    assert "Needs your attention" in sent[0][1]["content"] and "Listing" in sent[0][1]["content"]


async def test_a_finished_task_is_told_only_to_those_who_asked(client, scheduler, sent):
    await register(client)
    pid = (await make_project(client))["id"]
    await make_target(client, pid, name="quiet")  # failed and attention only
    await make_target(
        client,
        pid,
        name="chatty",
        config={"url": "https://discord.com/api/webhooks/2/other"},
        events=["done"],
    )
    await make_task(client, pid, title="Report", status="ready")
    await scheduler.tick()
    await drain(scheduler)
    await heard(sent, 1)
    await quiet()
    [(url, payload)] = sent
    assert url.endswith("/2/other") and "Done" in payload["content"]


async def test_a_switched_off_target_hears_nothing(client, scheduler, sent):
    await register(client)
    pid = (await make_project(client))["id"]
    await make_target(client, pid, enabled=False)
    await make_task(client, pid, title="Will fail", status="ready")
    await scheduler.tick()
    await drain(scheduler)
    await quiet()
    assert sent == []


async def test_the_same_failure_is_not_repeated_within_minutes(client, scheduler, sent):
    await register(client)
    pid = (await make_project(client))["id"]
    await make_target(client, pid)
    task = await make_task(client, pid, title="Will fail", status="ready")
    for _ in range(2):
        await scheduler.tick()
        await drain(scheduler)
        await client.post(f"/api/tasks/{task['id']}/run")
    await quiet()
    assert len(sent) == 1


async def test_a_step_of_a_workflow_does_not_speak_for_itself(client, scheduler, maker, sent):
    """Steps are internal tasks: the task that plays the workflow is the one that is told about."""
    await register(client)
    pid = (await make_project(client))["id"]
    await make_target(client, pid)
    task = await make_task(client, pid, title="Will fail", status="ready")
    async with maker() as s:
        (await s.get(Task, task["id"])).internal = True
        await s.commit()
    await scheduler.tick()
    await drain(scheduler)
    await quiet()
    assert sent == []


async def test_a_run_waiting_for_approval_needs_attention(client, runner, sent):
    _, pid = await setup(client)
    await make_target(client, pid)
    await start(client, pid, *gated("Publish this listing?"))
    await open_approvals(client)
    await heard(sent, 1)
    content = sent[0][1]["content"]
    assert "Needs your attention" in content and "Publish this listing?" in content and "Flow" in content


# a broken chat


async def test_a_chat_that_is_down_does_not_stop_the_work_and_is_reported(client, scheduler, monkeypatch):
    async def down(url: str, payload: dict) -> None:
        raise notifications.NotifyError("It answered with status 404")

    monkeypatch.setattr(notifications, "_post", down)
    await register(client)
    pid = (await make_project(client))["id"]
    target = await make_target(client, pid)
    task = await make_task(client, pid, title="Will fail", status="ready")
    await scheduler.tick()
    await drain(scheduler)
    await quiet()
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "failed"
    [listed] = (await client.get(f"/api/projects/{pid}/notifications")).json()
    assert listed["id"] == target["id"] and listed["last_error"] == "It answered with status 404"
    assert listed["last_sent_at"] is None


async def test_the_test_button_sends_even_when_switched_off_and_says_how_it_went(client, sent, monkeypatch):
    await register(client)
    pid = (await make_project(client, "Shop"))["id"]
    target = await make_target(client, pid, enabled=False)
    r = await client.post(f"/api/notifications/{target['id']}/test")
    assert r.json() == {"ok": True, "detail": ""}
    assert "Test" in sent[0][1]["content"] and "Shop" in sent[0][1]["content"]
    [listed] = (await client.get(f"/api/projects/{pid}/notifications")).json()
    assert listed["last_sent_at"] is not None and listed["last_error"] == ""

    async def down(url: str, payload: dict) -> None:
        raise notifications.NotifyError("Could not reach it (ConnectError)")

    monkeypatch.setattr(notifications, "_post", down)
    r = await client.post(f"/api/notifications/{target['id']}/test")
    assert r.json() == {"ok": False, "detail": "Could not reach it (ConnectError)"}
    [listed] = (await client.get(f"/api/projects/{pid}/notifications")).json()
    assert listed["last_error"] == "Could not reach it (ConnectError)"
