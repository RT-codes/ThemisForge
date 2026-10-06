import asyncio
import os

import pytest

from app.app_settings import MountRoot
from app.cells import CellSpec, DockerCellManager, Mount
from app.config import BACKEND_DIR, settings
from app.volumes import MountError, host_target
from tests.conftest import drain, make_project, make_task, register


def roots(path, write=False) -> list[MountRoot]:
    return [MountRoot(path=str(path), allow_write=write)]


@pytest.fixture
def notes(tmp_path):
    folder = tmp_path / "home" / "notes"
    folder.mkdir(parents=True)
    return folder


async def approve(client, path, write=False) -> None:
    r = await client.put("/api/settings", json={"mount_roots": [{"path": str(path), "allow_write": write}]})
    assert r.status_code == 200, r.text


# ----- the rules for host folders -----


def test_a_folder_inside_an_approved_one_can_be_mounted(notes):
    real, writable = (
        host_target(str(notes / ".."), roots(notes.parent))
        if False
        else host_target(str(notes), roots(notes.parent))
    )
    assert real == notes.resolve() and writable is False
    assert host_target(str(notes), roots(notes, write=True))[1] is True  # the root itself counts


def test_a_folder_outside_every_approved_one_is_refused(tmp_path, notes):
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(MountError, match="not inside an approved folder"):
        host_target(str(other), roots(notes))
    with pytest.raises(MountError, match="not inside an approved folder"):
        host_target(str(notes), [])


def test_a_symlink_cannot_lead_out_of_an_approved_folder(tmp_path, notes):
    secret = tmp_path / "secret"
    secret.mkdir()
    (notes / "link").symlink_to(secret)
    with pytest.raises(MountError, match="not inside an approved folder"):
        host_target(str(notes / "link"), roots(notes))


def test_a_path_that_is_not_a_plain_existing_absolute_folder_is_refused(tmp_path, notes):
    (notes / "file.txt").write_text("x")
    for bad, why in (
        ("relative/path", "absolute"),
        (str(notes / "missing"), "does not exist"),
        (str(notes / "file.txt"), "not a folder"),
        (str(notes) + ":ro", "colon"),
    ):
        with pytest.raises(MountError, match=why):
            host_target(bad, roots(notes))


def test_themisforges_own_data_and_configuration_can_never_be_mounted(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "data_dir", data)
    everything = roots(BACKEND_DIR.parent.parent)
    for protected in (
        data,
        BACKEND_DIR,
        BACKEND_DIR.parent,
    ):  # the data, the config and anything containing them
        with pytest.raises(MountError, match="Themis's own"):
            host_target(str(protected), everything + roots(tmp_path))


def test_approving_the_whole_disk_or_a_vague_path_is_refused():
    for bad in ("/", "relative", "/home/me:x"):
        with pytest.raises(ValueError):
            MountRoot(path=bad)
    assert MountRoot(path="/home/me/notes/").path == "/home/me/notes"


async def test_only_real_folders_can_be_approved(client, notes):
    await register(client)
    r = await client.put("/api/settings", json={"mount_roots": [{"path": str(notes / "nope")}]})
    assert r.status_code == 422 and "not a folder" in r.text
    await approve(client, notes)
    assert (await client.get("/api/settings")).json()["mount_roots"] == [
        {"path": str(notes), "allow_write": False}
    ]


# ----- the API -----


async def test_every_project_has_a_shared_folder_that_stays(client):
    await register(client)
    pid = (await make_project(client))["id"]
    volumes = (await client.get(f"/api/projects/{pid}/volumes")).json()
    assert [(v["name"], v["kind"], v["mode"], v["is_default"]) for v in volumes] == [
        ("shared", "managed", "rw", True)
    ]
    assert (await client.get(f"/api/projects/{pid}/volumes")).json()[0]["id"] == volumes[0]["id"]  # made once
    assert (await client.delete(f"/api/volumes/{volumes[0]['id']}")).status_code == 409


async def test_managed_folders_are_made_for_you_and_names_are_checked(client):
    await register(client)
    pid = (await make_project(client))["id"]
    r = await client.post(f"/api/projects/{pid}/volumes", json={"name": "Reports", "mode": "ro"})
    assert r.status_code == 201 and r.json()["name"] == "reports" and r.json()["exclusive_write"] is False
    assert (settings.data_dir / "projects" / str(pid) / "volumes" / "reports").is_dir()
    assert (await client.post(f"/api/projects/{pid}/volumes", json={"name": "reports"})).status_code == 409
    for bad in ("", "has space", "../up", "-dash", "x" * 41):
        assert (await client.post(f"/api/projects/{pid}/volumes", json={"name": bad})).status_code == 422, bad


