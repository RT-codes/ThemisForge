import base64
import json
from datetime import timedelta

from sqlalchemy import select

from app.app_settings import AppSettings
from app.cells import WritebackFilter
from app.codex import get_connection, save_auth
from app.config import settings
from app.crypto import decrypt
from app.harness import CODEX_AUTH, CodexRenderer, build_prompt, plan_for
from app.models import Attempt, AttemptStatus, utcnow
from tests.conftest import drain, make_project, make_task, register


def fake_auth(refresh: str = "R1", account: str = "acct-1") -> str:
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": {
                "id_token": "a.b.c",
                "access_token": "A1",
                "refresh_token": refresh,
                "account_id": account,
            },
            "last_refresh": "2026-10-05T12:00:00Z",
        }
    )


def ev(**kw) -> str:
    return json.dumps(kw) + "\n"


async def connect(maker, user_id: int, **kw) -> None:
    async with maker() as s:
        await save_auth(s, user_id, fake_auth(**kw), fresh=True)


async def stored_auth(maker, user_id: int) -> dict:
    async with maker() as s:
        conn = await get_connection(s, user_id)
        return json.loads(decrypt(conn.auth_encrypted))


# ----- plan and prompt -----


def test_plan_for_codex_and_placeholder():
    cfg = AppSettings(codex_image="my/codex:1")
    plan = plan_for("codex", cfg)
    assert plan and plan.image == "my/codex:1" and plan.uses_codex and plan.writeback == (CODEX_AUTH,)
    assert "codex exec" in plan.script and "--json" in plan.script and "dangerously-bypass" in plan.script
    assert "show_raw_agent_reasoning=true" in plan.script
    assert plan_for("", cfg) is None


def test_codex_uses_luna_with_high_effort_by_default():
    plan = plan_for("codex", AppSettings())
    assert "-m gpt-6-luna" in plan.script and "model_reasoning_effort=high" in plan.script
    custom = plan_for("codex", AppSettings(codex_model="gpt-6-sol", codex_reasoning_effort="low"))
    assert "-m gpt-6-sol" in custom.script and "model_reasoning_effort=low" in custom.script


def test_model_name_cannot_inject_shell():
    import pytest
    from pydantic import ValidationError

    for bad in ("x; rm -rf /", "$(id)", "a b", "-m", "`id`", "a'b"):
        with pytest.raises(ValidationError):
            AppSettings(codex_model=bad)


def test_prompt_carries_the_task():
    text = build_prompt("Fix login", "The button is dead.", {"area": "web", "empty": ""})
    assert "# Fix login" in text and "The button is dead." in text and "- area: web" in text
    assert "empty" not in text
    assert "/run/themis-secrets" in text  # the agent is told to leave credentials alone


# ----- rendering codex output -----


def test_renderer_makes_codex_events_readable():
    r = CodexRenderer()
    out = r.feed(
        ev(type="thread.started", thread_id="t-1")
        + ev(type="turn.started")
        + ev(type="item.completed", item={"type": "agent_message", "text": "On it."})
        + ev(
            type="item.started",
            item={"type": "command_execution", "command": "/bin/bash -lc \"printf 'hi' > a.txt\""},
        )
        + ev(
            type="item.completed",
            item={
                "type": "command_execution",
                "command": "x",
                "aggregated_output": "a.txt\n",
                "exit_code": 0,
            },
        )
        + ev(
            type="item.completed",
            item={"type": "command_execution", "command": "x", "aggregated_output": "", "exit_code": 2},
        )
        + ev(type="turn.completed", usage={"input_tokens": 100, "output_tokens": 7})
    )
    assert out.splitlines() == [
        "[codex] session t-1",
        "",
        "On it.",
        "",
        "$ printf 'hi' > a.txt",
        "a.txt",
        "[exit 2]",
        "",
        "[codex] done - 100 tokens in, 7 out",
    ]
    assert r.usage == {"input_tokens": 100, "output_tokens": 7}


def test_renderer_handles_split_chunks_and_non_json():
    r = CodexRenderer()
    line = ev(type="item.completed", item={"type": "agent_message", "text": "hello"})
    assert r.feed(line[:20]) == ""
    assert r.feed(line[20:] + "WARNING: something\n") == "hello\nWARNING: something\n"
    assert r.feed("tail without newline") == ""
    assert r.flush() == "tail without newline\n"


