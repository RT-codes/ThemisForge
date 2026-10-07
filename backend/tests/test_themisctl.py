"""The control file that installs, upgrades and rolls back Themis (scripts/themisctl.py)."""

import importlib.util
import io
import json
import os
import sqlite3
import tarfile
from pathlib import Path

import pytest

from app import version as app_version

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("themisctl", ROOT / "scripts" / "themisctl.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ctl = load()


# ----- versions: the control file cannot import the app, so its copy of the rule is tested against the app's -----


def test_the_control_file_orders_versions_exactly_like_the_app_does():
    versions = [
        "0.9.0",
        "0.10.0",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
        "1.0.1",
        "2.0.0",
    ]
    assert sorted(versions, key=ctl.sort_key) == sorted(versions, key=app_version.sort_key) == versions
    for bad in ("", "1.0", "latest", "1.0.0."):
        with pytest.raises(ValueError):
            ctl.sort_key(bad)


# ----- finding the release -----


def rel(tag, *, pre=False, draft=False):
    return {"tag_name": tag, "prerelease": pre, "draft": draft, "assets": []}


RELEASES = [
    rel("v0.2.0"),
    rel("v0.3.0-beta.1", pre=True),
    rel("v0.1.0"),
    rel("v0.2.1", draft=True),
    rel("nightly"),
    rel("v0.2.1-rc.1", pre=True),
]


def test_stable_is_the_newest_release_that_is_not_a_pre_release_or_a_draft():
    assert ctl.pick_release(RELEASES)["version"] == "0.2.0"
    assert ctl.pick_release(RELEASES, channel="beta")["version"] == "0.3.0-beta.1"
    assert ctl.pick_release(RELEASES, version="v0.1.0")["version"] == "0.1.0"
    assert ctl.pick_release(RELEASES, version="0.2.1-rc.1")["version"] == "0.2.1-rc.1"
    with pytest.raises(ctl.CtlError, match="no release 9.9.9"):
        ctl.pick_release(RELEASES, version="9.9.9")
    with pytest.raises(ctl.CtlError, match="no stable release"):
        ctl.pick_release([rel("v1.0.0-beta.1", pre=True)])


def test_a_release_without_its_files_says_it_may_not_be_published_yet():
    with pytest.raises(ctl.CtlError, match="not be fully published"):
        ctl.asset({"version": "1.0.0", "assets": []}, "themisforge-1.0.0.tar.gz")


# ----- checking and unpacking a download -----


def make_bundle(path: Path, *, version="1.2.3", extra=None, top=None):
    top = top or f"themisforge-{version}"
    files = {
        "VERSION": f"{version}\n",
        "backend/pyproject.toml": "[project]\n",
        "backend/uv.lock": "",
        "scripts/themisctl.py": "# ctl\n",
        "frontend/dist/index.html": "<html>",
        **(extra or {}),
    }
    with tarfile.open(path, "w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_a_download_that_does_not_match_its_checksum_is_refused(tmp_path):
    bundle = make_bundle(tmp_path / "themisforge-1.2.3.tar.gz")
    good = f"{ctl.sha256_of(bundle)}  {bundle.name}\n"
    ctl.verify_checksum(bundle, good, bundle.name)
    ctl.verify_checksum(
        bundle, f"{ctl.sha256_of(bundle)} *{bundle.name}\n", bundle.name
    )  # the binary-mode spelling
    with pytest.raises(ctl.CtlError, match="does not match"):
        ctl.verify_checksum(bundle, f"{'0' * 64}  {bundle.name}\n", bundle.name)
    with pytest.raises(ctl.CtlError, match="does not list"):
        ctl.verify_checksum(bundle, good, "other.tar.gz")


def test_a_bundle_is_unpacked_without_its_top_folder(tmp_path):
    dest = tmp_path / "out"
    ctl.safe_extract(make_bundle(tmp_path / "b.tar.gz"), dest)
    assert (dest / "VERSION").read_text() == "1.2.3\n" and (dest / "backend" / "uv.lock").is_file()


def test_a_bundle_that_writes_outside_its_folder_is_never_unpacked(tmp_path):
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as tar:
        for name in ("themisforge-1/VERSION", "themisforge-1/../../escaped.txt"):
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ctl.CtlError, match="outside"):
        ctl.safe_extract(bad, tmp_path / "out")
    assert not (tmp_path / "escaped.txt").exists()

    link = tmp_path / "link.tar.gz"
    with tarfile.open(link, "w:gz") as tar:
        info = tarfile.TarInfo("themisforge-1/evil")
        info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(info)
    with pytest.raises(ctl.CtlError, match="not a plain file"):
        ctl.safe_extract(link, tmp_path / "out2")

    two = tmp_path / "two.tar.gz"
    with tarfile.open(two, "w:gz") as tar:
        for name in ("a/x", "b/y"):
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ctl.CtlError, match="one top folder"):
        ctl.safe_extract(two, tmp_path / "out3")


