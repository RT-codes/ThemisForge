"""What Themis needs, checked at start and kept checked (app/preflight.py), the trail of runs (app/runlog.py), and the doctor."""

import json
import logging
import logging.handlers

import pytest

from app import docker_check, doctor, preflight, runlog
from app.app_settings import AppSettings
from app.config import settings
from app.docker_check import DockerStatus, parse_version
from app.main import app
from tests.conftest import drain, make_project, make_task, register


def docker_info(version="27.1.0", os_type="linux"):
    return json.dumps(
        {
            "ServerVersion": version,
            "OSType": os_type,
            "NCPU": 4,
            "MemTotal": 8 * 2**30,
            "OperatingSystem": "x",
        }
    )


@pytest.fixture
def docker_answers(monkeypatch):
    """Makes `docker info` answer with this JSON (and the docker program exist)."""

    def answer(text, code=0, err=""):
        async def fake(args, env, timeout):
            return code, text, err

        monkeypatch.setattr(docker_check.shutil, "which", lambda _: "/usr/bin/docker")
        monkeypatch.setattr(docker_check, "run_command", fake)

    return answer


# ----- Docker must be usable, not just there -----


def test_docker_versions_are_read_from_what_docker_prints():
    assert parse_version("27.1.0") == (27, 1, 0) and parse_version("24.0.7-ce") == (24, 0, 7)
    assert parse_version("25.0.0-rc.1") == (25, 0, 0) and parse_version("28.3") == (28, 3)
    assert parse_version("") is None and parse_version(None) is None and parse_version("dev") is None


async def test_a_docker_that_is_too_old_is_a_problem_with_a_way_out(docker_answers):
    docker_answers(docker_info(version="23.0.6"))
    status = await docker_check.check_docker()
    assert not status.ok and status.installed
    assert (
        "23.0.6" in status.error
        and docker_check.MIN_DOCKER_TEXT in status.error
        and "docs.docker.com" in status.hint
    )
    docker_answers(docker_info(version=docker_check.MIN_DOCKER_TEXT + ".0"))
    assert (await docker_check.check_docker()).ok  # the minimum itself is fine


async def test_docker_in_windows_container_mode_is_a_problem_cells_need_linux(docker_answers):
    docker_answers(docker_info(os_type="windows"))
    status = await docker_check.check_docker()
    assert not status.ok and "windows containers" in status.error and "Linux containers" in status.hint


async def test_a_missing_docker_says_where_to_get_it(monkeypatch):
    monkeypatch.setattr(docker_check.shutil, "which", lambda _: None)
    status = await docker_check.check_docker()
    assert (
        not status.installed
        and "docs.docker.com/desktop" in status.hint
        and "docs.docker.com/engine" in status.hint
    )


# ----- the checks -----


