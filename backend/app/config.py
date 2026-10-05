from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SECRET_KEY = "dev-insecure-secret-change-me-0123456789"


class Settings(BaseSettings):
    """Bootstrap config: read from the environment / .env before the app can start.

    Everything an operator edits while the app is running lives in the database instead
    (see app/app_settings.py).
    """

    model_config = SettingsConfigDict(env_prefix="THEMIS_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite+aiosqlite:///{BACKEND_DIR / 'themisforge.db'}"
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_minutes: int = 60 * 24 * 7
    cookie_secure: bool = False
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    # Where per-project workspaces and artifacts live (mounted into cells).
    data_dir: Path = BACKEND_DIR.parent / "data"

    # "docker" runs real containers, "fake" simulates a cell (development and tests).
    cell_backend: str = "docker"
    scheduler_enabled: bool = True
    scheduler_interval_seconds: float = 3.0


settings = Settings()
