from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="THEMIS_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite+aiosqlite:///{BACKEND_DIR / 'themisforge.db'}"
    secret_key: str = "dev-insecure-secret-change-me-0123456789"
    access_token_minutes: int = 60 * 24 * 7
    cookie_secure: bool = False
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"


settings = Settings()
