import pytest

from app.app_settings import AppSettings
from app.profiles import ProfileOverrides, resolve_profile
from tests.conftest import drain, make_project, make_task, register

CFG = AppSettings(cell_cpus=1, cell_memory_mb=1024, cell_timeout_seconds=600, cell_image="alpine:3")


def test_the_defaults_apply_when_nothing_is_overridden():
    p = resolve_profile(CFG, "alpine:3")
    assert (p.image, p.cpus, p.memory_mb, p.timeout_seconds) == ("alpine:3", 1, 1024, 600)


def test_each_layer_overrides_only_what_it_sets_and_later_layers_win():
    project = {"cpus": 2, "memory_mb": 2048}
    agent = {"memory_mb": 4096, "timeout_seconds": 60}
    run = {"cpus": 4}
    p = resolve_profile(CFG, "alpine:3", project, agent, run)
    assert (p.cpus, p.memory_mb, p.timeout_seconds) == (4, 4096, 60)
    assert resolve_profile(CFG, "alpine:3", None, {}, project).memory_mb == 2048


def test_a_harness_image_is_the_default_and_an_explicit_image_replaces_it():
    assert resolve_profile(CFG, "themisforge/cell-codex:latest").image == "themisforge/cell-codex:latest"
    assert resolve_profile(CFG, "codex-img", {"image": "mine:1"}).image == "mine:1"


def test_stored_overrides_with_unknown_or_empty_fields_are_harmless():
    assert resolve_profile(CFG, "alpine:3", {"cpus": None, "nonsense": 1}).cpus == 1


def test_overrides_are_validated_and_only_set_fields_are_kept():
    assert ProfileOverrides().clean() is None
    assert ProfileOverrides(image="  ", cpus=2).clean() == {"cpus": 2}
    for bad in (
        {"cpus": 0},
        {"cpus": 65},
        {"memory_mb": 8},
        {"timeout_seconds": 1},
        {"image": "-x"},
        {"x": 1},
    ):
        with pytest.raises(ValueError):
            ProfileOverrides.model_validate(bad)


async def test_a_project_can_override_the_cell_and_go_back_to_the_defaults(client):
    await register(client)
    pid = (await client.post("/api/projects", json={"name": "P", "cell_profile": {"cpus": 2}})).json()["id"]
    assert (await client.get(f"/api/projects/{pid}")).json()["cell_profile"] == {"cpus": 2}
    r = await client.patch(f"/api/projects/{pid}", json={"cell_profile": {"memory_mb": 512, "cpus": None}})
    assert r.json()["cell_profile"] == {"memory_mb": 512}
    assert (await client.patch(f"/api/projects/{pid}", json={"name": "Q"})).json()["cell_profile"] == {
        "memory_mb": 512
    }
    assert (await client.patch(f"/api/projects/{pid}", json={"cell_profile": None})).json()[
        "cell_profile"
    ] is None
    assert (await client.patch(f"/api/projects/{pid}", json={"cell_profile": {"cpus": 0}})).status_code == 422


async def test_a_cell_gets_its_projects_size(client, scheduler, cells):
    await register(client)
    await client.put("/api/settings", json={"budget": {"cpus": 8, "memory_mb": 8192}})
    plain = (await make_project(client, "Plain"))["id"]
    big = (
        await client.post(
            "/api/projects",
            json={"name": "Big", "cell_profile": {"cpus": 2, "memory_mb": 2048, "timeout_seconds": 90}},
        )
    ).json()["id"]
    await make_task(client, plain, title="a", status="ready")
    await make_task(client, big, title="b", status="ready")
    assert await scheduler.tick() == 2
    await drain(scheduler)
    sizes = {s.title: (s.cpus, s.memory_mb, s.timeout_seconds) for s in cells.specs}
    assert sizes == {"a": (1.0, 1024, 3600), "b": (2.0, 2048, 90)}


async def test_the_budget_counts_each_cells_own_size(client, scheduler):
    await register(client)
    await client.put("/api/settings", json={"budget": {"cpus": 3, "memory_mb": 8192}})
    big = (await client.post("/api/projects", json={"name": "Big", "cell_profile": {"cpus": 2}})).json()["id"]
    await make_task(client, big, title="first", status="ready")
    await make_task(client, big, title="second", status="ready")
    assert await scheduler.tick() == 1  # 2 + 2 CPUs do not fit in 3
    await drain(scheduler)
    assert await scheduler.tick() == 1


async def test_a_projects_cell_bigger_than_the_budget_fails_its_tasks_with_a_reason(client, scheduler):
    await register(client)
    await client.put("/api/settings", json={"budget": {"cpus": 2, "memory_mb": 2048}})
    pid = (await client.post("/api/projects", json={"name": "Huge", "cell_profile": {"cpus": 8}})).json()[
        "id"
    ]
    task = await make_task(client, pid, status="ready")
    assert await scheduler.tick() == 0
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "failed"


async def test_cell_defaults_are_visible_to_every_user(client):
    await register(client)
    await register(client, "c@d.co", "Bob")
    defaults = (await client.get("/api/system/status")).json()["cell_defaults"]
    assert defaults == {"image": "alpine:3", "cpus": 1.0, "memory_mb": 1024, "timeout_seconds": 3600}
