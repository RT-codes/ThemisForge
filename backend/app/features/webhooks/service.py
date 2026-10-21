import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

import app.features.webhooks.receiver as webhooks
from app import security
from app.errors import ApplicationError
from app.features.projects import boards
from app.features.projects.access import require_project
from app.features.webhooks.schemas import (
    DeliveryResult,
    WebhookCreated,
    WebhookIn,
    WebhookOut,
    WebhookPatch,
    WebhookTestIn,
)
from app.persistence.models import Project, TaskStatus, User, Webhook, WebhookDelivery
from app.runtime import Runtime


def _bad(detail: str) -> ApplicationError:
    return ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


async def _webhook(session: AsyncSession, webhook_id: int, user: User) -> Webhook:
    hook = await session.get(Webhook, webhook_id)
    project = await session.get(Project, hook.project_id) if hook else None
    if hook is None or project is None or project.owner_id != user.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Webhook not found")
    return hook


async def _out(session: AsyncSession, hook: Webhook) -> WebhookOut:
    out = WebhookOut.model_validate(hook)
    out.problem = await webhooks.problem(session, hook)
    return out


async def _created(session: AsyncSession, hook: Webhook, token: str) -> WebhookCreated:
    return WebhookCreated(**(await _out(session, hook)).model_dump(), path=f"/api/hooks/{token}")


async def _checked(session: AsyncSession, hook: Webhook) -> None:
    """A webhook is saved only when it could make a task: a made-up board, status, agent or property is refused here
    rather than on the first message."""
    if why := await webhooks.problem(session, hook):
        raise _bad(why)


async def list_webhooks(project_id: int, session: AsyncSession, user: User) -> list[WebhookOut]:
    await require_project(session, project_id, user)
    hooks = await session.scalars(
        select(Webhook).where(Webhook.project_id == project_id).order_by(Webhook.id)
    )
    return [await _out(session, h) for h in hooks]


async def create_webhook(
    project_id: int, body: WebhookIn, session: AsyncSession, user: User
) -> WebhookCreated:
    project = await require_project(session, project_id, user)
    board_id = body.board_id
    if board_id is None:
        board_id = (await boards.default_board(session, project.id)).id
    token, token_hash, hint = security.new_secret()
    hook = Webhook(
        project_id=project.id,
        token_hash=token_hash,
        token_hint=hint,
        **{**body.model_dump(exclude={"rules"}), "board_id": board_id},
        rules=[r.model_dump() for r in body.rules],
    )
    await _checked(session, hook)
    session.add(hook)
    await session.commit()
    return await _created(session, hook, token)


async def update_webhook(
    webhook_id: int, body: WebhookPatch, session: AsyncSession, user: User
) -> WebhookOut:
    hook = await _webhook(session, webhook_id, user)
    # null is a value only for the agent (none); anywhere else it means "not sent"
    for field in body.model_fields_set:
        value = getattr(body, field)
        if value is None and field != "agent_id":
            continue
        setattr(hook, field, [r.model_dump() for r in value] if field == "rules" else value)
    if "status" in body.model_fields_set and body.status == TaskStatus.RUNNING:
        raise _bad("Tasks start running through the scheduler: use Ready")
    await _checked(session, hook)
    await session.commit()
    return await _out(session, hook)


async def new_secret(webhook_id: int, session: AsyncSession, user: User) -> WebhookCreated:
    """A new address. The old one stops working at once, so whatever posts to it has to be given the new one."""
    hook = await _webhook(session, webhook_id, user)
    token, hook.token_hash, hook.token_hint = security.new_secret()
    await session.commit()
    return await _created(session, hook, token)


async def delete_webhook(webhook_id: int, session: AsyncSession, user: User) -> None:
    await session.delete(await _webhook(session, webhook_id, user))
    await session.commit()


async def list_deliveries(webhook_id: int, session: AsyncSession, user: User) -> list[WebhookDelivery]:
    hook = await _webhook(session, webhook_id, user)
    rows = await session.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == hook.id)
        .order_by(WebhookDelivery.id.desc())
        .limit(webhooks.KEEP_DELIVERIES)
    )
    return list(rows)


async def test_webhook(
    webhook_id: int, body: WebhookTestIn, runtime: Runtime, session: AsyncSession, user: User
) -> DeliveryResult:
    """Send the webhook a message of your own, as the other side would. It goes the whole way, so it makes a real task."""
    hook = await _webhook(session, webhook_id, user)
    try:
        json.loads(body.payload)
    except ValueError:
        raise _bad("The message is not valid JSON") from None
    result = await webhooks.receive(
        session, hook, body.payload.encode(), "application/json", {"x-github-event": body.event}
    )
    _wake(runtime, result)
    return DeliveryResult(
        outcome=result.outcome, detail=result.detail, task_id=result.task.id if result.task else None
    )


def _wake(runtime: Runtime, result: webhooks.Result) -> None:
    if result.task is not None and result.task.status == TaskStatus.READY:
        runtime.scheduler.wake()
