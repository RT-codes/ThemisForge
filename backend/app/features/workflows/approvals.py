import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import asdict

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.notifications.delivery import notify
from app.features.workflows.graph import (
    GraphNode,
)
from app.features.workflows.walk import Outcome, Prev
from app.persistence.models import (
    NodeStatus,
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
)


class ApprovalGates:
    """Persist decisions and wake their waiters, including resumed gates."""

    def __init__(self, maker: async_sessionmaker[AsyncSession], poll_seconds: Callable[[], float]) -> None:
        self.maker, self.poll_seconds = maker, poll_seconds
        self._answers: dict[int, asyncio.Event] = {}

    async def wait(self, nr_id: int, node: GraphNode, prev: Prev | None) -> Outcome:
        """Park the run here until a person answers (see `decide`). Approving passes on what the node before produced,
        unchanged; rejecting fails the node with the person's note as the reason.

        The gate is stored on its record (the question, and what the node before handed on), so after a restart
        `_resume` can pick the run up at this node without any state of the walker."""
        async with self.maker() as s:
            row = await s.get(WorkflowNodeRun, nr_id)
            assert row is not None
            if row.gate is None:  # not a gate being picked up again
                row.gate = {
                    "prompt": node.config.get("prompt", "").strip(),
                    "previous": asdict(prev) if prev else None,
                }
                row.status = NodeStatus.WAITING
                row.log = "Waiting for approval.\n"
                await s.commit()
                # Told once, when the gate first opens: a gate picked up again after a restart has already said so.
                run = await s.get(WorkflowRun, row.run_id)
                workflow = await s.get(Workflow, run.workflow_id) if run else None
                if run is not None and workflow is not None:
                    question = row.gate["prompt"].split("\n")[0] or row.label
                    notify(self.maker, run.project_id, "attention", question, f"Approval in {workflow.name}")
        answered = self._answers.setdefault(nr_id, asyncio.Event())
        try:
            while True:
                async with self.maker() as s:
                    row = await s.get(WorkflowNodeRun, nr_id)
                assert row is not None
                if row.decision:
                    break
                # the event wakes the gate the moment it is answered; the timeout only guards against a missed one
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(answered.wait(), self.poll_seconds())
        finally:
            self._answers.pop(nr_id, None)
        who, note = row.decided_by or "someone", row.decision_note.strip()
        verb = "Approved" if row.decision == "approved" else "Rejected"
        said = f"{verb} by {who}" + (f": {note}" if note else ".")
        log = f"Waiting for approval.\n{said}\n"
        result = prev.result if prev else ""
        if row.decision == "approved":
            return Outcome(NodeStatus.SUCCEEDED, result=result, log=log)
        return Outcome(NodeStatus.FAILED, result=result, log=log, error=said)

    async def decide(self, nr_id: int, approved: bool, note: str, by: str) -> bool:
        """Record the answer to an open approval gate and wake it. False when it is not open: answered already (the first
        answer stands), or not waiting. The update is conditional, so two people answering at once cannot both win."""
        async with self.maker() as s:
            result = await s.execute(
                update(WorkflowNodeRun)
                .where(
                    WorkflowNodeRun.id == nr_id,
                    WorkflowNodeRun.status == NodeStatus.WAITING,
                    WorkflowNodeRun.decision == "",
                )
                .values(decision="approved" if approved else "rejected", decision_note=note, decided_by=by)
            )
            await s.commit()
        if result.rowcount != 1:  # type: ignore[attr-defined]
            return False
        if answered := self._answers.get(nr_id):
            answered.set()
        return True