# ----- the home, the link and the releases -----


@pytest.fixture(params=["linux", "windows"])
def home(request, tmp_path, monkeypatch):
    """A home, run through both ways of keeping `current` (a link on Linux, a pointer file on Windows) on any system."""
    windows = request.param == "windows"
    if not windows and os.name == "nt":
        pytest.skip("a link needs privileges that a normal Windows user does not have")
    monkeypatch.setattr(ctl, "WINDOWS", windows)
    h = ctl.Home(tmp_path / "themis")
    h.make_dirs()
    return h


def put_release(home, version):
    folder = home.release_dir(version)
    (folder / "backend" / ".venv").mkdir(parents=True)
    (folder / "VERSION").write_text(version + "\n")
    return folder


def test_the_current_link_is_swapped_in_one_step_and_names_the_running_release(home):
    assert home.current_version() is None
    put_release(home, "1.0.0")
    put_release(home, "1.1.0")
    ctl.link_current(home, "1.0.0")
    assert home.current_version() == "1.0.0"
    ctl.link_current(home, "1.1.0")
    assert home.current_version() == "1.1.0"
    assert (
        not (home.root / "current.new").exists() and not (home.root / "current.txt.new").exists()
    )  # nothing half done
    with pytest.raises(ctl.CtlError, match="not on this machine"):
        ctl.link_current(home, "9.9.9")


def test_old_releases_are_pruned_but_the_running_one_and_the_one_before_stay(home):
    for v in ("0.1.0", "0.2.0", "0.3.0", "0.4.0"):
        put_release(home, v)
    (home.releases / "0.5.0.partial").mkdir()  # an interrupted unpack is not a release
    ctl.link_current(home, "0.4.0")
    assert ctl.prune(home) == ["0.1.0", "0.2.0"]
    assert home.installed() == ["0.3.0", "0.4.0"]
    ctl.link_current(
        home, "0.3.0"
    )  # a rollback: the newest is not the running one, and is the one that stays
    assert ctl.prune(home) == []


# ----- settings -----


def test_the_secret_key_is_made_once_and_never_replaced(home):
    assert ctl.write_config_env(home, host="127.0.0.1", port=8000, https=False) is True
    first = ctl.read_env_file(home.config_env)
    assert (
        len(first["THEMIS_SECRET_KEY"]) == 64
        and first["THEMIS_PORT"] == "8000"
        and "THEMIS_COOKIE_SECURE" not in first
    )
    if os.name != "nt":  # Windows has no such modes: the file is private to the user's own profile folder
        assert oct(home.config_env.stat().st_mode)[-3:] == "600"
    assert ctl.write_config_env(home, host="0.0.0.0", port=9000, https=True) is False
    again = ctl.read_env_file(home.config_env)
    assert (
        again["THEMIS_SECRET_KEY"] == first["THEMIS_SECRET_KEY"]
    )  # stored keys could no longer be decrypted otherwise
    assert (again["THEMIS_HOST"], again["THEMIS_PORT"], again["THEMIS_COOKIE_SECURE"]) == (
        "0.0.0.0",
        "9000",
        "true",
    )
    home.config_env.write_text(
        "THEMIS_SECRET_KEY=change-me-to-a-long-random-string\n# a comment\nTHEMIS_X=1\n"
    )
    assert (
        ctl.write_config_env(home, host="127.0.0.1", port=8000, https=False) is True
    )  # a placeholder is not a key
    assert ctl.read_env_file(home.config_env)["THEMIS_X"] == "1"  # what else was there is kept