def test_renderer_unescapes_quoted_commands_and_drops_codex_noise():
    r = CodexRenderer()
    cmd = '/bin/bash -lc "printf \'hi\\\\n\' > a.txt && echo \\"x\\""'
    out = r.feed(
        "Reading additional input from stdin...\n"
        + ev(type="item.started", item={"type": "command_execution", "command": cmd})
    )
    assert out == "$ printf 'hi\\n' > a.txt && echo \"x\"\n"


def test_renderer_shows_the_agents_thinking():
    out = CodexRenderer().feed(
        ev(type="item.completed", item={"type": "reasoning", "text": "**Checking the sums**"})
    )
    assert out == "[thinking] **Checking the sums**\n"


def test_renderer_keeps_unknown_events_visible():
    out = CodexRenderer().feed(
        ev(type="item.completed", item={"type": "web_search"}) + ev(type="something.new")
    )
    assert out == "[codex] web_search\n[codex] something.new\n"


# ----- taking the refreshed login out of the output -----


def block(path: str, content: str) -> str:
    b64 = base64.b64encode(content.encode()).decode()
    return f"@@THEMIS-WRITEBACK-BEGIN {path}@@\n{b64}\n@@THEMIS-WRITEBACK-END@@\n"


def test_writeback_block_is_captured_and_never_logged():
    f = WritebackFilter((CODEX_AUTH,))
    out = f.feed("working\n" + block(CODEX_AUTH, "SECRET-LOGIN") + "after\n")
    assert out == "working\nafter\n" and f.files == {CODEX_AUTH: "SECRET-LOGIN"}


def test_writeback_survives_arbitrary_chunking():
    f = WritebackFilter((CODEX_AUTH,))
    text = "a\n" + block(CODEX_AUTH, "SECRET-LOGIN") + "b"
    out = "".join(f.feed(text[i : i + 3]) for i in range(0, len(text), 3)) + f.flush()
    assert out == "a\nb" and f.files == {CODEX_AUTH: "SECRET-LOGIN"} and "SECRET" not in out


def test_writeback_only_for_files_the_cell_was_asked_for():
    f = WritebackFilter((CODEX_AUTH,))
    f.feed(block("/etc/passwd", "x"))
    assert f.files == {}


def test_partial_output_that_is_not_a_marker_is_not_held_back():
    f = WritebackFilter((CODEX_AUTH,))
    assert f.feed("progress... ") == "progress... "


# ----- running tasks -----


async def run_one(client, scheduler, **task):
    me = await register(client)
    pid = (await make_project(client))["id"]
    t = await make_task(client, pid, status="ready", **task)
    await scheduler.tick()
    await drain(scheduler)
    attempts = (await client.get(f"/api/tasks/{t['id']}/attempts")).json()
    detail = (await client.get(f"/api/attempts/{attempts[0]['id']}")).json() if attempts else None
    return me, t, detail


async def test_harness_field_is_validated_and_editable(client):
    await register(client)
    pid = (await make_project(client))["id"]
    t = await make_task(client, pid, harness="codex")
    assert t["harness"] == "codex"
    assert (await client.patch(f"/api/tasks/{t['id']}", json={"harness": ""})).json()["harness"] == ""
    assert (
        await client.post(f"/api/projects/{pid}/tasks", json={"title": "x", "harness": "nope"})
    ).status_code == 422


async def test_codex_task_without_a_connection_fails_clearly(client, scheduler, cells):
    _, t, detail = await run_one(client, scheduler, title="agent job", harness="codex")
    assert not cells.specs
    assert "Connect it in Settings" in detail["log"]
    assert (await client.get(f"/api/tasks/{t['id']}")).json()["status"] == "failed"


async def test_placeholder_task_is_unchanged(client, scheduler, cells):
    await run_one(client, scheduler, title="plain")
    spec = cells.specs[0]
    assert spec.script is None and spec.image == "alpine:3" and not spec.secret_files and spec.writeback == ()


