from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.db import Base
from app.persistence.models.common import RequestStatus, UtcDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class AccessRequest(Base):
    """Someone without an account asking the administrator for access."""

    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default=RequestStatus.PENDING, index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)


class Invite(Base):
    """A single-use link that lets one email address create an account. Only a hash of the token is stored."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)


class ControlToken(Base):
    """The key an outside agent (or, later, a run) holds to use Themis's MCP control plane (see app/control.py). It acts
    as its user. With a `project_id` it reaches that one project and nothing else; without one it reaches all of the
    user's projects and, for an administrator, the global settings. `scope` says what it may do: "read" looks, "write"
    also runs the project's work, "manage" also sets it up (agents, workflows, files).

    Unlike a webhook address it can be shown again: the secret is kept encrypted besides its hash, so the settings can
    always give the owner the full connect command instead of making them mint a new token."""

    __tablename__ = "control_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )  # None: every project of the user
    name: Mapped[str] = mapped_column(String(60))
    scope: Mapped[str] = mapped_column(String(10), default="read", server_default="read")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # what a request is looked up by
    token_encrypted: Mapped[str] = mapped_column(Text)  # what the owner is shown again
    token_hint: Mapped[str] = mapped_column(
        String(8), default=""
    )  # the last characters, to tell tokens apart
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
