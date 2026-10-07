"""Signing in to Codex inside a throwaway container of the cell image: nothing to install on the server but Docker."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

from app.codex import CodexLogins
from app.config import settings
from app.main import app
from tests.conftest import register

FAKE_DOCKER = Path(__file__).parent / "fake_docker.py"


@pytest.fixture(autouse=True)
def secure_key(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "a-real-secret-key-for-tests-0123456789")


@pytest.fixture(autouse=True)
async def logins(maker):
    app.state.codex_logins = CodexLogins(maker)
    yield app.state.codex_logins
    await app.state.codex_logins.shutdown()


@pytest.fixture
def fake_docker(tmp_path, monkeypatch):
    """Puts a `docker` on the PATH that is only a stand-in, and returns the folder where it keeps its records."""
    state = tmp_path / "docker-state"
    state.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if os.name == "nt":
        (bin_dir / "docker.cmd").write_text(f'@"{sys.executable}" "{FAKE_DOCKER}" %*\r\n')
    else:
        shim = bin_dir / "docker"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_DOCKER}" "$@"\n')
        shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(state))
    monkeypatch.setenv("FAKE_CODEX_MODE", "ok")
    monkeypatch.setattr(settings, "codex_login", "container")
    return state


async def wait_for(client, status: str, timeout: float = 15) -> dict:
    async with asyncio.timeout(timeout):
        while (body := (await client.get("/api/codex")).json())["login"]["status"] != status:
            await asyncio.sleep(0.05)
    return body


def calls(state: Path) -> list[str]:
    return (state / "calls.log").read_text().splitlines()


async def test_the_one_time_sign_in_runs_in_a_container_and_stores_the_login_as_before(
    client, maker, fake_docker
):
    await register(client)
    status = (await client.get("/api/codex")).json()
    assert status["can_sign_in"] is True  # Docker is all it needs
    started = (await client.post("/api/codex/login")).json()
    assert (
        started["status"] == "waiting"
        and started["code"] == "ABCD-12345"
        and "auth.example.test" in started["verification_url"]
    )
    done = await wait_for(client, "connected")
    assert (
        done["connected"] and done["account"] == "ada@example.test"
    )  # the same encrypted login in the same place
    run, copy, remove = calls(fake_docker)[0], calls(fake_docker)[1], calls(fake_docker)[2]
    assert (
        run.startswith("run --name themis-login-")
        and "themisforge/cell-codex:latest sh -c" in run
        and "exec codex login" in run
        and "--device-auth" in run
    )
    assert "-e CODEX_HOME=/tmp/codex-login" in run and "--label themis.login=1" in run
    assert copy.startswith("cp themis-login-") and copy.split()[1].endswith(":/tmp/codex-login/auth.json")
    assert remove.startswith("rm -f themis-login-")  # nothing is left behind
    assert not any(p.is_dir() for p in fake_docker.iterdir())


async def test_the_container_is_removed_when_the_sign_in_is_cancelled_or_fails(
    client, fake_docker, monkeypatch
):
    await register(client)
    monkeypatch.setenv("FAKE_CODEX_MODE", "hang")
    await client.post("/api/codex/login")
    await client.delete("/api/codex/login")
    assert (await wait_for(client, "cancelled"))["login"]["status"] == "cancelled"
    assert (fake_docker / "removed.txt").read_text().startswith("themis-login-")
    monkeypatch.setenv("FAKE_CODEX_MODE", "fail")
    await client.post("/api/codex/login")
    failed = await wait_for(client, "failed")
    assert "did not finish" in failed["login"]["error"]
    assert (fake_docker / "removed.txt").read_text().count("themis-login-") == 2


async def test_a_docker_that_cannot_run_the_sign_in_says_so(client, fake_docker, monkeypatch):
    await register(client)
    monkeypatch.setenv("FAKE_DOCKER_MODE", "daemon-down")
    await client.post("/api/codex/login")
    failed = await wait_for(client, "failed")
    assert (
        "Cannot connect to the Docker daemon" in failed["login"]["error"]
    )  # Docker's own words, not just "did not finish"


async def test_without_docker_on_the_server_the_reason_is_in_plain_words(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "codex_login", "container")
    monkeypatch.setenv("PATH", str(tmp_path))  # no docker here
    await register(client)
    status = (await client.get("/api/codex")).json()
    assert status["can_sign_in"] is False and "needs Docker" in status["sign_in_problem"]
    r = await client.post("/api/codex/login")
    assert r.status_code == 503 and "Docker" in r.json()["detail"]