async def test_host_folders_need_an_approved_root_and_respect_whether_writing_is_allowed(client, notes):
    await register(client)
    pid = (await make_project(client))["id"]
    body = {"name": "docs", "kind": "host", "host_path": str(notes), "mode": "ro"}
    assert (
        await client.post(f"/api/projects/{pid}/volumes", json=body)
    ).status_code == 422  # nothing approved yet

    await approve(client, notes.parent, write=False)
    ok = await client.post(f"/api/projects/{pid}/volumes", json=body)
    assert ok.status_code == 201 and ok.json()["can_write"] is False and ok.json()["exclusive_write"] is False
    rw = await client.post(f"/api/projects/{pid}/volumes", json={**body, "name": "docs2", "mode": "rw"})
    assert rw.status_code == 422 and "only read" in rw.text
    assert (await client.patch(f"/api/volumes/{ok.json()['id']}", json={"mode": "rw"})).status_code == 422

    await approve(client, notes.parent, write=True)
    rw = await client.post(f"/api/projects/{pid}/volumes", json={**body, "name": "docs2", "mode": "rw"})
    assert rw.status_code == 201 and rw.json()["exclusive_write"] is True  # real files: writers take turns
    assert (await client.patch(f"/api/volumes/{ok.json()['id']}", json={"mode": "rw"})).json()["mode"] == "rw"


async def test_a_host_folder_whose_approval_was_withdrawn_is_flagged(client, notes):
    await register(client)
    pid = (await make_project(client))["id"]
    await approve(client, notes.parent)
    await client.post(
        f"/api/projects/{pid}/volumes",
        json={"name": "docs", "kind": "host", "host_path": str(notes), "mode": "ro"},
    )
    await client.put("/api/settings", json={})
    docs = next(v for v in (await client.get(f"/api/projects/{pid}/volumes")).json() if v["name"] == "docs")
    assert "not inside an approved folder" in docs["problem"]


async def test_removing_a_folder_removes_it_from_agents_and_keeps_its_files(client):
    await register(client)
    pid = (await make_project(client))["id"]
    vol = (await client.post(f"/api/projects/{pid}/volumes", json={"name": "out"})).json()
    (settings.data_dir / "projects" / str(pid) / "volumes" / "out" / "keep.txt").write_text("x")
    agent = (
        await client.post(
            f"/api/projects/{pid}/agents", json={"name": "A", "mounts": [{"volume_id": vol["id"]}]}
        )
    ).json()
    assert (await client.delete(f"/api/volumes/{vol['id']}")).status_code == 204
    assert (await client.get(f"/api/agents/{agent['id']}")).json()["mounts"] == []
    assert (settings.data_dir / "projects" / str(pid) / "volumes" / "out" / "keep.txt").read_text() == "x"


async def test_folders_belong_to_their_projects_owner(client):
    await register(client)
    pid = (await make_project(client))["id"]
    vol = (await client.post(f"/api/projects/{pid}/volumes", json={"name": "private"})).json()
    await register(client, "c@d.co", "Bob")
    assert (await client.get(f"/api/projects/{pid}/volumes")).status_code == 404
    assert (await client.patch(f"/api/volumes/{vol['id']}", json={"mode": "ro"})).status_code == 404
    assert (await client.delete(f"/api/volumes/{vol['id']}")).status_code == 404


# ----- mounting into cells -----


def spec(tmp_path, **kw) -> CellSpec:
    base = {
        "attempt_id": 7,
        "task_id": 1,
        "project_id": 1,
        "title": "t",
        "description": "",
        "properties": {},
        "image": "alpine:3",
        "cpus": 1,
        "memory_mb": 64,
        "timeout_seconds": 30,
    }
    return CellSpec(**{**base, **kw})


