import asyncio
import base64
import glob
import io
import json
import os
import sys
import tarfile
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.cells import SECRETS_DIR, CellError, CellSpec, DockerCellManager, secrets_archive
from app.codex import CodexError, CodexLogins, get_connection, lease_codex, login_needs_refresh, save_auth
from app.config import settings
from app.crypto import decrypt
from app.main import app
from app.models import CodexConnection, utcnow
from tests.conftest import login, register
from tests.test_harness import fake_auth

FAKE = Path(__file__).parent / "fake_codex.py"


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    """Point THEMIS_CODEX_BIN at a shim that runs fake_codex.py (works on Linux and Windows)."""
    if os.name == "nt":
        shim = tmp_path / "codex.cmd"
        shim.write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n')
    else:
        shim = tmp_path / "codex"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        shim.chmod(0o755)
    monkeypatch.setattr(settings, "codex_bin", str(shim))
    monkeypatch.setattr(
        settings, "codex_login", "host"
    )  # these tests sign in with the stand-in CLI on this machine

    def mode(name: str) -> None:
        monkeypatch.setenv("FAKE_CODEX_MODE", name)

    mode("ok")
    return mode


@pytest.fixture(autouse=True)
def secure_key(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "a-real-secret-key-for-tests-0123456789")


@pytest.fixture(autouse=True)
async def logins(maker):
    app.state.codex_logins = CodexLogins(maker)
    yield app.state.codex_logins
    await app.state.codex_logins.shutdown()


async def wait_for(client, status: str, timeout: float = 10) -> dict:
    async with asyncio.timeout(timeout):
        while (body := (await client.get("/api/codex")).json())["login"]["status"] != status:
            await asyncio.sleep(0.05)
    return body


async def test_not_connected_by_default(client, fake_codex):
    await register(client)
    body = (await client.get("/api/codex")).json()
    assert body["can_sign_in"] and body["sign_in_problem"] == "" and body["secret_key_secure"]
    assert not body["connected"] and not body["needs_reconnect"] and body["login"] is None


async def test_requires_login(client):
    assert (await client.get("/api/codex")).status_code == 401
    assert (await client.post("/api/codex/login")).status_code == 401


async def test_refuses_with_the_insecure_default_key(client, fake_codex, monkeypatch):
    from app.config import DEFAULT_SECRET_KEY

    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)
    await register(client)
    r = await client.post("/api/codex/login")
    assert r.status_code == 409 and "THEMIS_SECRET_KEY" in r.json()["detail"]


async def test_cli_missing(client, monkeypatch):
    monkeypatch.setattr(settings, "codex_bin", "definitely-not-installed-codex")
    monkeypatch.setattr(settings, "codex_login", "host")
    await register(client)
    status = (await client.get("/api/codex")).json()
    assert not status["can_sign_in"] and "not found" in status["sign_in_problem"]
    r = await client.post("/api/codex/login")
    assert r.status_code == 503 and "not found" in r.json()["detail"]


async def test_device_sign_in_stores_an_encrypted_login(client, maker, fake_codex):
    await register(client)
    before = set(glob.glob(os.path.join(tempfile.gettempdir(), "themis-codex-*")))

    r = await client.post("/api/codex/login")
    assert r.status_code == 201
    assert r.json()["status"] == "waiting"
    assert r.json()["verification_url"] == "https://auth.example.test/codex/device"
    assert r.json()["code"] == "ABCD-12345"

    body = await wait_for(client, "connected")
    assert body["connected"] and body["account"] == "ada@example.test"
    assert body["refreshed_at"] is not None

    # nothing sensitive in any API response, and the stored value is ciphertext
    assert "TOKEN-SECRET" not in (await client.get("/api/codex")).text
    async with maker() as s:
        conn = (await s.scalars(select(CodexConnection))).one()
    assert "TOKEN-SECRET" not in conn.auth_encrypted and "ada@example.test" not in conn.auth_encrypted
    # the throwaway CODEX_HOME is gone
    assert set(glob.glob(os.path.join(tempfile.gettempdir(), "themis-codex-*"))) == before


async def test_failed_sign_in(client, fake_codex):
    fake_codex("fail")
    await register(client)
    await client.post("/api/codex/login")
    body = await wait_for(client, "failed")
    assert not body["connected"] and "did not finish" in body["login"]["error"]


async def test_cancel_sign_in(client, fake_codex):
    fake_codex("hang")
    await register(client)
    assert (await client.post("/api/codex/login")).json()["status"] == "waiting"
    assert (await client.delete("/api/codex/login")).status_code == 204
    assert (await client.get("/api/codex")).json()["login"]["status"] == "cancelled"