def test_the_service_runs_as_the_installing_user_with_the_docker_group(home):
    unit = ctl.render_unit(home, "rowan", ["docker"])
    assert "User=rowan" in unit and "SupplementaryGroups=docker" in unit
    assert (
        f"Environment=THEMIS_HOME={home.root}" in unit
        and f"ExecStart={home.current}/backend/.venv/bin/python -m app.run" in unit
    )
    assert "Restart=always" in unit and "SupplementaryGroups" not in ctl.render_unit(home, "rowan", [])


# ----- backups -----


def test_a_backup_holds_a_consistent_database_and_the_settings_and_can_be_restored(home):
    db = sqlite3.connect(home.db)
    db.execute("create table t (v text)")
    db.execute("insert into t values ('before')")
    db.commit()
    db.close()
    home.config_env.write_text("THEMIS_SECRET_KEY=k1\n")
    saved = ctl.backup(home, "pre-1.0-to-2.0")
    assert saved.parent == home.backups and saved.name.startswith("pre-1.0-to-2.0-")
    db = sqlite3.connect(home.db)
    db.execute("update t set v = 'after the new version changed it'")
    db.commit()
    db.close()
    home.config_env.write_text("THEMIS_SECRET_KEY=k2\n")
    Path(str(home.db) + "-wal").write_text("stale")
    ctl.restore(home, saved)
    assert sqlite3.connect(home.db).execute("select v from t").fetchone() == ("before",)
    assert (
        home.config_env.read_text() == "THEMIS_SECRET_KEY=k1\n" and not Path(str(home.db) + "-wal").exists()
    )


# ----- asking -----


def test_a_question_is_answered_yes_by_the_flag_and_no_when_nobody_can_answer(monkeypatch):
    assert ctl.ask("Install?", yes=True) is True
    monkeypatch.setattr(ctl.sys, "stdin", io.StringIO(""))  # not a terminal
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError("no tty")))
    assert ctl.ask("Install?") is False and ctl.ask("Go on?", default=True) is True


# ----- upgrading, and going back -----


class Machine:
    """Stands in for the computer: records what the service was told, and decides whether the new release comes up."""

    def __init__(self, ctl_module, home, monkeypatch, *, comes_up):
        self.calls, self.comes_up, self.ctl, self.home = [], comes_up, ctl_module, home
        self.releases = [{**rel("v1.0.0"), "assets": []}, {**rel("v1.1.0"), "assets": []}]
        monkeypatch.setattr(ctl_module, "check_platform", lambda: None)
        monkeypatch.setattr(ctl_module, "list_releases", lambda: self.releases)
        monkeypatch.setattr(ctl_module, "service_installed", lambda: True)
        monkeypatch.setattr(ctl_module, "service_active", lambda: True)
        monkeypatch.setattr(
            ctl_module, "service_action", lambda home, action, check=True: self.calls.append((action,))
        )
        monkeypatch.setattr(ctl_module, "ensure_docker", lambda *a, **k: None)
        monkeypatch.setattr(ctl_module, "get_cell_image", lambda *a, **k: None)
        monkeypatch.setattr(
            ctl_module, "stage_release", lambda home, release=None, **k: put_release(home, release["version"])
        )
        monkeypatch.setattr(ctl_module, "wait_until_up", self.up)

    def up(self, port, version, seconds=45):
        self.calls.append(("up?", version))
        return self.comes_up(version)


def run_upgrade(ctl_module, home, *argv):
    args = ctl_module.build_parser().parse_args(["upgrade", "--yes", *argv])
    ctl_module.cmd_upgrade(args, home)


