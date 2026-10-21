from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.db import Base
from app.persistence.models.common import TaskStatus, UtcDateTime, utcnow


class Webhook(Base):
    """An address other programs can post to, to make tasks in a project (see app/webhooks.py).

    The sender only provides what arrives (a message in any shape). Everything about the task that is made is set here,
    by the project's owner: where it lands, what runs it, which properties it has. Only a hash of the secret in the
    address is stored, like an invite's."""

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_hint: Mapped[str] = mapped_column(
        String(8), default=""
    )  # the last characters, to tell addresses apart
    # Where the tasks land. A deleted board leaves the webhook without one: deliveries are refused until another is chosen.
    board_id: Mapped[int | None] = mapped_column(ForeignKey("boards.id", ondelete="SET NULL"), default=None)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.BACKLOG)  # as Task.status
    # How the message becomes a task: text with {{path.to.value}} holes filled from the message (see webhooks.render).
    # Empty means the message's own "title" / "description", else the webhook's name / the message as it came.
    title_template: Mapped[str] = mapped_column(String(200), default="", server_default="")
    description_template: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Only messages that match make a task: [{"path", "equals": [...]}], all of them. Empty means every message.
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # What the task is, as on Task: it is the same choice, made once for every task this webhook makes.
    harness: Mapped[str] = mapped_column(String(20), default="", server_default="")
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), default=None)
    workflow_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    review_on_success: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    last_received_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class WebhookDelivery(Base):
    """One message that arrived at a webhook and what became of it. The newest few are kept, with the message itself,
    because the hard part of a webhook is knowing what the other side actually sent."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    webhook_id: Mapped[int] = mapped_column(ForeignKey("webhooks.id", ondelete="CASCADE"), index=True)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    # "created" (a task was made), "skipped" (no rule matched, or the sender's ping), "duplicate" (the sender sent
    # the same delivery again) or "refused" (why is in `detail`)
    outcome: Mapped[str] = mapped_column(String(12))
    detail: Mapped[str] = mapped_column(String(300), default="")
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), default=None)
    event: Mapped[str] = mapped_column(String(60), default="")  # what the sender called it, e.g. "issues"
    delivery_key: Mapped[str] = mapped_column(String(120), default="")  # the sender's id for this delivery
    payload: Mapped[str] = mapped_column(Text, default="")  # the start of the message


class NotificationTarget(Base):
    """Somewhere Themis tells a project's owner that something happened: a Discord channel today (see
    app/notifications.py). `kind` names the adapter that knows how to talk to it; what that adapter needs (a channel
    address, a bot token) is kept in `config_encrypted`, like a stored key, and never returned by the API."""

    __tablename__ = "notification_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    config_encrypted: Mapped[str] = mapped_column(Text)  # the adapter's fields as JSON, encrypted
    hint: Mapped[str] = mapped_column(String(20), default="")  # the end of the secret, to tell targets apart
    events: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )  # which events it hears: app/notifications.EVENTS
    last_sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    last_error: Mapped[str] = mapped_column(
        String(300), default=""
    )  # empty when the last message went through
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
