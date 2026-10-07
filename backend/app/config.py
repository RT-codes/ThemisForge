import os
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SECRET_KEY = "dev-insecure-secret-change-me-0123456789"


def _env_files() -> tuple[str, ...]:
    """The files settings are read from, later ones winning: .env beside where the server is started (development), and
    config.env in the install's home, which `themis install` writes (see themisctl.py)."""
    home = os.environ.get("THEMIS_HOME", "").strip()
    return (".env", str(Path(home).expanduser() / "config.env")) if home else (".env",)


class Settings(BaseSettings):
    """Bootstrap config: read from the environment / .env before the app can start.

    Everything an operator edits while the app is running lives in the database instead
    (see app/app_settings.py).
    """

    model_config = SettingsConfigDict(env_prefix="THEMIS_", env_file=_env_files(), extra="ignore")

    # An installed Themis keeps everything that is its own (database, projects, logs, settings, the code of each release)
    # under one home folder, apart from the code, so an upgrade swaps the code and never touches the data. A git
    # checkout has no home and keeps these next to the code, as before.
    home: Path | None = None
    # What `python -m app.run` listens on (the installer sets these; the default is this machine only)
    host: str = "127.0.0.1"
    port: int = 8000

    database_url: str = f"sqlite+aiosqlite:///{BACKEND_DIR / 'themisforge.db'}"
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_minutes: int = 60 * 24 * 7
    cookie_secure: bool = False
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    # Where per-project workspaces and artifacts live (mounted into cells).
    data_dir: Path = BACKEND_DIR.parent / "data"

    # Where the run trail (runs.jsonl: what happened at each start) and the rotating application log are written.
    log_dir: Path = BACKEND_DIR.parent / "logs"

    # Where Themis looks for newer releases (the same variable `themis upgrade` reads; tests and mirrors change it).
    release_api: str = "https://api.github.com/repos/RT-codes/ThemisForge"

    # "docker" runs real containers, "fake" simulates a cell (development and tests).
    cell_backend: str = "docker"
    # Where "Connect Codex" signs in: "container" runs Codex's sign-in inside the cell image (nothing to install on this
    # machine), "host" runs a Codex CLI installed here (development).
    codex_login: str = "container"
    # The Codex CLI used when codex_login is "host". Set a full path if it is not on PATH (on Windows, e.g. codex.cmd).
    codex_bin: str = "codex"
    scheduler_enabled: bool = True
    scheduler_interval_seconds: float = 3.0

    @model_validator(mode="after")
    def _keep_state_under_home(self) -> "Settings":
        """With a home, the database, data and logs live in it, unless one of them was set explicitly."""
        if self.home is None:
            return self
        self.home = self.home.expanduser().resolve()
        placed = {
            "database_url": f"sqlite+aiosqlite:///{(self.home / 'db' / 'themisforge.db').as_posix()}",
            "data_dir": self.home / "data",
            "log_dir": self.home / "logs",
        }
        for name, value in placed.items():
            if name not in self.model_fields_set:
                setattr(self, name, value)
        return self

    def ensure_state_dirs(self) -> None:
        """The folders the server writes to exist before it needs them (the database file's folder, for one)."""
        from sqlalchemy.engine import make_url

        for folder in (self.data_dir, self.log_dir):
            folder.mkdir(parents=True, exist_ok=True)
        if (db := make_url(self.database_url).database) and make_url(
            self.database_url
        ).get_backend_name() == "sqlite":
            Path(db).parent.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: int) -> Path:
        """Everything on disk that belongs to one project: its folders, and its config (see app/project_config.py)."""
        return self.data_dir / "projects" / str(project_id)


settings = Settings()
