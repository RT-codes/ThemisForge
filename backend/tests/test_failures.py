"""Why an attempt failed: the reason on the ticket, the agent that stops and says why, and a provider that is only
briefly unable to serve a run."""

import json
from datetime import timedelta

from sqlalchemy import select

from app.execution.cells.contract import CellResult
from app.execution.harnesses.codex import CODEX_AUTH, CodexRenderer
from app.execution.harnesses.prompts import RETRY_NOTE, parse_blocked
from app.features.connections.codex import save_auth
from app.persistence.models import Attempt, Task, TaskStatus
from tests.conftest import drain, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_harness import connect, fake_auth

CAPACITY = "Selected model is at capacity. Please try a different model."


async def retry_after(client, *waits: int) -> None:
    """Sets how long a run waits before each new try (seconds), like Settings, Cell package does."""
    settings = (await client.get("/api/settings")).json()
    settings["cell_package"]["retry_waits"] = list(waits)
    assert (await client.put("/api/settings", json=settings)).status_code == 200


async def codex_task(client, maker, title: str) -> tuple[dict, dict]:
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid)
    return await make_task(client, pid, title=title, status="ready", agent_id=agent["id"]), agent


async def latest_attempt(client, task_id: int) -> dict:
    attempts = (await client.get(f"/api/tasks/{task_id}/attempts")).json()
    return (await client.get(f"/api/attempts/{attempts[0]['id']}")).json()


# ----- the harness decides what is worth another go -----


def error_event(message: str) -> str:
    return json.dumps({"type": "error", "message": message}) + "\n"


def test_codex_capacity_and_outage_errors_are_transient():
    for message in (
        CAPACITY,
        "We're currently experiencing high demand. The service is overloaded.",
        "stream disconnected before completion",
        "unexpected status 503 Service Unavailable",
    ):
        renderer = CodexRenderer()
        renderer.feed(error_event(message))
        assert renderer.transient_error == message


def test_codex_errors_that_need_a_person_are_not_retried():
    for message in (
        "You've hit your usage limit. Try again at 3:14 PM on Friday.",
        "The 'gpt-nope' model does not exist",
        "Your access token could not be refreshed",
    ):
        renderer = CodexRenderer()
        renderer.feed(error_event(message))
        assert renderer.error == message and renderer.transient_error == ""


def test_what_an_agent_writes_when_blocked_is_split_into_reason_and_fix():
    assert parse_blocked("Reason: no browser in the cell.\nFix: add one to the cell image.\n") == (
        "no browser in the cell.",
        "add one to the cell image.",
    )
    assert parse_blocked("**Reason:** the key is missing\n**Fix:** add GITHUB_TOKEN") == (
        "the key is missing",
        "add GITHUB_TOKEN",
    )
    assert parse_blocked("I could not find the repository.") == ("I could not find the repository.", "")
    reason, _ = parse_blocked("Reason: " + "x" * 5000)
    assert len(reason) == 400


# ----- a run is started again when the provider could not serve it -----


async def test_a_run_the_provider_could_not_serve_is_started_again_and_succeeds(
    client, scheduler, cells, maker
):
    task, _ = await codex_task(client, maker, "Upgrade a component")
    await retry_after(client, 0, 0, 0)
    cells.capacity_errors["Upgrade a component"] = 2

    await scheduler.tick()
    await drain(scheduler)

    assert len(cells.specs) == 3
    assert len({s.attempt_id for s in cells.specs}) == 1  # one attempt, three runs
    assert cells.specs[-1].prompt.count(RETRY_NOTE) == 1  # told it continues, once however many retries
    attempt = await latest_attempt(client, task["id"])
    assert attempt["status"] == "succeeded" and attempt["failure"] is None
    assert "Starting it again in 0 s (retry 2 of 3)" in attempt["log"] and CAPACITY in attempt["log"]
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "done"


async def test_a_provider_that_stays_unavailable_fails_with_that_reason(client, scheduler, cells, maker):
    task, _ = await codex_task(client, maker, "Upgrade a component")
    await retry_after(client, 0, 0)
    cells.capacity_errors["Upgrade a component"] = 99

    await scheduler.tick()
    await drain(scheduler)

    assert len(cells.specs) == 3  # the first run and two more, as many as there are waits
    attempt = await latest_attempt(client, task["id"])
    failure = attempt["failure"]
    assert attempt["status"] == "failed" and failure["source"] == "themis"
    assert CAPACITY in failure["reason"] and "also after 2 more tries" in failure["reason"]
    assert "another model" in failure["action"]
    assert CAPACITY in failure["tail"]  # the last lines of the log, for the ticket
    shown = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert shown["status"] == "failed" and shown["last_failure_reason"] == failure["reason"]


async def test_a_program_that_is_not_a_codex_run_is_never_started_again(client, scheduler, cells):
    await register(client)
    await retry_after(client, 0, 0, 0)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="will fail", status="ready")

    await scheduler.tick()
    await drain(scheduler)

    assert len(cells.specs) == 1
    failure = (await latest_attempt(client, task["id"]))["failure"]
    assert "exit code 1" in failure["reason"] and "simulated failure" in failure["tail"]


