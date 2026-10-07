"""An installed Themis keeps its own things under one home folder, apart from its code (app/config.py)."""

from pathlib import Path

import pytest

from app import config, run, volumes
from app.app_settings import MountRoot
from app.config import Settings


def test_with_a_home_everything_that_is_ours_lives_in_it(tmp_path):
    s = Settings(home=tmp_path / "themis")
    home = (tmp_path / "themis").resolve()
    assert s.database_url == f"sqlite+aiosqlite:///{(home / 'db' / 'themisforge.db').as_posix()}"
    assert (s.data_dir, s.log_dir) == (home / "data", home / "logs")


def test_a_setting_given_explicitly_wins_over_the_home(tmp_path):
    s = Settings(
        home=tmp_path / "themis", data_dir=tmp_path / "elsewhere", database_url="sqlite+aiosqlite:///x.db"
    )
    assert (
        s.data_dir == tmp_path / "elsewhere"
        and s.database_url.endswith("x.db")
        and s.log_dir == (tmp_path / "themis").resolve() / "logs"
    )


def test_without_a_home_a_checkout_keeps_its_state_beside_the_code():
    s = Settings()
    assert (
        s.home is None
        and s.data_dir == config.BACKEND_DIR.parent / "data"
        and s.log_dir == config.BACKEND_DIR.parent / "logs"
    )
    assert Path(s.database_url.removeprefix("sqlite+aiosqlite:///")) == config.BACKEND_DIR / "themisforge.db"


def test_the_install_reads_its_settings_from_config_env_in_the_home(monkeypatch, tmp_path):
    monkeypatch.delenv("THEMIS_HOME", raising=False)
    assert config._env_files() == (".env",)
    monkeypatch.setenv("THEMIS_HOME", str(tmp_path))
    assert config._env_files() == (".env", str(tmp_path / "config.env"))


def test_the_state_folders_are_made_when_the_server_starts(tmp_path):
    s = Settings(home=tmp_path / "themis")
    s.ensure_state_dirs()
    home = (tmp_path / "themis").resolve()
    assert (home / "data").is_dir() and (home / "logs").is_dir() and (home / "db").is_dir()
    s.ensure_state_dirs()  # again is fine


def test_the_home_with_the_secret_key_and_the_code_can_never_be_mounted_into_a_cell(tmp_path, monkeypatch):
    home = tmp_path / "themis"
    (home / "releases").mkdir(parents=True)
    (home / "config.env").write_text("THEMIS_SECRET_KEY=x")
    monkeypatch.setattr(config, "settings", Settings(home=home))
    monkeypatch.setattr(volumes, "settings", config.settings)
    for inside in (home, home / "releases", home / "data"):
        inside.mkdir(parents=True, exist_ok=True)
        with pytest.raises(volumes.MountError, match="Themis's own data"):
            volumes.host_target(str(inside), [MountRoot(path=str(tmp_path), allow_write=True)])
    # a folder next to it is fine
    other = tmp_path / "notes"
    other.mkdir()
    assert (
        volumes.host_target(str(other), [MountRoot(path=str(tmp_path), allow_write=True)])[0]
        == other.resolve()
    )


def test_the_service_entry_point_listens_where_the_settings_say(monkeypatch):
    seen = {}
    monkeypatch.setattr(run.uvicorn, "run", lambda app, **kw: seen.update(app=app, **kw))
    monkeypatch.setattr(run, "settings", Settings(host="0.0.0.0", port=9001))
    run.main()
    assert seen == {"app": "app.main:app", "host": "0.0.0.0", "port": 9001}
    assert Path(run.__file__).name == "run.py"
