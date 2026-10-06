import asyncio

import pytest

from app.app_settings import AppSettings, load_settings
from app.budget import Cost, admit, cells_that_fit, never_fits, recommend_budget
from app.cells import CellResult, CellSpec
from app.docker_check import DockerStatus
from app.models import AppSetting
from app.routers import system as system_router
from tests.conftest import drain, make_project, make_task, register

SMALL, BIG = Cost(1, 1024), Cost(4, 4096)


def test_cells_are_admitted_in_order_while_they_fit():
    budget = Cost(4, 4096)
    assert admit(budget, [], [SMALL, SMALL, SMALL]) == 3
    assert admit(budget, [SMALL, SMALL], [SMALL, SMALL, SMALL]) == 2  # the running ones count
    assert admit(budget, [SMALL] * 4, [SMALL]) == 0
    assert admit(Cost(8, 2048), [], [SMALL, SMALL, SMALL]) == 2  # memory can be the limit as well as CPUs


def test_a_big_cell_is_not_overtaken_by_the_small_ones_behind_it():
    assert admit(Cost(4, 4096), [SMALL], [BIG, SMALL]) == 0


def test_a_cell_bigger_than_the_whole_budget_never_fits():
    assert never_fits(Cost(2, 2048), BIG)
    assert not never_fits(Cost(4, 4096), BIG)


def test_how_many_cells_fit():
    assert cells_that_fit(Cost(6, 8192), SMALL) == 6
    assert cells_that_fit(Cost(6, 3000), SMALL) == 2
    assert cells_that_fit(Cost(0.5, 4096), SMALL) == 0
    assert cells_that_fit(Cost(0.3, 4096), Cost(0.1, 64)) == 3  # no float surprises


def test_the_recommended_budget_leaves_the_machine_room():
    assert recommend_budget(8, 16384) == Cost(6, 12288)  # 8 CPUs: keep 1.6, so 6 whole CPUs
    assert recommend_budget(4, 8192) == Cost(3, 6144)
    assert recommend_budget(2, 4096) == Cost(1, 3072)
    assert recommend_budget(1, 1024).cpus == 1  # never recommend zero


def test_a_budget_is_checked():
    for bad in ({"cpus": 0}, {"cpus": 5000}, {"memory_mb": 10}):
        with pytest.raises(ValueError):
            AppSettings.model_validate({"budget": bad})


async def test_settings_saved_with_a_cell_count_become_the_same_budget(maker):
    async with maker() as s:
        s.add(
            AppSetting(key="app", value={"max_concurrent_cells": 3, "cell_cpus": 2.0, "cell_memory_mb": 512})
        )
        await s.commit()
    async with maker() as s:
        cfg = await load_settings(s)
    assert cfg.budget.cpus == 6.0 and cfg.budget.memory_mb == 1536
    assert not hasattr(cfg, "max_concurrent_cells")


def test_an_old_cell_count_that_is_huge_still_loads():
    cfg = AppSettings.model_validate(
        {"max_concurrent_cells": 64, "cell_cpus": 64, "cell_memory_mb": 1_048_576}
    )
    assert cfg.budget.cpus == 4096 and cfg.budget.memory_mb == 16_777_216


async def test_the_budget_limits_how_many_cells_run_at_once(client, scheduler, cells, monkeypatch):
    await register(client)
    await client.put("/api/settings", json={"budget": {"cpus": 2, "memory_mb": 2048}})
    pid = (await make_project(client))["id"]
    for name in "abc":
        await make_task(client, pid, title=name, status="ready")
    gate = asyncio.Event()

    async def slow_run(spec: CellSpec, on_log):
        await gate.wait()
        return CellResult(exit_code=0)

    monkeypatch.setattr(cells, "run", slow_run)
    assert await scheduler.tick() == 2  # two cells of 1 CPU / 1024 MB fill 2 CPUs
    assert await scheduler.tick() == 0
    gate.set()
    await drain(scheduler)
    assert await scheduler.tick() == 1


async def test_memory_can_be_the_limit(client, scheduler, cells, monkeypatch):
    await register(client)
    await client.put("/api/settings", json={"budget": {"cpus": 8, "memory_mb": 1024}})
    pid = (await make_project(client))["id"]
    await make_task(client, pid, title="a", status="ready")
    await make_task(client, pid, title="b", status="ready")
    monkeypatch.setattr(cells, "run", lambda spec, on_log: asyncio.Event().wait())
    assert await scheduler.tick() == 1
    scheduler._live[next(iter(scheduler._live))].task.cancel()


async def test_a_task_that_cannot_fit_the_whole_budget_fails_with_a_reason(client, scheduler):
    await register(client)
    await client.put("/api/settings", json={"cell_cpus": 4, "budget": {"cpus": 2, "memory_mb": 2048}})
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, title="too big", status="ready")
    assert await scheduler.tick() == 0
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "failed"
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    log = (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    assert "more than the whole resource budget" in log and "Settings" in log


async def test_the_status_shows_how_many_cells_fit(client):
    await register(client)
    await client.put("/api/settings", json={"budget": {"cpus": 3, "memory_mb": 8192}})
    assert (await client.get("/api/system/status")).json()["scheduler"]["max_cells"] == 3


async def test_resources_report_the_host_and_a_recommendation(client, monkeypatch):
    await register(client)

    async def docker(host=""):
        return DockerStatus(installed=True, host="local socket", ok=True, cpus=8, memory_mb=16384)

    monkeypatch.setattr(system_router, "check_docker", docker)
    r = (await client.get("/api/system/resources")).json()
    assert r["ok"] and r["host_cpus"] == 8 and r["host_memory_mb"] == 16384
    assert r["recommended"] == {"cpus": 6.0, "memory_mb": 12288}
    assert r["disk_total_mb"] > 0 and r["disk_free_mb"] > 0


async def test_resources_without_docker_still_report_the_disk(client, monkeypatch):
    await register(client)

    async def docker(host=""):
        return DockerStatus(
            installed=True, host="local socket", ok=False, error="Cannot connect", hint="Start Docker"
        )

    monkeypatch.setattr(system_router, "check_docker", docker)
    r = (await client.get("/api/system/resources")).json()
    assert not r["ok"] and r["error"] == "Cannot connect" and r["recommended"] is None
    assert r["disk_free_mb"] > 0


async def test_resources_are_admin_only(client):
    await register(client)
    await register(client, "c@d.co", "Bob")
    assert (await client.get("/api/system/resources")).status_code == 403
