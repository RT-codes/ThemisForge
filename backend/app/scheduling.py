"""When tasks run and where they go afterwards.

A task is picked up by the scheduler when it is READY and its next_run_at is empty (run as soon
as there is a free cell) or in the past. Recurring (cron) tasks return to READY after every
attempt with the next occurrence; one-off tasks finish as DONE / REVIEW / FAILED. A recurring task
parked in INBOX is paused.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from .models import AttemptStatus, ScheduleKind, Task, TaskStatus


def validate_cron(expr: str) -> str:
    expr = " ".join(expr.split())
    if len(expr.split(" ")) != 5 or not croniter.is_valid(expr):
        raise ValueError("Cron must have 5 fields, e.g. '0 9 * * 1-5' (minute hour day month weekday)")
    return expr


def next_cron(expr: str, tz: str, after: datetime) -> datetime:
    zone = ZoneInfo(tz)
    return croniter(expr, after.astimezone(zone)).get_next(datetime).astimezone(UTC)


def cron_occurrences(expr: str, tz: str, start: datetime, end: datetime) -> Iterator[datetime]:
    it = croniter(expr, start.astimezone(ZoneInfo(tz)))
    while (at := it.get_next(datetime).astimezone(UTC)) <= end:
        yield at


def refresh_next_run(task: Task, tz: str, now: datetime) -> None:
    """Recompute next_run_at after the status or the schedule of a task changed."""
    if task.status == TaskStatus.RUNNING:
        return
    if task.status != TaskStatus.READY:
        task.next_run_at = None
    elif task.schedule_kind == ScheduleKind.CRON and task.cron:
        task.next_run_at = next_cron(task.cron, tz, now)
    elif task.schedule_kind == ScheduleKind.ONCE and task.run_at:
        task.next_run_at = task.run_at
    else:
        task.next_run_at = None


def finish_task(task: Task, outcome: AttemptStatus, tz: str, now: datetime) -> None:
    """Move a task on after its attempt ended."""
    if task.schedule_kind == ScheduleKind.CRON and task.cron:
        task.status = TaskStatus.READY
        refresh_next_run(task, tz, now)
        return
    task.next_run_at = None
    if outcome == AttemptStatus.SUCCEEDED:
        task.status = TaskStatus.REVIEW if task.review_on_success else TaskStatus.DONE
    elif outcome == AttemptStatus.CANCELLED:
        task.status = TaskStatus.BLOCKED
    else:
        task.status = TaskStatus.FAILED
