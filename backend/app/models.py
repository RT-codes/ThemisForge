from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Dialect,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator):
    """SQLite drops tzinfo; this stores UTC and hands back timezone-aware datetimes."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: use timezone-aware values")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class TaskStatus(StrEnum):
    INBOX = "inbox"
    READY = "ready"
    RUNNING = "running"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class ScheduleKind(StrEnum):
    NONE = "none"
    ONCE = "once"
    CRON = "cron"


class AttemptStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    # Custom Kanban properties: [{"key", "name", "type", "options"}], see app/properties.py.
    properties: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.INBOX, index=True)
    position: Mapped[float] = mapped_column(Float, default=0.0)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    schedule_kind: Mapped[str] = mapped_column(String(10), default=ScheduleKind.NONE)
    cron: Mapped[str | None] = mapped_column(String(100), default=None)
    run_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    # The scheduler picks up READY tasks whose next_run_at is empty or in the past.
    next_run_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    review_on_success: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="tasks")
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="Attempt.id.desc()"
    )


class Attempt(Base):
    """One execution of a task inside a cell: when it ran, what it logged, how it ended."""

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=AttemptStatus.RUNNING)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    exit_code: Mapped[int | None] = mapped_column(Integer, default=None)
    log: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")

    task: Mapped[Task] = relationship(back_populates="attempts")


class Secret(Base):
    """A named credential. The value is encrypted at rest (see app/crypto.py)."""

    __tablename__ = "secrets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[str] = mapped_column(String(50), default="custom")
    value_encrypted: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class AppSetting(Base):
    """Key/value store for operator settings edited from the Settings page."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
