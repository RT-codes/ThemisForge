"""Cell profiles: what size and image a cell gets.

The global defaults live in Settings. A project, an agent and a single run can each override some of them; only the
fields that differ are stored, so a default changed later still reaches everything that did not override it.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .app_settings import AppSettings


class ProfileOverrides(BaseModel):
    """The parts of a cell profile a project, agent or run may change. Empty fields are not overridden."""

    model_config = ConfigDict(extra="forbid")

    image: str | None = None
    cpus: float | None = Field(default=None, gt=0, le=64)
    memory_mb: int | None = Field(default=None, ge=64, le=1_048_576)
    timeout_seconds: int | None = Field(default=None, ge=10, le=86_400)

    @field_validator("image")
    @classmethod
    def valid_image(cls, v: str | None) -> str | None:
        if v is None or not (v := v.strip()):
            return None
        if v.startswith("-") or any(c.isspace() for c in v):
            raise ValueError("Invalid image name")
        return v

    def clean(self) -> dict[str, Any] | None:
        """What is stored: only the fields that are set, or None when nothing is overridden."""
        return self.model_dump(exclude_none=True) or None


@dataclass(frozen=True)
class Profile:
    image: str
    cpus: float
    memory_mb: int
    timeout_seconds: int


def resolve_profile(cfg: AppSettings, default_image: str, *layers: dict[str, Any] | None) -> Profile:
    """The global defaults, then each layer on top of it in order (project, agent, run). The image a harness
    needs (Codex brings its own) is the default image, so only an explicit override replaces it."""
    values: dict[str, Any] = {
        "image": default_image,
        "cpus": cfg.cell_cpus,
        "memory_mb": cfg.cell_memory_mb,
        "timeout_seconds": cfg.cell_timeout_seconds,
    }
    for layer in layers:
        for key, value in (layer or {}).items():
            if key in values and value is not None:
                values[key] = value
    return Profile(**values)
