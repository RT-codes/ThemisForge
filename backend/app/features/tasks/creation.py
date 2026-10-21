"""Making a task: the one path every new task takes, whether a person made it in the app or a webhook did.

The router and the webhook receiver both build a `TaskIn`, so what a task may be given is checked in one place. A
broken rule raises `TaskError`, which the API turns into a 422 (see main.py); the webhook receiver writes it into its
delivery log instead.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects import boards
from app.features.projects.properties import clean_values
from app.features.system.settings import load_settings
from app.features.tasks.scheduling import refresh_next_run
from app.features.tasks.schemas import TaskIn
from app.persistence.models import Agent, Project, Task, TaskStage, Workflow, utcnow


class TaskError(Exception):
    """A task cannot be made or changed like that. The message is for the person who asked."""


async def agent_for(session: AsyncSession, project_id: int, agent_id: int) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.project_id != project_id:
        raise TaskError("That agent does not exist in this project")
    return agent


async def workflows_for(
    session: AsyncSession, project_id: int, harness: str, workflow_ids: list[int]
) -> list[int]:
    """The workflows a task may play: only when it runs with them, and only ones from its own project."""
    if harness != "workflow":
        return []
    if not workflow_ids:
        raise TaskError("Choose the workflow this task should play")
    found = set(
        await session.scalars(
            select(Workflow.id).where(Workflow.id.in_(set(workflow_ids)), Workflow.project_id == project_id)
        )
    )
    if missing := set(workflow_ids) - found:
        raise TaskError(f"Workflow {min(missing)} does not exist in this project")
    return workflow_ids


async def set_stages(session: AsyncSession, task: Task, workflow_ids: list[int]) -> None:
    """Make the task play exactly these workflows. An unchanged list is left alone, so the stages keep their runs."""
    current = await session.scalars(
        select(TaskStage.workflow_id).where(TaskStage.task_id == task.id).order_by(TaskStage.position)
    )
    if list(current) == workflow_ids:
        return
    await session.execute(delete(TaskStage).where(TaskStage.task_id == task.id))
    session.add_all(
        TaskStage(task_id=task.id, position=i, workflow_id=wid) for i, wid in enumerate(workflow_ids)
    )


async def new_task(
    session: AsyncSession, project: Project, body: TaskIn, actor: str, cause: str = ""
) -> Task:
    """Add a task to the session, with its stages and its line in the history. The caller commits, and wakes the
    scheduler when the task is Ready. `actor` and `cause` are for the history: a person's name, or "Webhook <name>"
    with what set it off."""
    try:
        props = clean_values(project.properties, body.properties)
    except ValueError as e:
        raise TaskError(str(e)) from None
    try:
        board = (
            await boards.project_board(session, project.id, body.board_id)
            if body.board_id is not None
            else await boards.default_board(session, project.id)
        )
        boards.check_status(board, body.status)
    except boards.BoardError as e:
        raise TaskError(str(e)) from None
    task = Task(
        project_id=project.id,
        board_id=board.id,
        title=body.title,
        description=body.description,
        status=body.status,
        position=await boards.next_position(session, board.id, body.status),
        properties=props,
        schedule_kind=body.schedule_kind,
        cron=body.cron,
        run_at=body.run_at,
        review_on_success=body.review_on_success,
        harness=body.harness,
        cooldown_seconds=body.cooldown_seconds,
        max_hops=body.max_hops,
    )
    stages: list[int] = []
    if body.agent_id is not None:
        agent = await agent_for(session, project.id, body.agent_id)
        task.agent_id, task.harness = agent.id, agent.harness
    else:
        stages = await workflows_for(session, project.id, body.harness, body.workflow_ids)
    refresh_next_run(task, (await load_settings(session)).timezone, utcnow())
    session.add(task)
    await session.flush()
    await set_stages(session, task, stages)
    boards.record_new_task(session, task, board, actor, cause)
    return task
