import shutil

from sqlalchemy import select

from app import docker_check
from app.models import Secret
from tests.conftest import register


async def test_settings_are_admin_only(client):
    await register(client, "a@b.co")
    assert (await client.get("/api/settings")).json()["max_concurrent_cells"] == 2
    client.cookies.clear()
    await register(client, "c@d.co", "Bob")
    assert (await client.get("/api/settings")).status_code == 403
    assert (await client.put("/api/settings", json={})).status_code == 403
    assert (await client.get("/api/secrets")).status_code == 403
    assert (await client.get("/api/system/docker")).status_code == 403
    assert (await client.get("/api/system/status")).status_code == 200  # any signed-in user


async def test_settings_validation_and_persistence(client):
    await register(client)
    for bad in (
        {"timezone": "Mars/Base"},
        {"docker_host": "http://nope"},
        {"cell_image": "-rm"},
        {"max_concurrent_cells": 0},
    ):
        assert (await client.put("/api/settings", json=bad)).status_code == 422, bad
    saved = (await client.put("/api/settings", json={"docker_host": "ssh://u@h", "cell_cpus": 2})).json()
    assert saved["docker_host"] == "ssh://u@h" and saved["cell_cpus"] == 2
    assert (await client.get("/api/settings")).json() == saved


async def test_secrets_are_encrypted_and_masked(client, maker):
    await register(client)
    r = await client.post(
        "/api/secrets", json={"name": "Anthropic", "kind": "anthropic", "value": "sk-ant-supersecret-1234"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["hint"] == "…1234" and "value" not in body and "supersecret" not in r.text
    assert "supersecret" not in (await client.get("/api/secrets")).text

    async with maker() as s:
        stored = (await s.scalars(select(Secret))).one()
        assert "supersecret" not in stored.value_encrypted

    dup = await client.post("/api/secrets", json={"name": "Anthropic", "value": "x"})
    assert dup.status_code == 409
    assert (await client.delete(f"/api/secrets/{body['id']}")).status_code == 204
    assert (await client.get("/api/secrets")).json() == []


async def test_docker_status_endpoint(client, monkeypatch):
    await register(client)
    seen = []

    async def fake_check(host=""):
        seen.append(host)
        return docker_check.DockerStatus(ok=True, installed=True, host=host or "local socket", version="99.0")

    monkeypatch.setattr("app.routers.system.check_docker", fake_check)
    assert (await client.get("/api/system/docker")).json()["version"] == "99.0"
    assert (await client.get("/api/system/docker?host=tcp://x:2376")).json()["host"] == "tcp://x:2376"
    assert (await client.get("/api/system/docker?host=bogus")).status_code == 422
    assert seen == ["", "tcp://x:2376"]


async def test_check_docker_reports_each_failure_mode(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    missing = await docker_check.check_docker()
    assert not missing.installed and "install" in missing.hint

    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")

    async def denied(args, env, timeout):
        return 1, "", "permission denied while trying to connect to the Docker daemon socket"

    monkeypatch.setattr(docker_check, "run_command", denied)
    status = await docker_check.check_docker()
    assert status.installed and not status.ok and "docker' group" in status.hint

    async def ok(args, env, timeout):
        assert env.get("DOCKER_HOST") == "ssh://u@h"
        return (
            0,
            '{"ServerVersion": "27.1.0", "NCPU": 4, "MemTotal": 8589934592, "OperatingSystem": "Debian"}',
            "",
        )

    monkeypatch.setattr(docker_check, "run_command", ok)
    status = await docker_check.check_docker("ssh://u@h")
    assert status.ok and status.version == "27.1.0" and status.cpus == 4 and status.memory_mb == 8192


async def test_system_status_reports_scheduler(client, scheduler):
    await register(client)
    status = (await client.get("/api/system/status")).json()
    assert status["scheduler"]["active_cells"] == 0 and status["scheduler"]["max_cells"] == 2
    assert status["timezone"] == "UTC"
    assert status["insecure_secret_key"] is True  # the test environment uses the default key
