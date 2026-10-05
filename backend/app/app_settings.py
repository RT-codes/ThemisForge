from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AppSetting

_KEY = "app"


class AppSettings(BaseModel):
    """Operator settings edited from the Settings page (stored as one JSON row)."""

    timezone: str = "UTC"  # cron schedules are evaluated in this zone
    docker_host: str = ""  # empty = the local Docker socket; e.g. ssh://user@host or tcp://host:2376
    cell_image: str = "alpine:3"
    cell_cpus: float = Field(default=1.0, gt=0, le=64)
    cell_memory_mb: int = Field(default=1024, ge=64, le=1_048_576)
    cell_timeout_seconds: int = Field(default=3600, ge=10, le=86_400)
    max_concurrent_cells: int = Field(default=2, ge=1, le=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Unknown timezone: {v}") from None
        return v

    @field_validator("docker_host")
    @classmethod
    def valid_docker_host(cls, v: str) -> str:
        v = v.strip()
        if v and not v.startswith(("unix://", "tcp://", "ssh://")):
            raise ValueError("Docker host must start with unix://, tcp:// or ssh://")
        return v

    @field_validator("cell_image")
    @classmethod
    def valid_image(cls, v: str) -> str:
        v = v.strip()
        if not v or v.startswith("-") or any(c.isspace() for c in v):
            raise ValueError("Invalid image name")
        return v


async def load_settings(session: AsyncSession) -> AppSettings:
    row = await session.get(AppSetting, _KEY)
    return AppSettings.model_validate(row.value) if row else AppSettings()


async def save_settings(session: AsyncSession, value: AppSettings) -> AppSettings:
    row = await session.get(AppSetting, _KEY)
    if row is None:
        session.add(AppSetting(key=_KEY, value=value.model_dump()))
    else:
        row.value = value.model_dump()
    await session.commit()
    return value
