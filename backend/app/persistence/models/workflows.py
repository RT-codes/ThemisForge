from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.db import Base
from app.persistence.models.common import NodeStatus, RunStatus, UtcDateTime, utcnow


class Workflow(Base):
    """A workflow in a project's library: nodes and edges as JSON (see app/workflows.py)."""

    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), default="Workflow")
    description: Mapped[str] = mapped_column(Text, default="")
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, default=lambda: {"nodes": [], "edges": []})
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)


class NodePreset(Base):
    """A configured workflow node a project keeps in the editor's palette ("saved nodes"). It holds ids of the
    project's own agents, folders and boards, so it only makes sense inside that project."""

    __tablename__ = "node_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(100), default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class WorkflowRun(Base):
    """One execution of a workflow, with the graph as it was when the run began."""

    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    # the run that is waiting for the task that started this one (a workflow played from a task inside a workflow)
    parent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.RUNNING)
    trigger: Mapped[str] = mapped_column(String(20), default="test")  # test | task | status
    # the task whose move into a status started this run (trigger "status"); its nodes can work with it
    trigger_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), default=None
    )
    outcome: Mapped[str] = mapped_column(Text, default="")  # what the End node said, or why the run failed
    # The working folder (see Attempt.workdir_id) the last step of this run ended in. The next stage of a task
    # starts with it, so a node that asks to continue picks up where this run left off.
    workdir_id: Mapped[int | None] = mapped_column(Integer, default=None)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    nodes: Mapped[list["WorkflowNodeRun"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="WorkflowNodeRun.seq"
    )


class WorkflowNodeRun(Base):
    """What happened at one node during a run: when, how it ended, its output and any error."""

    __tablename__ = "workflow_node_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(100))
    seq: Mapped[int] = mapped_column(Integer)  # chronological order within the run
    # indexed because the open approvals (status "waiting") are looked up on every poll of the app
    status: Mapped[str] = mapped_column(String(20), default=NodeStatus.RUNNING, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    log: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    # An approval gate keeps what it needs to be picked up again after a restart: what it asks ("prompt") and what the
    # node before it handed on ("previous", a Prev). The person's answer goes in the next three columns; the gate
    # polls them. `decision` is "" while open, then "approved" or "rejected" (written once, see decide_approval).
    gate: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    decision: Mapped[str] = mapped_column(String(10), default="", server_default="")
    decision_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    decided_by: Mapped[str] = mapped_column(String(100), default="", server_default="")
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), default=None)
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("attempts.id", ondelete="SET NULL"), default=None
    )

    run: Mapped[WorkflowRun] = relationship(back_populates="nodes")
