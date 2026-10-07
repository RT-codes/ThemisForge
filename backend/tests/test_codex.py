import asyncio
import glob
import io
import os
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.cells import SECRETS_DIR, CellError, CellSpec, DockerCellManager, secrets_archive
from app.codex import CodexError, CodexLogins, lease_codex
from app.config import settings
from app.main import app
from app.models import CodexConnection
from tests.conftest import login, register

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


async def test_lease_serialises_use_and_writes_refreshed_logins_back(client, maker, fake_codex):
    me = await register(client)
    await client.post("/api/codex/login")
    await wait_for(client, "connected")

    order: list[str] = []

    async def use(tag: str) -> None:
        async with lease_codex(maker, me["id"]) as lease:
            order.append(f"{tag}:start")
            assert "REFRESH-TOKEN-SECRET" in lease.auth_json or "ROTATED" in lease.auth_json
            await asyncio.sleep(0.05)
            await lease.save_back(lease.auth_json.replace("REFRESH-TOKEN-SECRET", "ROTATED"))
            order.append(f"{tag}:end")

    await asyncio.gather(use("a"), use("b"))
    assert order in (["a:start", "a:end", "b:start", "b:end"], ["b:start", "b:end", "a:start", "a:end"])
    async with lease_codex(maker, me["id"]) as lease:
        assert "ROTATED" in lease.auth_json


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
    monkeypatch.delattr(os, "getuid")
    args = DockerCellManager().build_args(spec(secret_files={f"{SECRETS_DIR}/codex/auth.json": "x"}))
    assert "--user" not in args and not any("uid=" in a for a in args)
