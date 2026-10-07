"""The Files page: browsing and managing what is inside a project's folders."""

import asyncio
import os

import pytest

from app.app_settings import AppSettings
from app.config import settings
from app.volumes import plan_mounts
from tests.conftest import drain, make_project, make_task, register
from tests.test_volumes import approve, notes  # noqa: F401  (notes is a fixture)


async def shared_id(client, pid: int) -> int:
    volumes = (await client.get(f"/api/projects/{pid}/volumes")).json()
    return next(v["id"] for v in volumes if v["is_default"])


@pytest.fixture
async def files(client):
    """A signed-in user with a project: (volume id of its shared folder, the folder on disk)."""
    await register(client)
    pid = (await make_project(client))["id"]
    vid = await shared_id(client, pid)
    disk = settings.data_dir / "projects" / str(pid) / "volumes" / "shared"
    disk.mkdir(parents=True)  # a cell (or the first visit to the page) would make it
    return vid, disk


def put(client, vid, path, data=b"hello", **params):
    return client.put(f"/api/volumes/{vid}/file", params={"path": path, **params}, content=data)


async def test_the_shared_folder_starts_empty_and_lists_what_is_in_it(client, files):
    vid, disk = files
    empty = (await client.get(f"/api/volumes/{vid}/files")).json()
    assert empty["entries"] == [] and empty["writable"] is True and empty["runs"] == []
    (disk / "docs").mkdir()
    (disk / "b.txt").write_text("bb")
    (disk / "A.md").write_text("a")
    listing = (await client.get(f"/api/volumes/{vid}/files")).json()
    assert [(e["name"], e["is_dir"]) for e in listing["entries"]] == [
        ("docs", True),
        ("A.md", False),
        ("b.txt", False),
    ]
    assert listing["entries"][2]["size"] == 2


async def test_upload_read_move_and_delete(client, files):
    vid, disk = files
    assert (await client.post(f"/api/volumes/{vid}/folder", json={"path": "reports"})).status_code == 201
    assert (await put(client, vid, "reports/a.txt", b"first")).status_code == 204
    assert (disk / "reports" / "a.txt").read_bytes() == b"first"
    assert not list(disk.rglob("*.part"))

    # an upload never silently replaces a file
    assert (await put(client, vid, "reports/a.txt", b"second")).status_code == 409
    assert (await put(client, vid, "reports/a.txt", b"second", overwrite=True)).status_code == 204

    read = await client.get(f"/api/volumes/{vid}/file", params={"path": "reports/a.txt"})
    assert read.text == "second" and read.headers["content-type"].startswith("text/plain")
    down = await client.get(f"/api/volumes/{vid}/file", params={"path": "reports/a.txt", "download": True})
    assert "attachment" in down.headers["content-disposition"]

    move = {"source": "reports/a.txt", "destination": "reports/b.txt"}
    assert (await client.post(f"/api/volumes/{vid}/move", json=move)).status_code == 204
    assert (await client.post(f"/api/volumes/{vid}/move", json=move)).status_code == 404
    assert not (disk / "reports" / "a.txt").exists() and (disk / "reports" / "b.txt").exists()
    clash = {"source": "reports", "destination": "reports/inner"}
    assert (await client.post(f"/api/volumes/{vid}/move", json=clash)).status_code == 422

    assert (await client.delete(f"/api/volumes/{vid}/file", params={"path": "reports"})).status_code == 204
    assert not (disk / "reports").exists()
    assert (await client.delete(f"/api/volumes/{vid}/file", params={"path": "reports"})).status_code == 404


@pytest.mark.skipif(os.name == "nt", reason="Windows has no executable bit")
async def test_overwriting_a_file_keeps_its_permissions(client, files):
    vid, disk = files
    script = disk / "run.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    assert (await put(client, vid, "run.sh", b"#!/bin/sh\necho hi\n", overwrite=True)).status_code == 204
    assert script.read_text().endswith("echo hi\n") and script.stat().st_mode & 0o777 == 0o755


async def test_html_is_never_served_as_a_page_and_svg_only_in_a_sandbox(client, files):
    vid, disk = files
    (disk / "x.html").write_text("<script>alert(1)</script>")
    (disk / "x.svg").write_text("<svg onload=alert(1)/>")
    (disk / "x.PNG").write_bytes(b"\x89PNG")
    for name, kind in (("x.html", "text/plain"), ("x.svg", "image/svg+xml"), ("x.PNG", "image/png")):
        r = await client.get(f"/api/volumes/{vid}/file", params={"path": name})
        assert r.headers["content-type"].startswith(kind) and r.headers["x-content-type-options"] == "nosniff"
        # a script in the file cannot run even when the address is opened directly
        assert r.headers["content-security-policy"].startswith("sandbox;")
    down = await client.get(f"/api/volumes/{vid}/file", params={"path": "x.svg", "download": True})
    assert "attachment" in down.headers["content-disposition"]