# ----- an agent that stops and says why -----


async def test_an_agent_that_writes_why_it_is_blocked_fails_the_attempt_with_its_words(
    client, scheduler, cells, maker
):
    task, _ = await codex_task(client, maker, "Take screenshots")
    cells.blocked["Take screenshots"] = (
        "Reason: Chromium cannot start, the cell has no libglib or libnss3.\n"
        "Fix: use a cell image that includes the browser libraries.\n"
    )

    await scheduler.tick()
    await drain(scheduler)

    attempt = await latest_attempt(client, task["id"])
    assert attempt["status"] == "failed" and attempt["exit_code"] == 0  # the program itself ended well
    assert attempt["failure"]["source"] == "agent"
    assert attempt["failure"]["reason"] == "Chromium cannot start, the cell has no libglib or libnss3."
    assert attempt["failure"]["action"] == "use a cell image that includes the browser libraries."
    assert "finished" in attempt["result"]  # what it did say is kept
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "failed"


async def test_every_codex_run_is_told_how_to_stop(client, scheduler, cells, maker):
    await codex_task(client, maker, "Anything")
    await scheduler.tick()
    await drain(scheduler)
    assert "/cell/blocked.md" in cells.specs[0].prompt


# ----- the other ways to fail say so too -----


async def test_a_restart_gives_the_attempt_it_cut_short_a_reason(client, scheduler, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="one-off", status="ready")
    async with maker() as s:
        row = await s.get(Task, task["id"])
        row.status = TaskStatus.RUNNING
        s.add(Attempt(task_id=row.id))
        await s.commit()

    await scheduler.reconcile()

    async with maker() as s:
        failure = (await s.scalars(select(Attempt))).one().failure
    assert failure["reason"] == "Themis restarted while this attempt was running."
    assert "Run now" in failure["action"]


async def test_a_task_that_could_not_start_says_why(client, scheduler):
    await register(client)
    await client.put("/api/settings", json={"cell_cpus": 4, "budget": {"cpus": 2, "memory_mb": 2048}})
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="too big", status="ready")

    assert await scheduler.tick() == 0

    shown = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert "more than the whole resource budget" in shown["last_failure_reason"]


async def test_no_retries_when_the_waits_are_empty(client, scheduler, cells, maker):
    task, _ = await codex_task(client, maker, "Upgrade a component")
    await retry_after(client)
    cells.capacity_errors["Upgrade a component"] = 1

    await scheduler.tick()
    await drain(scheduler)

    assert len(cells.specs) == 1
    attempt = await latest_attempt(client, task["id"])
    assert attempt["status"] == "failed" and "more tr" not in attempt["failure"]["reason"]


# ----- a login another run already refreshed -----

REUSED = (
    "Your access token could not be refreshed because your refresh token was already used. "
    "Please log out and sign in again."
)


def test_a_used_up_refresh_token_is_a_rejected_login_not_a_provider_blip():
    renderer = CodexRenderer()
    renderer.feed(error_event(REUSED))
    assert renderer.login_rejected and renderer.transient_error == ""


async def rejecting_first_run(cells, seen: list[str], before_error=None) -> None:
    """The first cell Codex starts has its login refused; later cells run as usual."""
    original = cells.run

    async def run(spec, on_log):
        seen.append(spec.secret_files[CODEX_AUTH])
        if len(seen) == 1:
            if before_error is not None:
                await before_error()
            await on_log(error_event(REUSED))
            return CellResult(exit_code=1)
        return await original(spec, on_log)

    cells.run = run


async def test_a_refused_login_is_swapped_for_the_newer_stored_one_and_tried_again(
    client, scheduler, cells, maker
):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    agent = await make_agent(client, pid)
    task = await make_task(client, pid, title="Parallel branch", status="ready", agent_id=agent["id"])

    async def another_run_refreshed_first() -> None:
        async with maker() as session:
            await save_auth(session, me["id"], fake_auth(refresh="R2", age=-timedelta(minutes=1)))

    seen: list[str] = []
    await rejecting_first_run(cells, seen, another_run_refreshed_first)
    await scheduler.tick()
    await drain(scheduler)
    assert len(seen) == 2 and '"R1"' in seen[0] and '"R2"' in seen[1]
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "done"
    assert "Another run refreshed the Codex login first" in (await latest_attempt(client, task["id"]))["log"]


async def test_a_login_that_is_refused_and_has_no_newer_one_fails_and_says_to_reconnect(
    client, scheduler, cells, maker
):
    task, _ = await codex_task(client, maker, "Dead login")
    seen: list[str] = []
    await rejecting_first_run(cells, seen)
    await scheduler.tick()
    await drain(scheduler)
    assert len(seen) == 1  # nothing newer to try, so no second go
    attempt = await latest_attempt(client, task["id"])
    assert attempt["failure"]["source"] == "themis"
    assert "refused the saved login" in attempt["failure"]["reason"]
    assert "Connect Codex again" in attempt["failure"]["action"]