def installed_at(home, version, text="v1 data"):
    put_release(home, version)
    ctl.link_current(home, version)
    db = sqlite3.connect(home.db)
    db.execute("create table t (v text)")
    db.execute("insert into t values (?)", (text,))
    db.commit()
    db.close()
    home.config_env.write_text("THEMIS_PORT=8000\n")
    home.save_state(version=version, channel="stable")


def test_an_upgrade_backs_up_switches_and_keeps_the_old_release_for_a_rollback(home, monkeypatch):
    installed_at(home, "1.0.0")
    machine = Machine(ctl, home, monkeypatch, comes_up=lambda v: True)
    run_upgrade(ctl, home)
    assert (
        home.current_version() == "1.1.0"
        and home.state()["version"] == "1.1.0"
        and home.state()["previous"] == "1.0.0"
    )
    assert home.installed() == ["1.0.0", "1.1.0"]
    assert [c[0] for c in machine.calls if c[0] != "up?"] == ["stop", "restart"]
    (saved,) = list(home.backups.iterdir())
    assert saved.name.startswith("pre-1.0.0-to-1.1.0-") and (saved / "themisforge.db").is_file()


def test_an_upgrade_that_does_not_come_up_goes_back_and_restores_the_database(home, monkeypatch):
    installed_at(home, "1.0.0")
    machine = Machine(
        ctl, home, monkeypatch, comes_up=lambda v: v == "1.0.0"
    )  # only the old one ever answers

    def new_version_changes_the_database(*a, **k):
        db = sqlite3.connect(home.db)
        db.execute("update t set v = 'migrated by 1.1.0'")
        db.commit()
        db.close()

    monkeypatch.setattr(
        ctl,
        "link_current",
        lambda h, v, _real=ctl.link_current: (
            _real(h, v),
            new_version_changes_the_database() if v == "1.1.0" else None,
        ),
    )
    with pytest.raises(ctl.CtlError, match="Themis 1.0.0 is running again"):
        run_upgrade(ctl, home)
    assert home.current_version() == "1.0.0"
    assert sqlite3.connect(home.db).execute("select v from t").fetchone() == (
        "v1 data",
    )  # as it was before the attempt
    assert ("up?", "1.0.0") in machine.calls and home.state()["version"] == "1.0.0"


def test_upgrade_check_only_looks_and_a_current_install_is_left_alone(home, monkeypatch, capsys):
    installed_at(home, "1.0.0")
    machine = Machine(ctl, home, monkeypatch, comes_up=lambda v: True)
    run_upgrade(ctl, home, "--check")
    assert (
        "1.1.0 is available (you have 1.0.0)" in capsys.readouterr().out and home.current_version() == "1.0.0"
    )
    run_upgrade(ctl, home)
    machine.calls.clear()
    run_upgrade(ctl, home)  # already the newest
    assert machine.calls == [] and "newest" in capsys.readouterr().out


def test_nothing_installed_says_how_to_install(home, monkeypatch):
    monkeypatch.setattr(ctl, "check_platform", lambda: None)
    with pytest.raises(ctl.CtlError, match="themis install"):
        ctl.cmd_upgrade(ctl.build_parser().parse_args(["upgrade"]), home)