async def test_codex_task_gets_the_owners_login_and_a_private_workspace(client, scheduler, cells, maker):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    t = await make_task(client, pid, title="agent job", description="do it", status="ready", harness="codex")
    cells.log_text = ev(type="item.completed", item={"type": "agent_message", "text": "all done"})
    await scheduler.tick()
    await drain(scheduler)

    spec = cells.specs[0]
    assert (
        spec.image == "themisforge/cell-codex:latest"
        and spec.harness == "codex"
        and spec.owner_id == me["id"]
    )
    assert json.loads(spec.secret_files[CODEX_AUTH])["tokens"]["refresh_token"] == "R1"
    assert "codex exec" in spec.script and spec.writeback == (CODEX_AUTH,)
    assert "agent job" in (spec.cell_dir / "prompt.md").read_text()
    assert spec.workspace_dir == settings.data_dir / "projects" / str(pid) / "workspaces" / str(
        spec.attempt_id
    )
    assert "SECRET" not in repr(spec)

    log = (
        await client.get(
            f"/api/attempts/{(await client.get(f'/api/tasks/{t["id"]}/attempts')).json()[0]['id']}"
        )
    ).json()["log"]
    assert "all done" in log and '"type"' not in log  # rendered, not raw JSON
    assert (await client.get(f"/api/tasks/{t['id']}")).json()["status"] == "done"


async def test_each_attempt_has_its_own_workspace(client, scheduler, cells):
    await register(client)
    pid = (await make_project(client))["id"]
    for _ in range(2):
        await make_task(client, pid, status="ready")
    await scheduler.tick()
    await drain(scheduler)
    a, b = (s.workspace_dir for s in cells.specs)
    assert a != b and a.is_dir() and b.is_dir()


async def test_a_refreshed_login_is_written_back(client, scheduler, cells, maker):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    await make_task(client, pid, status="ready", harness="codex")
    cells.writeback = {CODEX_AUTH: fake_auth(refresh="R2")}
    await scheduler.tick()
    await drain(scheduler)
    assert (await stored_auth(maker, me["id"]))["tokens"]["refresh_token"] == "R2"


async def test_a_login_for_another_account_is_not_written_back(client, scheduler, cells, maker):
    me = await register(client)
    await connect(maker, me["id"])
    pid = (await make_project(client))["id"]
    t = await make_task(client, pid, status="ready", harness="codex")
    cells.writeback = {CODEX_AUTH: fake_auth(refresh="EVIL", account="someone-else")}
    await scheduler.tick()
    await drain(scheduler)
    assert (await stored_auth(maker, me["id"]))["tokens"]["refresh_token"] == "R1"
    attempt = (await client.get(f"/api/tasks/{t['id']}/attempts")).json()[0]
    assert "different account" in (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]


# ----- cleaning up workspaces -----


async def test_old_workspaces_are_pruned(client, scheduler, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid)
    root = settings.data_dir / "projects" / str(pid) / "workspaces"

    async with maker() as s:
        s.add_all(
            [
                Attempt(
                    task_id=task["id"],
                    status=AttemptStatus.SUCCEEDED,
                    finished_at=utcnow() - timedelta(days=10),
                ),
                Attempt(
                    task_id=task["id"],
                    status=AttemptStatus.SUCCEEDED,
                    finished_at=utcnow() - timedelta(days=1),
                ),
                Attempt(task_id=task["id"], status=AttemptStatus.RUNNING),
            ]
        )
        await s.commit()
        old, recent, running = (await s.scalars(select(Attempt).order_by(Attempt.id))).all()
    for attempt in (old, recent, running):
        (root / str(attempt.id)).mkdir(parents=True)
        (root / str(attempt.id) / "file.txt").write_text("x")
    (root / "9999").mkdir()  # its attempt does not exist any more

    assert await scheduler.prune_workspaces() == 2
    assert not (root / str(old.id)).exists() and not (root / "9999").exists()
    assert (root / str(recent.id)).exists() and (root / str(running.id)).exists()


def test_settings_defaults():
    cfg = AppSettings()
    assert cfg.keep_workspaces_days == 7 and cfg.codex_image == "themisforge/cell-codex:latest"
