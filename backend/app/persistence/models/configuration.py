from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.db import Base
from app.persistence.models.common import UtcDateTime, utcnow


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


class Volume(Base):
    """A folder that outlives a run and can be mounted into cells at /workspace/NAME (see app/volumes.py)."""

    __tablename__ = "volumes"
    # ids are never reused (SQLite would hand a deleted newest id to the next row): workflow nodes refer to a folder by
    # id, and a stale one must never quietly point at a different folder
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_volumes_project_id_name"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))  # a slug: it becomes the folder name inside the cell
    kind: Mapped[str] = mapped_column(String(10), default="managed")  # "managed" (ThemisForge's own) | "host"
    host_path: Mapped[str] = mapped_column(Text, default="")  # kind "host": the folder on this machine
    mode: Mapped[str] = mapped_column(String(2), default="rw")  # the most a cell may do: "ro" | "rw"
    exclusive_write: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )  # writers take turns
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Agent(Base):
    """A configured worker of a project: who it is, what it was told, how it runs (see app/harness.py)."""

    __tablename__ = "agents"
    # never reuse an id: workflow nodes name their agent by id, and an agent can hold keys
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_agents_project_id_name"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(200), default="")  # one line: what it is responsible for
    description: Mapped[str] = mapped_column(Text, default="")  # for people: what this agent is for
    instructions: Mapped[str] = mapped_column(
        Text, default=""
    )  # for the agent: always put in front of its task
    harness: Mapped[str] = mapped_column(String(20), default="codex")
    model: Mapped[str] = mapped_column(String(100), default="")  # empty = the model in Settings
    reasoning_effort: Mapped[str] = mapped_column(String(10), default="")  # empty = the effort in Settings
    cell_profile: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # overrides, like a project's
    mounts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # [{"volume_id", "mode"}]
    skills: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )  # names, see app/features/agents/skills.py
    mcp_servers: Mapped[list[int]] = mapped_column(JSON, default=list, server_default="[]")  # McpServer ids
    secrets: Mapped[list[int]] = mapped_column(
        JSON, default=list, server_default="[]"
    )  # Secret ids, see app/features/tools/keys.py
    connections: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )  # provider ids this agent may use through the project's connections, see app/features/connections/service.py
    # The agent's file in the project's config folder is the source of truth (see app/features/project_config/store.py); this row is
    # its identity (tasks and workflows point at the id) and a parsed copy for fast lists and for planning runs.
    path: Mapped[str] = mapped_column(
        String(300), default="", server_default=""
    )  # relative to the config folder
    config_error: Mapped[str] = mapped_column(
        Text, default="", server_default=""
    )  # why the file cannot be read
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)


class McpServer(Base):
    """A tool server (MCP) a project's agents can be given, written into the harness config for each run."""

    __tablename__ = "mcp_servers"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_mcp_servers_project_id_name"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))  # a slug: it is the server's name in the agent's config
    kind: Mapped[str] = mapped_column(String(10), default="stdio")  # "stdio" (a command) | "http"
    command: Mapped[str] = mapped_column(Text, default="")
    args: Mapped[list[str]] = mapped_column(JSON, default=list)
    url: Mapped[str] = mapped_column(Text, default="")
    env: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict
    )  # plain settings for the server's environment
    secret_env: Mapped[dict[str, int]] = mapped_column(
        JSON, default=dict
    )  # environment variable -> Secret id
    bearer_secret_id: Mapped[int | None] = mapped_column(
        Integer, default=None
    )  # http: the key sent as a bearer token
    # http: how the server wants people to sign in, as the id of an auth scheme (app/mcp_auth), or "" for none. The
    # sign in itself is an McpLogin of the project's owner: a tool says how, never holds the credential.
    auth: Mapped[str] = mapped_column(String(20), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")  # for people
    # like Agent.path: the file in the config folder is the truth, this row is its identity and a parsed copy
    path: Mapped[str] = mapped_column(String(300), default="", server_default="")
    config_error: Mapped[str] = mapped_column(Text, default="", server_default="")
    last_test: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # the latest connection test: {"ok", "message", "tools", "at"}
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