def test_the_installed_files_include_this_control_file():
    """The shim runs scripts/themisctl.py of the current release, so the bundle must carry it."""
    spec = importlib.util.spec_from_file_location("build_release", ROOT / "scripts" / "build_release.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    assert "scripts/themisctl.py" in build.INCLUDE
    assert json.loads(json.dumps(sorted(build.INCLUDE)))  # a plain list of paths


def test_the_home_can_be_given_before_or_after_the_command():
    """`install.sh --home X` hands its options to `themis install`, so --home must work after the command too."""
    parse = ctl.build_parser().parse_args
    assert parse(["--home", "/a", "install"]).home == "/a"
    assert parse(["install", "--home", "/b", "--port", "8010"]).home == "/b"
    assert parse(["upgrade", "--check", "--home", "/c"]).home == "/c"
    assert parse(["--home", "/first", "status"]).home == "/first"  # not erased by the command's own default
    assert getattr(parse(["status"]), "home", None) is None


# ----- Windows: the pieces, checked from any system (the platform is a switch in the module) -----


@pytest.fixture
def windows(monkeypatch, tmp_path):
    monkeypatch.setattr(ctl, "WINDOWS", True)
    return ctl.Home(
        tmp_path / "Themis Home (work)"
    )  # a space and parentheses: normal in a Windows user's folders


def test_the_launcher_reads_which_release_is_current_each_time_and_keeps_its_output(windows):
    text = ctl.windows_launcher(windows)
    root = str(windows.root)
    assert (
        text.startswith("@echo off\r\n") and "\r\n" in text and "\n" not in text.replace("\r\n", "")
    )  # real batch line endings
    assert (
        f'set "THEMIS_HOME={root}"' in text and "set PYTHONUTF8=1" in text
    )  # UTF-8 whatever the system's code page
    assert f'set /p THEMIS_V=<"{root}\\current.txt"' in text  # an upgrade changes the file, not the task
    assert '\\releases\\%THEMIS_V%\\backend\\.venv\\Scripts\\python.exe" -m app.run' in text
    assert f'"{root}\\logs\\service.log" 2>&1' in text


def test_the_command_runs_the_current_release_and_says_so_when_nothing_is_installed(windows):
    text = ctl.windows_shim(windows)
    assert "%*" in text and "themisctl.py" in text and "goto missing" in text and ":missing" in text
    assert "if not exist" in text and "(" not in text.split("goto missing")[0].replace(
        str(windows.root), ""
    )  # no blocks to break on a ( in a path


def test_the_scheduled_task_runs_for_this_user_at_logon_in_their_session_and_restarts_itself(windows):
    import xml.etree.ElementTree as ET

    runner = windows.root / "bin" / "themis-run.vbs"
    xml = ctl.windows_task_xml(runner, "PC\\Ro&wan <dev>")  # characters that must be escaped
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    root = ET.fromstring(xml.split("?>", 1)[1])  # well formed, once escaped
    assert root.find("t:Triggers/t:LogonTrigger/t:UserId", ns).text == "PC\\Ro&wan <dev>"
    assert (
        root.find("t:Principals/t:Principal/t:LogonType", ns).text == "InteractiveToken"
    )  # Docker Desktop lives in the session
    assert (
        root.find("t:Principals/t:Principal/t:RunLevel", ns).text == "LeastPrivilege"
    )  # no administrator rights
    assert root.find("t:Settings/t:ExecutionTimeLimit", ns).text == "PT0S"  # a server has no time limit
    assert root.find("t:Settings/t:RestartOnFailure/t:Count", ns).text == "999"
    # no console window: Windows Script Host starts the hidden runner (a .cmd started by the task opens a visible window)
    assert root.find("t:Actions/t:Exec/t:Command", ns).text == "wscript.exe"
    assert root.find("t:Actions/t:Exec/t:Arguments", ns).text == f'//B //Nologo "{runner}"'


def test_the_runner_starts_the_launcher_with_its_window_hidden_and_waits_for_it(windows):
    launcher = windows.root / "bin" / "themis-run.cmd"
    text = ctl.windows_hidden_runner(launcher)
    assert text.count("\r\n") == 4 and "\n" not in text.replace("\r\n", "")  # real script line endings
    assert (
        f'shell.Run("""{launcher}""", 0, True)' in text
    )  # style 0: hidden; True: wait, so the task stays "running" with Themis
    assert text.rstrip().endswith("WScript.Quit code")  # the launcher's exit code reaches the task


def test_the_current_release_on_windows_is_named_by_a_pointer_file(windows):
    (windows.release_dir("1.2.3")).mkdir(parents=True)
    assert windows.current_version() is None
    with pytest.raises(ctl.CtlError, match="themis install"):
        windows.current_path()
    ctl.link_current(windows, "1.2.3")
    assert windows.current_file.read_text() == "1.2.3\n" and windows.current_path() == windows.release_dir(
        "1.2.3"
    )
    windows.current_file.write_text("1.9.9\n")  # names a release that is not there: nothing is installed
    assert windows.current_version() is None
    windows.current_file.write_text("not a version")
    assert windows.current_version() is None
    python = windows.python(windows.release_dir("1.2.3"))
    assert (
        python.name == "python.exe" and python.parent.name == "Scripts"
    )  # the layout of a virtualenv on Windows


def test_the_service_is_a_task_that_is_ended_then_the_server_stopped_by_its_process_id(windows, monkeypatch):
    calls = []
    monkeypatch.setattr(
        ctl,
        "_schtasks",
        lambda *a, check=True: (
            calls.append(("schtasks", *a)) or type("R", (), {"stdout": "", "returncode": 0})()
        ),
    )
    monkeypatch.setattr(
        ctl,
        "run",
        lambda cmd, **k: calls.append(("run", *cmd)) or type("R", (), {"stdout": "", "returncode": 0})(),
    )
    monkeypatch.setattr(ctl, "port_in_use", lambda port: False)
    windows.root.mkdir(parents=True)
    windows.pid_file.write_text("4242\n")
    ctl.service_action(windows, "restart")
    assert [c[:3] for c in calls if c[0] == "schtasks"] == [
        ("schtasks", "/End", "/TN"),
        ("schtasks", "/Run", "/TN"),
    ]
    assert ("run", "taskkill", "/PID", "4242", "/T", "/F") in calls and not windows.pid_file.exists()
    calls.clear()
    ctl.service_action(windows, "start")
    assert calls == [("schtasks", "/Run", "/TN", "Themis")]  # starting does not stop anything first


def test_a_task_that_reports_running_is_active(windows, monkeypatch):
    out = "Folder: \\\nTaskName: \\Themis\nStatus:     Running\n"
    monkeypatch.setattr(
        ctl, "_schtasks", lambda *a, check=True: type("R", (), {"stdout": out, "returncode": 0})()
    )
    assert ctl.service_installed() and ctl.service_active()
    monkeypatch.setattr(
        ctl,
        "_schtasks",
        lambda *a, check=True: type("R", (), {"stdout": out.replace("Running", "Ready"), "returncode": 0})(),
    )
    assert not ctl.service_active()
    monkeypatch.setattr(
        ctl, "_schtasks", lambda *a, check=True: type("R", (), {"stdout": "", "returncode": 1})()
    )
    assert not ctl.service_installed()


def test_the_installer_refuses_an_elevated_window_on_windows(windows, monkeypatch):
    monkeypatch.setattr(ctl.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(ctl, "is_elevated", lambda: True)
    with pytest.raises(ctl.CtlError, match="not as administrator"):
        ctl.check_platform()
    monkeypatch.setenv("THEMIS_ALLOW_ELEVATED", "1")  # the way around for CI runners and containers
    ctl.check_platform()
    monkeypatch.delenv("THEMIS_ALLOW_ELEVATED")
    monkeypatch.setattr(ctl, "is_elevated", lambda: False)
    ctl.check_platform()  # a normal window is fine
    monkeypatch.setattr(ctl.platform, "machine", lambda: "riscv64")
    with pytest.raises(ctl.CtlError, match="not supported"):
        ctl.check_platform()


def docker_report(**docker):
    ok = bool(docker.pop("ok", False))
    return {
        "checks": [] if ok else [{"id": "docker", "level": "fail", "message": "Docker: x", "hint": "do y"}],
        "docker": docker,
    }


def test_without_docker_desktop_windows_offers_winget_and_then_stops_so_it_can_be_started(
    windows, monkeypatch
):
    monkeypatch.setattr(ctl, "doctor_json", lambda *a, **k: docker_report(installed=False))
    ran = []
    monkeypatch.setattr(ctl, "run", lambda cmd, **k: ran.append(cmd))
    monkeypatch.setattr(ctl.shutil, "which", lambda name: "C:\\winget.exe" if name == "winget" else None)
    with pytest.raises(ctl.CtlError, match="Start it from the Start menu"):
        ctl.ensure_docker(windows, windows.root, yes=True)
    assert ran == [
        [
            "winget",
            "install",
            "-e",
            "--id",
            "Docker.DockerDesktop",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
    ]
    ran.clear()
    with pytest.raises(ctl.CtlError, match="docs.docker.com/desktop"):  # declined: where to get it
        ctl.ensure_docker(windows, windows.root, yes=False)
    assert ran == []
    monkeypatch.setattr(ctl.shutil, "which", lambda name: None)  # no winget either
    with pytest.raises(ctl.CtlError, match="docs.docker.com/desktop"):
        ctl.ensure_docker(windows, windows.root, yes=True)


def test_docker_desktop_that_is_installed_but_not_running_is_started_and_waited_for(windows, monkeypatch):
    monkeypatch.setattr(ctl, "doctor_json", lambda *a, **k: docker_report(installed=True, version=None))
    monkeypatch.setattr(
        ctl,
        "wait_for_docker_desktop",
        lambda *a, **k: docker_report(ok=True, installed=True, version="29.7.2"),
    )
    ctl.ensure_docker(windows, windows.root, yes=True)  # no error: it came up
    monkeypatch.setattr(
        ctl, "wait_for_docker_desktop", lambda *a, **k: docker_report(installed=True, version=None)
    )
    with pytest.raises(ctl.CtlError, match="Docker is not usable"):
        ctl.ensure_docker(windows, windows.root, yes=True)


def test_docker_desktop_in_windows_container_mode_is_explained_not_started(windows, monkeypatch):
    monkeypatch.setattr(
        ctl, "doctor_json", lambda *a, **k: docker_report(installed=True, version="29.7.2", os_type="windows")
    )
    monkeypatch.setattr(
        ctl, "wait_for_docker_desktop", lambda *a, **k: pytest.fail("starting it would not help")
    )
    with pytest.raises(ctl.CtlError, match="Docker is not usable"):
        ctl.ensure_docker(windows, windows.root, yes=True)


def test_the_foreground_server_ends_with_its_exit_code_on_windows(windows, monkeypatch):
    windows.release_dir("1.0.0").mkdir(parents=True)
    ctl.link_current(windows, "1.0.0")
    seen = {}

    def fake_run(cmd, env, cwd, check):
        seen.update(cmd=cmd, env=env, cwd=cwd)
        return type("R", (), {"returncode": 3})()

    monkeypatch.setattr(ctl.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as stop:
        ctl.run_app(windows, "app.run", [])
    assert stop.value.code == 3 and seen["cmd"][1:] == ["-m", "app.run"] and seen["env"]["PYTHONUTF8"] == "1"
    assert (
        seen["env"]["THEMIS_HOME"] == str(windows.root)
        and seen["cwd"] == windows.release_dir("1.0.0") / "backend"
    )


def test_a_folder_added_to_the_users_path_is_quoted_for_powershell_and_only_once(monkeypatch):
    seen = []
    monkeypatch.setattr(
        ctl,
        "powershell",
        lambda script, check=True: seen.append(script) or type("R", (), {"stdout": "added\n"})(),
    )
    assert ctl.add_to_user_path(Path("C:/Users/O'Brien/AppData/Local/Themis/bin")) is True
    folder = str(Path("C:/Users/O'Brien/AppData/Local/Themis/bin")).replace("'", "''")
    assert f"'{folder}'" in seen[0]  # an apostrophe in a name cannot end the quoted string
    monkeypatch.setattr(ctl, "powershell", lambda script, check=True: type("R", (), {"stdout": ""})())
    assert ctl.add_to_user_path(Path("C:/x")) is False  # it was already there


def test_running_the_installer_again_reuses_the_release_that_is_there_even_if_it_cannot_be_replaced(
    home, monkeypatch
):
    """On Windows a running Themis holds its files, so a repair run must not try to delete and unpack them again."""
    bundle = make_bundle(home.root / "themisforge-1.2.3.tar.gz")
    ran = []
    monkeypatch.setattr(ctl, "find_uv", lambda: "uv")
    monkeypatch.setattr(ctl, "run", lambda cmd, **k: (ran.append(cmd), (k["cwd"] / ".venv").mkdir())[0])
    first = ctl.stage_release(home, bundle=bundle)
    assert first == home.release_dir("1.2.3") and len(ran) == 1 and (first / "VERSION").is_file()
    monkeypatch.setattr(
        ctl.shutil, "rmtree", lambda *a, **k: pytest.fail("a release in use must not be deleted")
    )
    assert ctl.stage_release(home, bundle=bundle) == first and len(ran) == 1  # reused, nothing run


def test_a_leftover_that_cannot_be_removed_says_to_stop_themis(home, monkeypatch):
    bundle = make_bundle(home.root / "themisforge-2.0.0.tar.gz", version="2.0.0")
    stuck = home.release_dir("2.0.0")
    stuck.mkdir(parents=True)  # incomplete (no environment) and, as on Windows, impossible to delete
    monkeypatch.setattr(ctl.shutil, "rmtree", lambda *a, **k: None)
    with pytest.raises(ctl.CtlError, match="Stop Themis"):
        ctl.stage_release(home, bundle=bundle)


def test_the_installer_always_says_when_it_is_waiting_for_docker_desktop(windows, monkeypatch, capsys):
    """A silent wait looked like a frozen installer: it must say what it waits for, start Docker Desktop when it can,
    and report progress."""
    clock = {"now": 0.0}
    monkeypatch.setattr(ctl.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(ctl.time, "sleep", lambda s: clock.__setitem__("now", clock["now"] + s))
    answers = iter(
        [docker_report(installed=True, version=None)] * 6
        + [docker_report(ok=True, installed=True, version="29.7.2")]
    )
    monkeypatch.setattr(ctl, "doctor_json", lambda *a, **k: next(answers))
    started = []
    exe = windows.root / "Docker Desktop.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(ctl, "find_docker_desktop", lambda: exe)
    monkeypatch.setattr(ctl.subprocess, "Popen", lambda cmd, **k: started.append(cmd))
    report = ctl.wait_for_docker_desktop(windows, windows.root, seconds=120)
    out = capsys.readouterr().out
    assert ctl.docker_problem(report) is None and started == [[str(exe)]]
    assert (
        "installed, but it is not running" in out
        and "starting it for you" in out
        and "still waiting for Docker" in out
    )
    assert "Start Docker Desktop when you sign in" in out  # the tip that stops it happening after a restart


def test_when_docker_desktop_cannot_be_found_the_person_is_told_to_start_it(windows, monkeypatch, capsys):
    monkeypatch.setattr(ctl, "find_docker_desktop", lambda: None)
    monkeypatch.setattr(
        ctl, "doctor_json", lambda *a, **k: docker_report(ok=True, installed=True, version="29.7.2")
    )
    ctl.wait_for_docker_desktop(windows, windows.root)
    assert "start it from the Start menu" in capsys.readouterr().out


def test_docker_desktop_is_found_next_to_its_command_or_in_the_usual_folders(windows, monkeypatch, tmp_path):
    install = tmp_path / "Docker" / "Docker"
    (install / "resources" / "bin").mkdir(parents=True)
    (install / "Docker Desktop.exe").write_text("")
    (install / "resources" / "bin" / "docker.exe").write_text("")
    monkeypatch.setattr(ctl.shutil, "which", lambda name: str(install / "resources" / "bin" / "docker.exe"))
    assert ctl.find_docker_desktop() == install / "Docker Desktop.exe"
    monkeypatch.setattr(ctl.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert ctl.find_docker_desktop() == install / "Docker Desktop.exe"
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "nowhere"))
    assert ctl.find_docker_desktop() is None


def test_a_docker_command_in_a_short_path_does_not_break_the_search_for_docker_desktop(monkeypatch):
    monkeypatch.setattr(ctl.shutil, "which", lambda name: "docker.exe")
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert ctl.find_docker_desktop() is None  # no folder above it to look in, and no error