@pytest.mark.parametrize("bad", ["../outside.txt", "a/../../outside.txt", "..", "a/./b"])
async def test_paths_cannot_leave_the_folder(client, files, bad):
    vid, disk = files
    (disk.parent / "outside.txt").write_text("secret")
    assert (await client.get(f"/api/volumes/{vid}/file", params={"path": bad})).status_code == 422
    assert (await put(client, vid, bad)).status_code == 422
    assert (await client.delete(f"/api/volumes/{vid}/file", params={"path": bad})).status_code == 422
    assert (await client.get(f"/api/volumes/{vid}/files", params={"path": bad})).status_code == 422
    assert (disk.parent / "outside.txt").read_text() == "secret"


async def test_a_symlink_cannot_be_used_to_read_or_write_outside(client, files, tmp_path):
    vid, disk = files
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "key.txt").write_text("secret")
    try:
        (disk / "link").symlink_to(secret)
        (disk / "filelink").symlink_to(secret / "key.txt")
    except OSError:  # Windows without the privilege to make links
        pytest.skip("cannot create symbolic links here")
    assert (await client.get(f"/api/volumes/{vid}/files", params={"path": "link"})).status_code == 422
    assert (await client.get(f"/api/volumes/{vid}/file", params={"path": "link/key.txt"})).status_code == 422
    assert (await client.get(f"/api/volumes/{vid}/file", params={"path": "filelink"})).status_code == 422
    assert (await put(client, vid, "link/new.txt")).status_code == 422
    assert not (secret / "new.txt").exists()
    # the link itself can be removed, and that never touches what it points at
    assert (await client.delete(f"/api/volumes/{vid}/file", params={"path": "link"})).status_code == 204
    assert not (disk / "link").exists() and (secret / "key.txt").read_text() == "secret"


async def test_the_folder_itself_cannot_be_deleted_or_overwritten(client, files):
    vid, disk = files
    assert (await client.delete(f"/api/volumes/{vid}/file", params={"path": ""})).status_code == 422
    assert (await put(client, vid, "")).status_code == 422
    assert disk.is_dir()


async def test_a_read_only_folder_can_be_browsed_but_not_changed(client, notes):  # noqa: F811
    await register(client)
    pid = (await make_project(client))["id"]
    await approve(client, notes.parent, write=False)
    (notes / "a.txt").write_text("a")
    body = {"name": "docs", "kind": "host", "host_path": str(notes), "mode": "ro"}
    vid = (await client.post(f"/api/projects/{pid}/volumes", json=body)).json()["id"]
    listing = (await client.get(f"/api/volumes/{vid}/files")).json()
    assert listing["writable"] is False and [e["name"] for e in listing["entries"]] == ["a.txt"]
    assert (await client.get(f"/api/volumes/{vid}/file", params={"path": "a.txt"})).text == "a"
    assert (await put(client, vid, "b.txt")).status_code == 403
    assert (await client.delete(f"/api/volumes/{vid}/file", params={"path": "a.txt"})).status_code == 403
    assert (await client.post(f"/api/volumes/{vid}/folder", json={"path": "x"})).status_code == 403
    assert (notes / "a.txt").exists()


async def test_a_host_folder_follows_its_approval(client, notes):  # noqa: F811
    await register(client)
    pid = (await make_project(client))["id"]
    await approve(client, notes.parent, write=True)
    body = {"name": "docs", "kind": "host", "host_path": str(notes), "mode": "rw"}
    vid = (await client.post(f"/api/projects/{pid}/volumes", json=body)).json()["id"]
    assert (await put(client, vid, "a.txt")).status_code == 204 and (notes / "a.txt").exists()
    await approve(client, notes.parent, write=False)  # withdrawn after the folder was added
    assert (await put(client, vid, "b.txt")).status_code == 403
    await client.put("/api/settings", json={"mount_roots": []})
    assert (await client.get(f"/api/volumes/{vid}/files")).status_code == 409


