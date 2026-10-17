import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import boards, security, webhooks
from ..deps import CurrentUser, SessionDep
from ..models import Project, TaskStatus, Webhook, WebhookDelivery
from ..schemas import (
    DeliveryOut,
    DeliveryResult,
    WebhookCreated,
    WebhookIn,
    WebhookOut,
    WebhookPatch,
    WebhookTestIn,
)

# What the owner sets up, behind the login ...
router = APIRouter(tags=["webhooks"])
# ... and the address the other side posts to. There is no login here: the secret in the address is the credential.
receiver = APIRouter(tags=["webhooks"])


def _bad(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


async def _project(session: AsyncSession, project_id: int, user: CurrentUser) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


async def _webhook(session: AsyncSession, webhook_id: int, user: CurrentUser) -> Webhook:
    hook = await session.get(Webhook, webhook_id)
    project = await session.get(Project, hook.project_id) if hook else None
    if hook is None or project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")
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


# setting up


@router.get("/projects/{project_id}/webhooks", response_model=list[WebhookOut])
async def list_webhooks(project_id: int, session: SessionDep, user: CurrentUser) -> list[WebhookOut]:
    await _project(session, project_id, user)
    hooks = await session.scalars(
        select(Webhook).where(Webhook.project_id == project_id).order_by(Webhook.id)
    )
    return [await _out(session, h) for h in hooks]


@router.post(
    "/projects/{project_id}/webhooks", response_model=WebhookCreated, status_code=status.HTTP_201_CREATED
)
async def create_webhook(
    project_id: int, body: WebhookIn, session: SessionDep, user: CurrentUser
) -> WebhookCreated:
    project = await _project(session, project_id, user)
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


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: int, body: WebhookPatch, session: SessionDep, user: CurrentUser
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


@router.post("/webhooks/{webhook_id}/token", response_model=WebhookCreated)
async def new_secret(webhook_id: int, session: SessionDep, user: CurrentUser) -> WebhookCreated:
    """A new address. The old one stops working at once, so whatever posts to it has to be given the new one."""
    hook = await _webhook(session, webhook_id, user)
    token, hook.token_hash, hook.token_hint = security.new_secret()
    await session.commit()
    return await _created(session, hook, token)


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(webhook_id: int, session: SessionDep, user: CurrentUser) -> None:
    await session.delete(await _webhook(session, webhook_id, user))
    await session.commit()


# what arrived


@router.get("/webhooks/{webhook_id}/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(webhook_id: int, session: SessionDep, user: CurrentUser) -> list[WebhookDelivery]:
    hook = await _webhook(session, webhook_id, user)
    rows = await session.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == hook.id)
        .order_by(WebhookDelivery.id.desc())
        .limit(webhooks.KEEP_DELIVERIES)
    )
    return list(rows)


@router.post("/webhooks/{webhook_id}/test", response_model=DeliveryResult)
async def test_webhook(
    webhook_id: int, body: WebhookTestIn, request: Request, session: SessionDep, user: CurrentUser
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
    _wake(request, result)
    return DeliveryResult(
        outcome=result.outcome, detail=result.detail, task_id=result.task.id if result.task else None
    )


# the address


def _wake(request: Request, result: webhooks.Result) -> None:
    if result.task is not None and result.task.status == TaskStatus.READY:
        request.app.state.scheduler.wake()


async def _body(request: Request) -> bytes:
    """The message, read only up to the limit: a sender cannot make the server hold what it likes."""
    too_big = HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The message is too big")
    if int(request.headers.get("content-length") or 0) > webhooks.MAX_BODY:
        raise too_big
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > webhooks.MAX_BODY:
            raise too_big
        chunks.append(chunk)
    return b"".join(chunks)


@receiver.post("/hooks/{token}", response_model=DeliveryResult)
async def receive(token: str, request: Request, session: SessionDep) -> JSONResponse:
    hook = await session.scalar(select(Webhook).where(Webhook.token_hash == security.hash_secret(token)))
    if hook is None:  # a wrong address and a deleted webhook look the same
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if webhooks.too_many(hook.id):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many messages. Try again in a minute.",
            headers={"Retry-After": "60"},
        )
    result = await webhooks.receive(
        session, hook, await _body(request), request.headers.get("content-type", ""), dict(request.headers)
    )
    _wake(request, result)
    out = DeliveryResult(
        outcome=result.outcome, detail=result.detail, task_id=result.task.id if result.task else None
    )
    return JSONResponse(out.model_dump(), status_code=result.status_code)