async def test_each_user_has_their_own_connection(client, fake_codex):
    await register(client, "admin@b.co", "Admin")
    await register(client, "ada@b.co", "Ada")
    await client.post("/api/codex/login")
    await wait_for(client, "connected")
    await login(client, "admin@b.co")  # even an administrator sees only their own
    assert not (await client.get("/api/codex")).json()["connected"]
    await login(client, "ada@b.co")
    assert (await client.get("/api/codex")).json()["connected"]


async def test_disconnect(client, fake_codex):
    await register(client)
    await client.post("/api/codex/login")
    await wait_for(client, "connected")
    assert (await client.delete("/api/codex")).status_code == 204
    assert not (await client.get("/api/codex")).json()["connected"]


async def test_login_unreadable_after_the_secret_key_changes(client, fake_codex, monkeypatch):
    await register(client)
    await client.post("/api/codex/login")
    await wait_for(client, "connected")
    monkeypatch.setattr(settings, "secret_key", "a-different-secret-key-0123456789abcdef")
    await login(client, "a@b.co")  # sessions are signed with the same key
    body = (await client.get("/api/codex")).json()
    assert not body["connected"] and body["needs_reconnect"]


def refreshed(auth_json: str, marker: str = "ROTATED", minutes: int = 1) -> str:
    """What Codex writes after a refresh: new tokens and a later last_refresh."""
    data = json.loads(auth_json)
    data["tokens"]["refresh_token"] = marker
    data["last_refresh"] = (utcnow() + timedelta(minutes=minutes)).isoformat()
    return json.dumps(data)


async def test_lease_takes_turns_by_default_and_writes_refreshed_logins_back(client, maker, fake_codex):
    me = await register(client)
    await client.post("/api/codex/login")
    await wait_for(client, "connected")

    order: list[str] = []

    async def use(tag: str) -> None:
        async with lease_codex(maker, me["id"]) as lease:
            order.append(f"{tag}:start")
            assert "REFRESH-TOKEN-SECRET" in lease.auth_json or "ROTATED" in lease.auth_json
            await asyncio.sleep(0.05)
            assert await lease.save_back(refreshed(lease.auth_json))
            order.append(f"{tag}:end")

    await asyncio.gather(use("a"), use("b"))
    assert order in (["a:start", "a:end", "b:start", "b:end"], ["b:start", "b:end", "a:start", "a:end"])
    async with lease_codex(maker, me["id"]) as lease:
        assert "ROTATED" in lease.auth_json


async def connect_with(maker, user_id: int, **kw) -> None:
    async with maker() as session:
        await save_auth(session, user_id, fake_auth(**kw), fresh=True)


class Overlap:
    """Runs leases at once and records how many held the login at the same moment."""

    def __init__(self, maker, user_id: int, **lease_kw) -> None:
        self.maker, self.user_id, self.lease_kw = maker, user_id, lease_kw
        self.now = self.peak = 0

    async def use(self, hold: float = 0.05, then=None) -> None:
        async with lease_codex(self.maker, self.user_id, **self.lease_kw) as lease:
            self.now += 1
            self.peak = max(self.peak, self.now)
            await asyncio.sleep(hold)
            if then is not None:
                await then(lease)
            self.now -= 1


async def test_runs_share_a_fresh_login_up_to_the_limit(client, maker):
    me = await register(client)
    await connect_with(maker, me["id"])
    seen = Overlap(maker, me["id"], max_parallel=3)
    await asyncio.gather(*(seen.use() for _ in range(5)))
    assert seen.peak == 3  # five wanted it, the limit let three through at a time


async def test_a_login_due_for_refresh_is_used_by_one_run_at_a_time(client, maker):
    me = await register(client)
    await connect_with(maker, me["id"], age=timedelta(days=9))  # Codex would refresh it as soon as it starts
    seen = Overlap(maker, me["id"], max_parallel=3)
    await asyncio.gather(*(seen.use() for _ in range(3)))
    assert seen.peak == 1


async def test_after_the_refreshing_run_the_others_share_again(client, maker):
    me = await register(client)
    await connect_with(maker, me["id"], age=timedelta(days=9))
    seen = Overlap(maker, me["id"], max_parallel=3)

    async def refresh(lease) -> None:
        assert await lease.save_back(refreshed(lease.auth_json))

    # the first to arrive refreshes alone; the three that were waiting then find a fresh login and run together
    first = asyncio.create_task(seen.use(0.1, refresh))
    await asyncio.sleep(0.02)
    await asyncio.gather(first, *(seen.use() for _ in range(3)))
    assert seen.peak == 3


