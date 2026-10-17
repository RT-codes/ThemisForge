"""What a project's attempts used, added up from what each attempt recorded (see Attempt.harness and friends).

Kept as tokens per harness and model: money is worked out from these once there is a rate for each model, so this is
the one place that sums them, for the REST API, the MCP control plane and whatever shows usage next.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Attempt, Task
from .schemas import UsageRow


async def usage_by_model(
    session: AsyncSession, project_id: int, since: datetime | None = None
) -> list[UsageRow]:
    """One row per harness, model and way of paying, for the attempts that started at or after `since` (all of them
    when None). Attempts that ran no harness are not counted; one that ran but reported no tokens is counted as an
    attempt with zero tokens, so a number of attempts without tokens shows that reporting is missing."""
    spent = [
        func.coalesce(func.sum(getattr(Attempt, name)), 0)
        for name in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
    ]
    query = (
        select(Attempt.harness, Attempt.model, Attempt.billing, func.count(Attempt.id), *spent)
        .join(Task, Task.id == Attempt.task_id)
        .where(Task.project_id == project_id, Attempt.harness.is_not(None))
        .group_by(Attempt.harness, Attempt.model, Attempt.billing)
        .order_by(Attempt.harness, Attempt.model)
    )
    if since is not None:
        query = query.where(Attempt.started_at >= since)
    return [
        UsageRow(
            harness=harness,
            model=model or "",
            billing=billing or "subscription",
            attempts=attempts,
            input_tokens=input_tokens,
            cached_input_tokens=cached,
            output_tokens=output,
            reasoning_output_tokens=reasoning,
        )
        for harness, model, billing, attempts, input_tokens, cached, output, reasoning in await session.execute(
            query
        )
    ]