async def test_a_folder_a_run_is_using_is_locked_for_every_change_but_stays_readable(
    client, files, scheduler, monkeypatch
):
    vid, disk = files
    (disk / "a.txt").write_text("a")
    monkeypatch.setattr(
        scheduler, "runs_using", lambda volume_id: [(7, "Write the poem")] if volume_id == vid else []
    )
    listing = (await client.get(f"/api/volumes/{vid}/files")).json()
    assert listing["runs"] == [{"task_id": 7, "title": "Write the poem"}]

    changes = [
        put(client, vid, "b.txt"),
        put(client, vid, "a.txt", overwrite=True),
        client.post(f"/api/volumes/{vid}/folder", json={"path": "x"}),
        client.post(f"/api/volumes/{vid}/move", json={"source": "a.txt", "destination": "c.txt"}),
        client.delete(f"/api/volumes/{vid}/file", params={"path": "a.txt"}),
    ]
    for change in changes:
        r = await change
        assert r.status_code == 409 and "task 7 (Write the poem)" in r.text
    assert [p.name for p in disk.iterdir()] == ["a.txt"] and (disk / "a.txt").read_text() == "a"
    # looking and downloading are never blocked
    assert (await client.get(f"/api/volumes/{vid}/file", params={"path": "a.txt"})).text == "a"


async def test_a_listing_that_has_not_changed_is_answered_with_304(client, files, scheduler, monkeypatch):
    vid, disk = files
    first = await client.get(f"/api/volumes/{vid}/files")
    etag = first.headers["etag"]
    again = await client.get(f"/api/volumes/{vid}/files", headers={"if-none-match": etag})
    assert again.status_code == 304 and not again.content

    (disk / "new.txt").write_text("hi")  # a file appears (an agent made it)
    changed = await client.get(f"/api/volumes/{vid}/files", headers={"if-none-match": etag})
    assert changed.status_code == 200 and [e["name"] for e in changed.json()["entries"]] == ["new.txt"]
    etag = changed.headers["etag"]
    (disk / "new.txt").write_text("hello")  # and is changed
    assert (await client.get(f"/api/volumes/{vid}/files", headers={"if-none-match": etag})).status_code == 200
    etag = (await client.get(f"/api/volumes/{vid}/files")).headers["etag"]

    # a run starting changes the answer too, so the page learns the folder is locked
    monkeypatch.setattr(scheduler, "runs_using", lambda volume_id: [(1, "T")])
    assert (await client.get(f"/api/volumes/{vid}/files", headers={"if-none-match": etag})).status_code == 200


async def test_a_save_is_refused_when_the_file_changed_since_it_was_opened(client, files):
    vid, disk = files
    (disk / "notes.md").write_text("one")
    opened = (await client.get(f"/api/volumes/{vid}/files")).json()["entries"][0]["modified"]
    (disk / "notes.md").write_text("two")  # an agent rewrote it meanwhile
    stale = await put(client, vid, "notes.md", b"mine", overwrite=True, base=opened)
    assert stale.status_code == 412 and "changed since you opened it" in stale.text
    assert (disk / "notes.md").read_text() == "two"

    fresh = (await client.get(f"/api/volumes/{vid}/files")).json()["entries"][0]["modified"]
    assert (await put(client, vid, "notes.md", b"mine", overwrite=True, base=fresh)).status_code == 204
    assert (disk / "notes.md").read_text() == "mine"
    assert (await put(client, vid, "notes.md", b"forced", overwrite=True)).status_code == 204  # "save anyway"


async def test_other_peoples_folders_are_not_visible(client, files):
    vid, _ = files
    await register(client, email="b@b.co", name="Bo")
    assert (await client.get(f"/api/volumes/{vid}/files")).status_code == 404


# ----- renaming a folder -----


def project_id(disk) -> int:
    """The project a `files` fixture folder belongs to: data/projects/<id>/volumes/shared."""
    return int(disk.parent.parent.name)


