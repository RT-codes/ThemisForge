from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.db import Base
from app.persistence.models.common import AttemptStatus, ScheduleKind, TaskStatus, UtcDateTime, utcnow
from app.persistence.models.projects import Project


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    # The board the task lives on. Boards with tasks are never deleted outright (the API moves the tasks first), the
    # cascade only serves deleting a whole project.
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    # A built-in status ("backlog"...) or a custom one of its board ("custom:<id>", see BoardStatus).
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.BACKLOG, index=True)
    position: Mapped[float] = mapped_column(Float, default=0.0)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    schedule_kind: Mapped[str] = mapped_column(String(10), default=ScheduleKind.NONE)
    cron: Mapped[str | None] = mapped_column(String(100), default=None)
    run_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    # The scheduler picks up READY tasks whose next_run_at is empty or in the past.
    next_run_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    review_on_success: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # The task this one was spawned from (a follow-up made on another board); the link survives a move of either task.
    origin_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), default=None, index=True
    )
    # Made by a workflow step: "run:<run id>:<node id>". Unique, so a step that runs again cannot make a second task.
    origin_key: Mapped[str | None] = mapped_column(String(80), default=None, unique=True)
    # Loop guard (see app/features/projects/automation.py). `hops` counts how many times automation moved or made this task in a row; a
    # person acting on it starts the count again. The two overrides beat the project's and the global settings.
    hops: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cooldown_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    max_hops: Mapped[int | None] = mapped_column(Integer, default=None)
    # What runs: "" = the placeholder program in a cell, "codex" = Codex in a cell (see app/execution/harnesses/service.py),
    # "workflow" = play the workflows of its TaskStage rows, one after the other, instead of running a cell.
    harness: Mapped[str] = mapped_column(String(20), default="", server_default="")
    # The agent that does this task (its instructions, model, cell and folders), see Agent below.
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), default=None)
    # Extras for this one run, set by a workflow's Agent node:
    # {"profile": {...}, "mounts": [{"volume_id", "mode"}], "workdir": <attempt id>}.
    run_options: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Made by a workflow's Agent node to run its step: a task only so the scheduler, the budget and the history work
    # on it. It is not board work, so it stays off the boards and out of the counts (unless asked for), never starts a
    # workflow by being moved, and does not wait out the start delay: the workflow is already waiting for it.
    internal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="tasks")
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="Attempt.id.desc()"
    )


class TaskStage(Base):
    """One workflow a task plays, in order. Its progress is the run it started in the task's latest attempt.

    Read and written through queries (see the task router), not a relationship on Task: tasks are loaded and made in
    many async places, where an unloaded collection would fail on access.

    There is no status column on purpose: a stage with no run is "not started", otherwise it is whatever its run says,
    so the two can never disagree. A new attempt clears every `workflow_run_id` (see WorkflowRunner.run_for_task);
    the runs themselves, and the attempt that started them, stay as the history.
    """

    __tablename__ = "task_stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    # deleting a workflow takes it out of the tasks that played it
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), default=None
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
    # set when the task played workflows: the run of the stage playing now, or of the last one that did
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), default=None
    )
    # The working folder this attempt used, named by the attempt that made it (data/projects/<id>/workspaces/<n>).
    # Its own id unless the run continued in an earlier folder; a task that plays workflows gets the folder its last
    # stage ended in, so whatever waits for it can carry on there. Null on attempts from before folders were passed on.
    workdir_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    # What the cell changed in that folder: {"added": [...], "changed": [...], "removed": [...], "more": n}. It is what
    # the next run in the folder is told (see harness.workdir_note). Null for tasks that ran no cell.
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Why a failed attempt failed, for the person looking at the ticket: {"source": "themis" | "agent", "reason",
    # "action", "tail"}. `source` says who worked it out (Themis from what it saw, or the agent that stopped and said so
    # in /cell/blocked.md); `action` is what to change, empty when nobody knows; `tail` is the last lines of the log.
    # Null on a run that did not fail, and on attempts from before reasons were kept.
    failure: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # What the attempt used, kept as the harness reported it and not as money: prices change, and a subscription has
    # none, so cost is worked out from these later. `harness`, `model` (the one really used, Settings' default filled
    # in) and `billing` ("subscription" | "api") are set when the attempt starts; the token counts when it ends,
    # added up over the runs it took (see Scheduler._execute). All null for attempts that ran no harness (the
    # placeholder program, a task that plays workflows) and for attempts from before usage was kept. The token counts
    # are also null when the harness reported none: a run that crashed or was cancelled before its turn ended.
    harness: Mapped[str | None] = mapped_column(String(20), default=None)
    model: Mapped[str | None] = mapped_column(String(100), default=None)
    billing: Mapped[str | None] = mapped_column(String(20), default=None)
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)  # part of input_tokens
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    reasoning_output_tokens: Mapped[int | None] = mapped_column(
        Integer, default=None
    )  # part of output_tokens

    task: Mapped[Task] = relationship(back_populates="attempts")
