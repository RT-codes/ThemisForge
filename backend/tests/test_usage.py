"""What an attempt used is kept as the harness reported it: which harness and model, and the tokens spent."""

import json

from app.execution.harnesses.codex import CodexRenderer
from app.execution.harnesses.types import TokenUsage
from tests.conftest import drain, make_project, make_task, register
from tests.test_agents import make_agent
from tests.test_failures import latest_attempt, retry_after
from tests.test_harness import connect

SPENT = {
    "input_tokens": 1200,
    "cached_input_tokens": 1000,
    "output_tokens": 80,
    "reasoning_output_tokens": 30,
}


async def codex_task(client, maker, title: str, **agent) -> dict:
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    made = await make_agent(client, pid, **agent)
    return await make_task(client, pid, title=title, status="ready", agent_id=made["id"])


def turn(usage: dict) -> str:
    return json.dumps({"type": "turn.completed", "usage": usage}) + "\n"


# ----- reading the report -----


def test_the_renderer_reads_every_count_and_ignores_what_it_does_not_know():
    r = CodexRenderer()
    assert r.usage is None  # nothing is known until the harness reports
    r.feed(turn({**SPENT, "something_new": 5, "total_tokens": "many"}))
    assert r.usage == TokenUsage(1200, 1000, 80, 30)


def test_a_later_report_replaces_an_earlier_one_in_the_same_run():
    r = CodexRenderer()
    r.feed(turn({"input_tokens": 10, "output_tokens": 1}) + turn({"input_tokens": 25, "output_tokens": 4}))
    assert r.usage == TokenUsage(
        input_tokens=25, output_tokens=4
    )  # the thread's total so far, not a second run


def test_usage_adds_up_field_by_field():
    assert TokenUsage(1, 2, 3, 4) + TokenUsage(10, 20, 30, 40) == TokenUsage(11, 22, 33, 44)


# ----- keeping it on the attempt -----


async def test_an_attempt_keeps_the_harness_the_model_and_the_tokens_it_spent(
    client, scheduler, cells, maker
):
    task = await codex_task(client, maker, "Summarise the week", model="gpt-5-mini")
    cells.usage["Summarise the week"] = SPENT

    await scheduler.tick()
    await drain(scheduler)

    attempt = await latest_attempt(client, task["id"])
    assert (attempt["harness"], attempt["model"], attempt["billing"]) == (
        "codex",
        "gpt-5-mini",
        "subscription",
    )
    assert {k: attempt[k] for k in SPENT} == SPENT


async def test_an_agent_without_a_model_is_recorded_under_the_model_it_really_got(
    client, scheduler, cells, maker
):
    task = await codex_task(client, maker, "Summarise the week")
    settings = (await client.get("/api/settings")).json()

    await scheduler.tick()
    await drain(scheduler)

    attempt = await latest_attempt(client, task["id"])
    assert attempt["model"] == settings["codex_model"] != ""  # never the empty "use the default"


async def test_runs_that_were_started_again_are_all_counted(client, scheduler, cells, maker):
    task = await codex_task(client, maker, "Upgrade a component")
    await retry_after(client, 0, 0)
    cells.capacity_errors["Upgrade a component"] = 2  # two runs end in trouble, the third works
    cells.usage["Upgrade a component"] = {"input_tokens": 100, "output_tokens": 10}

    await scheduler.tick()
    await drain(scheduler)

    attempt = await latest_attempt(client, task["id"])
    assert len(cells.specs) == 3 and attempt["status"] == "succeeded"
    assert (attempt["input_tokens"], attempt["output_tokens"]) == (300, 30)  # the provider billed all three


async def test_a_failed_attempt_still_keeps_what_it_spent(client, scheduler, cells, maker):
    task = await codex_task(client, maker, "This will fail")
    cells.usage["This will fail"] = SPENT

    await scheduler.tick()
    await drain(scheduler)

    attempt = await latest_attempt(client, task["id"])
    assert attempt["status"] == "failed" and attempt["input_tokens"] == 1200


async def test_a_harness_that_reported_nothing_leaves_the_counts_empty_not_zero(
    client, scheduler, cells, maker
):
    task = await codex_task(client, maker, "Quiet one")

    await scheduler.tick()
    await drain(scheduler)

    attempt = await latest_attempt(client, task["id"])
    assert attempt["harness"] == "codex"  # it did run on Codex...
    assert attempt["input_tokens"] is None and attempt["output_tokens"] is None  # ...but nothing was reported


async def test_the_placeholder_program_has_no_usage_at_all(client, scheduler, cells):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="No agent", status="ready")

    await scheduler.tick()
    await drain(scheduler)

    attempt = await latest_attempt(client, task["id"])
    assert all(
        attempt[k] is None
        for k in ("harness", "model", "billing", "input_tokens", "cached_input_tokens", "output_tokens")
    )