async def new_folder(client, pid, name="reports", **extra) -> dict:
    r = await client.post(f"/api/projects/{pid}/volumes", json={"name": name, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def test_renaming_a_managed_folder_moves_it_on_disk_and_keeps_its_files(client, maker):
    await register(client)
    pid = (await make_project(client))["id"]
    vol = await new_folder(client, pid)
    old = settings.data_dir / "projects" / str(pid) / "volumes" / "reports"
    (old / "a.txt").write_text("kept")
    r = await client.patch(
        f"/api/volumes/{vol['id']}", json={"name": " Summaries "}
    )  # tidied like a new name
    assert r.status_code == 200 and r.json()["name"] == "summaries" and r.json()["id"] == vol["id"]
    new = old.parent / "summaries"
    assert not old.exists() and (new / "a.txt").read_text() == "kept"
    assert [e["name"] for e in (await client.get(f"/api/volumes/{vol['id']}/files")).json()["entries"]] == [
        "a.txt"
    ]

    # the next cell mounts it under the new name, from where it now lives (it is found by id, not by name)
    async with maker() as session:
        mounts = await plan_mounts(session, pid, [{"volume_id": vol["id"], "mode": "rw"}], AppSettings())
    assert {m.name: m.source for m in mounts}["summaries"] == new


async def test_renaming_a_host_folder_changes_only_its_name(client, notes):  # noqa: F811
    await register(client)
    pid = (await make_project(client))["id"]
    await approve(client, notes.parent, write=True)
    vol = await new_folder(client, pid, "docs", kind="host", host_path=str(notes))
    r = await client.patch(f"/api/volumes/{vol['id']}", json={"name": "handbook"})
    assert r.json()["name"] == "handbook" and r.json()["host_path"] == vol["host_path"] and notes.is_dir()


async def test_the_shared_folder_cannot_be_renamed(client, files):
    vid, disk = files
    r = await client.patch(f"/api/volumes/{vid}", json={"name": "inbox"})
    assert r.status_code == 409 and "shared folder keeps its name" in r.text
    assert disk.is_dir()


async def test_a_rename_that_would_clash_or_is_not_a_valid_name_is_refused(client, files):
    _, disk = files
    pid = project_id(disk)
    a, b = await new_folder(client, pid, "a"), await new_folder(client, pid, "b")
    taken = await client.patch(f"/api/volumes/{a['id']}", json={"name": "b"})
    assert taken.status_code == 409 and "already has a folder" in taken.text
    assert (await client.patch(f"/api/volumes/{a['id']}", json={"name": "shared"})).status_code == 409
    for bad in ("", "Has Space", "../up", "-dash"):
        assert (await client.patch(f"/api/volumes/{a['id']}", json={"name": bad})).status_code == 422, bad
    same = await client.patch(
        f"/api/volumes/{a['id']}", json={"name": "a", "mode": "ro"}
    )  # same name: nothing to do
    assert same.status_code == 200 and same.json()["name"] == "a" and same.json()["mode"] == "ro"
    assert b["name"] == "b"


async def test_a_rename_onto_files_left_on_disk_is_refused(client, files):
    _, disk = files
    a = await new_folder(client, project_id(disk), "a")
    leftover = disk.parent / "old-name"
    leftover.mkdir()  # what removing a folder from a project leaves behind
    (leftover / "x.txt").write_text("x")
    r = await client.patch(f"/api/volumes/{a['id']}", json={"name": "old-name"})
    assert r.status_code == 409 and "still exists on disk" in r.text
    assert (disk.parent / "a").is_dir() and (leftover / "x.txt").exists()


async def test_a_folder_a_run_is_using_keeps_its_name_until_it_finishes(
    client, files, scheduler, monkeypatch
):
    _, disk = files
    a = await new_folder(client, project_id(disk), "a")
    monkeypatch.setattr(scheduler, "runs_using", lambda volume_id: [(3, "Busy task")])
    r = await client.patch(f"/api/volumes/{a['id']}", json={"name": "b"})
    assert r.status_code == 409 and "run is using" in r.text and "Busy task" in r.text
    assert (disk.parent / "a").is_dir() and not (disk.parent / "b").exists()
    # settings other than the name are still changeable meanwhile
    assert (await client.patch(f"/api/volumes/{a['id']}", json={"mode": "ro"})).status_code == 200


# ----- the scheduler's side of the lock -----


async def test_a_running_task_locks_the_folders_it_mounts_until_it_ends(
    client, files, scheduler, cells, monkeypatch
):
    from app.cells import CellResult

    vid, disk = files
    pid = project_id(disk)
    task = await make_task(client, pid, title="Write the poem", status="ready")
    gate = asyncio.Event()

    async def slow(spec, on_log):
        await gate.wait()
        return CellResult(exit_code=0)

    monkeypatch.setattr(cells, "run", slow)
    assert await scheduler.tick() == 1  # every cell mounts the shared folder
    assert scheduler.runs_using(vid) == [(task["id"], "Write the poem")]
    listing = (await client.get(f"/api/volumes/{vid}/files")).json()
    assert listing["runs"] == [{"task_id": task["id"], "title": "Write the poem"}]
    assert (await put(client, vid, "a.txt")).status_code == 409

    gate.set()
    await drain(scheduler)
    assert scheduler.runs_using(vid) == []
    assert (await put(client, vid, "a.txt")).status_code == 204


async def test_no_run_starts_on_a_folder_while_it_is_being_renamed(client, files, scheduler):
    vid, disk = files
    await make_task(client, project_id(disk), title="job", status="ready")
    with scheduler.renaming(vid):
        assert await scheduler.tick() == 0  # it would mount the old path and make a fresh empty folder there
    assert await scheduler.tick() == 1
    await drain(scheduler)