def test_docker_gets_one_volume_flag_per_mount_and_read_only_ones_say_so(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    mounts = [Mount("docs", tmp_path / "d", True, 2), Mount("shared", tmp_path / "s", False, 1)]
    args = DockerCellManager().build_args(spec(tmp_path, mounts=mounts))
    flags = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
    assert f"{tmp_path / 'd'}:/workspace/docs:ro" in flags and f"{tmp_path / 's'}:/workspace/shared" in flags
    assert not any(f.endswith("shared:ro") for f in flags)


async def test_every_cell_mounts_the_projects_shared_folder_and_the_mountpoints_are_ours(
    client, scheduler, cells
):
    await register(client)
    pid = (await make_project(client))["id"]
    await make_task(client, pid, status="ready")
    await scheduler.tick()
    await drain(scheduler)
    mounts = cells.specs[0].mounts
    assert [(m.name, m.read_only) for m in mounts] == [("shared", False)]
    assert mounts[0].source == settings.data_dir / "projects" / str(pid) / "volumes" / "shared"
    assert (cells.specs[0].workspace_dir / "shared").is_dir()
    assert os.stat(cells.specs[0].workspace_dir / "shared").st_uid == os.getuid()


async def test_a_run_fails_with_the_reason_when_its_host_folder_is_no_longer_approved(
    client, scheduler, notes
):
    await register(client)
    pid = (await make_project(client))["id"]
    await approve(client, notes.parent, write=True)
    vol = (
        await client.post(
            f"/api/projects/{pid}/volumes", json={"name": "docs", "kind": "host", "host_path": str(notes)}
        )
    ).json()
    agent = (
        await client.post(
            f"/api/projects/{pid}/agents", json={"name": "A", "mounts": [{"volume_id": vol["id"]}]}
        )
    ).json()
    await client.put(
        "/api/settings", json={"mount_roots": [{"path": str(notes.parent), "allow_write": False}]}
    )
    task = await make_task(client, pid, status="ready", agent_id=agent["id"])
    assert await scheduler.tick() == 0
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "failed"
    attempt = (await client.get(f"/api/tasks/{task['id']}/attempts")).json()[0]
    assert (
        "no longer approved for writing" in (await client.get(f"/api/attempts/{attempt['id']}")).json()["log"]
    )


async def test_writers_on_a_locked_folder_take_turns_without_blocking_others(
    client, scheduler, cells, monkeypatch
):
    from app.cells import CellResult
    from tests.test_harness import connect

    me = await register(client)
    await connect(scheduler.maker, me["id"])
    await client.put("/api/settings", json={"budget": {"cpus": 8, "memory_mb": 8192}})
    pid = (await make_project(client))["id"]
    vol = (
        await client.post(f"/api/projects/{pid}/volumes", json={"name": "out", "exclusive_write": True})
    ).json()
    writer = (
        await client.post(
            f"/api/projects/{pid}/agents", json={"name": "W", "mounts": [{"volume_id": vol["id"]}]}
        )
    ).json()
    reader = (
        await client.post(
            f"/api/projects/{pid}/agents",
            json={"name": "R", "mounts": [{"volume_id": vol["id"], "mode": "ro"}]},
        )
    ).json()
    first = await make_task(client, pid, title="w1", status="ready", agent_id=writer["id"])
    await make_task(client, pid, title="w2", status="ready", agent_id=writer["id"])
    await make_task(client, pid, title="r1", status="ready", agent_id=reader["id"])
    plain = await make_task(client, pid, title="plain", status="ready")

    gate = asyncio.Event()

    async def slow(spec, on_log):
        await gate.wait()
        return CellResult(exit_code=0)

    monkeypatch.setattr(cells, "run", slow)
    assert await scheduler.tick() == 3  # w1, r1 (read only, no lock) and plain; w2 waits its turn
    assert await scheduler.tick() == 0
    started = {s.title for s in (live.spec for live in scheduler._live.values())}
    assert started == {"w1", "r1", "plain"}
    gate.set()
    await drain(scheduler)
    assert await scheduler.tick() == 1  # w2 now gets the folder
    await drain(scheduler)
    assert (await client.get(f"/api/tasks/{first['id']}")).json()["status"] == "done"
    assert (await client.get(f"/api/tasks/{plain['id']}")).json()["status"] == "done"


async def test_the_id_of_a_removed_folder_is_never_given_to_a_new_one(client):
    """A workflow node refers to a folder by id. If the newest folder is removed and another is made, the old id must
    not quietly mean the new folder."""
    await register(client)
    pid = (await make_project(client))["id"]
    await client.get(f"/api/projects/{pid}/volumes")  # makes `shared`
    gone = (await client.post(f"/api/projects/{pid}/volumes", json={"name": "gone"})).json()
    await client.delete(f"/api/volumes/{gone['id']}")
    fresh = (await client.post(f"/api/projects/{pid}/volumes", json={"name": "fresh"})).json()
    assert fresh["id"] != gone["id"]


async def test_the_id_of_a_removed_agent_is_never_given_to_a_new_one(client):
    from tests.test_agents import make_agent

    await register(client)
    pid = (await make_project(client))["id"]
    gone = await make_agent(client, pid, name="Gone")
    await client.delete(f"/api/agents/{gone['id']}")
    assert (await make_agent(client, pid, name="Fresh"))["id"] != gone["id"]