@pytest.fixture
def real_docker(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cell_backend", "docker")
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{tmp_path / 'p.db'}")


async def test_cells_cannot_run_without_a_working_docker_but_everything_else_is_a_warning(
    real_docker, monkeypatch
):
    async def broken(host=""):
        return DockerStatus(
            ok=False, installed=True, host="local socket", error="cannot connect", hint="Start Docker"
        )

    monkeypatch.setattr(preflight, "check_docker", broken)
    checks = await preflight.run_checks(AppSettings())
    docker = next(c for c in checks if c.id == "docker")
    assert docker.level == "fail" and docker.hint == "Start Docker" and not preflight.cells_can_run(checks)
    assert not any(c.id == "cell_image" for c in checks)  # nothing to ask a Docker that is not there

    async def working(host=""):
        return DockerStatus(ok=True, installed=True, host="local socket", version="27.1.0", cpus=4)

    async def no_image(args, env, timeout):
        return 1, "", "No such image"

    monkeypatch.setattr(preflight, "check_docker", working)
    monkeypatch.setattr(preflight, "run_command", no_image)
    checks = await preflight.run_checks(AppSettings())
    assert preflight.cells_can_run(checks)
    image = next(c for c in checks if c.id == "cell_image")
    assert image.level == "warn" and "build-images" in image.hint  # a missing image does not stop the app


async def test_simulated_cells_need_no_docker(monkeypatch):
    monkeypatch.setattr(settings, "cell_backend", "fake")
    checks = await preflight.run_checks(AppSettings())
    assert preflight.cells_can_run(checks) and not any(c.id == "docker" for c in checks)
    assert next(c for c in checks if c.id == "cell_backend").level == "warn"


async def test_the_background_check_pauses_cells_and_wakes_the_scheduler_when_docker_returns(
    real_docker, monkeypatch, maker, scheduler, tmp_path
):
    state = {"ok": False}

    async def docker(host=""):
        if state["ok"]:
            return DockerStatus(ok=True, installed=True, host="local socket", version="27.1.0", cpus=4)
        return DockerStatus(ok=False, installed=True, host="local socket", error="cannot connect")

    async def image(args, env, timeout):
        return 0, "", ""

    monkeypatch.setattr(preflight, "check_docker", docker)
    monkeypatch.setattr(preflight, "run_command", image)
    trail = runlog.Trail(tmp_path / "logs")
    trail.begin()
    pre = preflight.Preflight()
    await pre.refresh(maker, scheduler, trail)
    assert (
        not pre.cells_ready
        and not scheduler.cells_ready
        and [c.id for c in pre.problems if c.level == "fail"] == ["docker"]
    )
    scheduler._wake.clear()
    state["ok"] = True
    await pre.refresh(maker, scheduler, trail)
    assert (
        pre.cells_ready and scheduler.cells_ready and scheduler._wake.is_set()
    )  # waiting tasks start at once
    events = [json.loads(line) for line in trail.path.read_text().splitlines()]
    assert [e["event"] for e in events[:2]] == ["start", "preflight"]  # the first look records everything
    changes = {e["id"]: e["level"] for e in events[2:] if e["event"] == "check_changed"}
    assert changes == {
        "docker": "ok",
        "cell_image": "ok",
    }  # then only what changed (the image is only asked once Docker works)


async def test_tasks_wait_while_docker_is_down_and_run_when_it_is_back(client, scheduler):
    await register(client)
    pid = (await make_project(client))["id"]
    task = await make_task(client, pid, status="ready")
    scheduler.cells_ready = False
    assert await scheduler.tick() == 0
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "ready"  # waiting, not failed
    assert (await client.get(f"/api/tasks/{task['id']}/attempts")).json() == []
    scheduler.cells_ready = True
    assert await scheduler.tick() == 1
    await drain(scheduler)
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["status"] == "done"


async def test_the_status_tells_everyone_cells_are_paused_but_only_administrators_why(client):
    await register(client)  # the administrator
    app.state.preflight.cells_ready = False
    app.state.preflight.checks = [preflight.Check("docker", "fail", "Docker: cannot connect", "Start Docker")]
    try:
        status = (await client.get("/api/system/status")).json()
        assert status["cells_ready"] is False and status["problems"][0]["hint"] == "Start Docker"
        assert status["version"]
        await register(client, "b@c.de", "Bob")  # signed in as a user without administrator rights
        member = (await client.get("/api/system/status")).json()
        assert member["cells_ready"] is False and member["problems"] == []
    finally:
        app.state.preflight = preflight.Preflight()


# ----- the trail -----


def test_each_run_leaves_a_trail_and_only_the_last_runs_are_kept(tmp_path):
    for n in range(runlog.RUN_LIMIT + 5):
        trail = runlog.Trail(tmp_path)
        trail.begin()
        trail.event("ready")
        trail.end()
    runs = runlog.read_runs(tmp_path, last=100)
    assert len(runs) == runlog.RUN_LIMIT and all(r.outcome == "stopped cleanly" for r in runs)
    assert runs[-1].newest and not runs[0].newest


def test_the_trail_tells_a_crash_from_a_clean_stop_and_a_failed_start(tmp_path):
    clean = runlog.Trail(tmp_path)
    clean.begin()
    clean.end()
    crashed = runlog.Trail(tmp_path)  # started, never stopped: killed or lost power
    crashed.begin()
    crashed.event("ready")
    failed = runlog.Trail(tmp_path)
    failed.begin()
    failed.event("startup_failed", error="OperationalError: unable to open database file")
    last = runlog.Trail(tmp_path)
    last.begin()
    last.event(
        "preflight",
        checks=[
            {"id": "docker", "level": "fail", "message": "Docker: cannot connect"},
            {"id": "python", "level": "ok", "message": "Python"},
        ],
    )
    outcomes = [(r.outcome, r.failure, r.problems) for r in runlog.read_runs(tmp_path)]
    assert outcomes[0][0] == "stopped cleanly"
    assert "without a clean stop" in outcomes[1][0] and "running now" not in outcomes[1][0]
    assert outcomes[2][:2] == ("failed to start", "OperationalError: unable to open database file")
    assert outcomes[3][0].startswith("running now") and outcomes[3][2] == ["Docker: cannot connect"]


def test_a_line_cut_short_by_a_crash_does_not_hide_the_rest(tmp_path):
    trail = runlog.Trail(tmp_path)
    trail.begin()
    trail.event("ready")
    with trail.path.open("a") as f:
        f.write('{"run": "abc", "event": "sto')  # the power went here
    assert len(runlog.read_runs(tmp_path)) == 1


def test_an_unwritable_trail_never_stops_themis(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    trail = runlog.Trail(blocked / "logs")
    trail.begin()  # must not raise
    trail.event("ready")
    trail.end()


def test_the_log_file_rotates_and_is_set_up_once(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        runlog.setup_file_logging(tmp_path)
        runlog.setup_file_logging(tmp_path)
        added = [h for h in root.handlers if h not in before]
        assert len(added) == 1 and isinstance(added[0], logging.handlers.RotatingFileHandler)
        logging.getLogger("app.test").warning("hello from the test")
        added[0].flush()
        assert "hello from the test" in (tmp_path / "themis.log").read_text()
    finally:
        for h in root.handlers[:]:
            if h not in before:
                root.removeHandler(h)
                h.close()


# ----- the doctor -----


def test_the_doctor_lists_the_checks_and_the_last_runs_and_can_write_a_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "cell_backend", "fake")
    monkeypatch.setattr(settings, "log_dir", tmp_path / "logs")
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{tmp_path / 'd.db'}")
    monkeypatch.setattr(doctor, "_app_settings", lambda: AppSettings())
    monkeypatch.setenv("THEMIS_SECRET_KEY", "super-secret-value-that-must-not-leak")
    trail = runlog.Trail(settings.log_dir)
    trail.begin()
    trail.event("startup_failed", error="boom")
    (settings.log_dir / "themis.log").write_text("2026-01-01 ERROR app: something broke\n")
    report = tmp_path / "report.txt"
    code = doctor.run(["--report", str(report)])
    out = capsys.readouterr().out
    assert (
        code == 0
        and "Recent runs" in out
        and "failed to start" in out
        and "error: boom" in out
        and "Python 3." in out
    )
    text = report.read_text()
    assert (
        "THEMIS_SECRET_KEY" in text and "super-secret-value-that-must-not-leak" not in text
    )  # names, never values
    assert "something broke" in text and "startup_failed" in text and "Version:" in text


def test_the_doctor_fails_when_something_is_broken(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "cell_backend", "docker")
    monkeypatch.setattr(settings, "log_dir", tmp_path / "logs")
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{tmp_path / 'd.db'}")
    monkeypatch.setattr(doctor, "_app_settings", lambda: AppSettings())

    async def broken(cfg, **_):
        return [preflight.Check("docker", "fail", "Docker: cannot connect", "Start Docker Desktop")]

    monkeypatch.setattr(doctor, "run_checks", broken)
    assert doctor.run([]) == 1
    out = capsys.readouterr().out
    assert "cannot connect" in out and "Start Docker Desktop" in out and "1 problem(s)" in out
