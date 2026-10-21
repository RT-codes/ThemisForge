from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.db import Base
from app.persistence.models.common import UtcDateTime, utcnow


class CodexConnection(Base):
    """One user's Codex login (ChatGPT plan). The whole auth.json is encrypted at rest (see app/codex.py)."""

    __tablename__ = "codex_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    auth_encrypted: Mapped[str] = mapped_column(Text)
    account: Mapped[str] = mapped_column(String(320), default="")
    connected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    refreshed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)


class Connection(Base):
    """One user's sign in to an outside service (GitHub, ...). The credential is encrypted at rest (app/connections.py)."""

    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("user_id", "provider", "account", name="uq_connections_account"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(
        String(40)
    )  # a provider id, see app/features/connections/service.py
    method: Mapped[str] = mapped_column(String(10))  # how it was made: "token" | "oauth"
    credential_encrypted: Mapped[str] = mapped_column(Text)  # JSON, e.g. {"token": "..."}
    account: Mapped[str] = mapped_column(String(320), default="")  # who it is, shown in the UI ("octocat")
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )  # what the provider learned: no secrets
    connected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    checked_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)  # last successful test


class McpLogin(Base):
    """One user's sign in to a tool server that asks for one (see app/mcp_auth). It is the user's, not a project's: a
    project's tools use their owner's, found by the server's address, so signing in once covers every project and
    every tool that points at that server. The secret part is encrypted and owned by the auth scheme, so a scheme that
    keeps other things than tokens needs no new column."""

    __tablename__ = "mcp_logins"
    __table_args__ = (UniqueConstraint("user_id", "resource", name="uq_mcp_logins_resource"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resource: Mapped[str] = mapped_column(String(2000))  # the server's address in its canonical form
    scheme: Mapped[str] = mapped_column(String(20))  # the auth scheme that made it
    status: Mapped[str] = mapped_column(String(20), default="active")  # "active" | "needs_sign_in"
    error: Mapped[str] = mapped_column(Text, default="")  # why it needs a new sign in, for people
    credential_encrypted: Mapped[str] = mapped_column(
        Text, default=""
    )  # JSON the scheme owns, see app/crypto.py
    account: Mapped[str] = mapped_column(String(320), default="")  # who it is, shown ("Acme workspace")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # what the server said: no secrets
    expires_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime(), default=None
    )  # when the token stops working
    refreshed_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime(), default=None
    )  # last time it was renewed
    connected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class ProjectConnection(Base):
    """The connection a project uses for a provider. Agents of the project can then opt in to it (Agent.connections)."""

    __tablename__ = "project_connections"
    __table_args__ = (UniqueConstraint("project_id", "provider", name="uq_project_connections_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"))
    config: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )  # per project, e.g. {"repo": "owner/name"}
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