async def test_a_stale_login_never_replaces_a_newer_one(client, maker):
    me = await register(client)
    await connect_with(maker, me["id"])
    async with lease_codex(maker, me["id"], max_parallel=2) as slow:
        async with lease_codex(maker, me["id"], max_parallel=2) as quick:
            assert await quick.save_back(refreshed(quick.auth_json, "NEWER", minutes=2))
        # the slow run began before that refresh, and still holds the login whose refresh token is now used up
        assert not await slow.save_back(refreshed(slow.auth_json, "OLDER", minutes=1))
        assert "NEWER" in slow.auth_json  # it carries on with (and retries with) the login that works
    async with maker() as session:
        conn = await get_connection(session, me["id"])
        stored = json.loads(decrypt(conn.auth_encrypted))
    assert stored["tokens"]["refresh_token"] == "NEWER"


def jwt(**claims) -> str:
    part = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{part({'alg': 'none'})}.{part(claims)}.sig"


def test_login_needs_refresh_looks_at_its_age_and_its_access_token():
    now = utcnow()
    auth = lambda **kw: json.loads(fake_auth(**kw))
    assert not login_needs_refresh(auth(), 3600, now)
    assert login_needs_refresh(auth(age=timedelta(days=7, hours=23)), 3600, now)  # would turn 8 days mid-run
    assert not login_needs_refresh(auth(age=timedelta(days=7)), 3600, now)
    fresh = auth()
    fresh["tokens"]["access_token"] = jwt(exp=(now + timedelta(minutes=30)).timestamp())
    assert login_needs_refresh(fresh, 3600, now)  # the token ends before the run could
    fresh["tokens"]["access_token"] = jwt(exp=(now + timedelta(days=5)).timestamp())
    assert not login_needs_refresh(fresh, 3600, now)
    unknown = auth()
    del unknown["last_refresh"]
    assert login_needs_refresh(unknown, 3600, now)  # not knowing counts as due


async def test_lease_needs_a_connection(maker, client):
    me = await register(client)
    with pytest.raises(CodexError):
        async with lease_codex(maker, me["id"]):
            pass


async def test_save_back_rejects_a_non_chatgpt_login(client, maker, fake_codex):
    me = await register(client)
    await client.post("/api/codex/login")
    await wait_for(client, "connected")
    async with lease_codex(maker, me["id"]) as lease:
        with pytest.raises(CodexError):
            await lease.save_back('{"OPENAI_API_KEY": "sk-whatever"}')


# ----- handing the login to a cell -----


def spec(**kw) -> CellSpec:
    return CellSpec(
        attempt_id=1, task_id=1, project_id=1, title="t", description="", properties={},
        image="alpine:3", cpus=1, memory_mb=64, timeout_seconds=10, **kw,
    )  # fmt: skip


def test_secrets_archive_is_owner_only_and_stays_under_the_secrets_dir():
    path = f"{SECRETS_DIR}/codex/auth.json"
    with tarfile.open(fileobj=io.BytesIO(secrets_archive({path: "TOP-SECRET"}, 1000, 1000))) as tar:
        member = tar.getmember(path.lstrip("/"))
        assert member.mode == 0o600 and member.uid == 1000
        assert tar.extractfile(member).read() == b"TOP-SECRET"
    for bad in ("/etc/passwd", f"{SECRETS_DIR}/../etc/passwd", "relative/auth.json"):
        with pytest.raises(CellError):
            secrets_archive({bad: "x"})


def test_docker_args_never_contain_the_secret():
    args = DockerCellManager().build_args(spec(secret_files={f"{SECRETS_DIR}/codex/auth.json": "TOP-SECRET"}))
    assert not any("TOP-SECRET" in a for a in args)
    assert "-i" in args and any(a.startswith(f"{SECRETS_DIR}:") and "noexec" in a for a in args)
    plain = DockerCellManager().build_args(spec())
    assert "-i" not in plain and not any(SECRETS_DIR in a for a in plain)


def test_docker_args_work_without_unix_user_ids(monkeypatch):
    """Windows has no os.getuid: cells must still start (as the image's default user)."""
    monkeypatch.delattr(os, "getuid", raising=False)  # already missing on Windows
    args = DockerCellManager().build_args(spec(secret_files={f"{SECRETS_DIR}/codex/auth.json": "x"}))
    assert "--user" not in args and not any("uid=" in a for a in args)
