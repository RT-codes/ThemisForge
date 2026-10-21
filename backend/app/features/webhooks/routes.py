from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

import app.features.webhooks.receiver as webhooks
import app.features.webhooks.service as operations
from app import security
from app.api.dependencies import CurrentUser, SessionDep
from app.features.webhooks.schemas import (
    DeliveryOut,
    DeliveryResult,
    WebhookCreated,
    WebhookIn,
    WebhookOut,
    WebhookPatch,
    WebhookTestIn,
)
from app.features.webhooks.service import _wake
from app.persistence.models import Webhook, WebhookDelivery

router = APIRouter(tags=["webhooks"])

receiver = APIRouter(tags=["webhooks"])


@router.get("/projects/{project_id}/webhooks", response_model=list[WebhookOut])
async def list_webhooks(project_id: int, session: SessionDep, user: CurrentUser) -> list[WebhookOut]:
    return await operations.list_webhooks(project_id, session, user)


@router.post(
    "/projects/{project_id}/webhooks", response_model=WebhookCreated, status_code=status.HTTP_201_CREATED
)
async def create_webhook(
    project_id: int, body: WebhookIn, session: SessionDep, user: CurrentUser
) -> WebhookCreated:
    return await operations.create_webhook(project_id, body, session, user)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: int, body: WebhookPatch, session: SessionDep, user: CurrentUser
) -> WebhookOut:
    return await operations.update_webhook(webhook_id, body, session, user)


@router.post("/webhooks/{webhook_id}/token", response_model=WebhookCreated)
async def new_secret(webhook_id: int, session: SessionDep, user: CurrentUser) -> WebhookCreated:
    """A new address. The old one stops working at once, so whatever posts to it has to be given the new one."""

    return await operations.new_secret(webhook_id, session, user)


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(webhook_id: int, session: SessionDep, user: CurrentUser) -> None:
    return await operations.delete_webhook(webhook_id, session, user)


@router.get("/webhooks/{webhook_id}/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(webhook_id: int, session: SessionDep, user: CurrentUser) -> list[WebhookDelivery]:
    return await operations.list_deliveries(webhook_id, session, user)


@router.post("/webhooks/{webhook_id}/test", response_model=DeliveryResult)
async def test_webhook(
    webhook_id: int, body: WebhookTestIn, request: Request, session: SessionDep, user: CurrentUser
) -> DeliveryResult:
    """Send the webhook a message of your own, as the other side would. It goes the whole way, so it makes a real task."""

    return await operations.test_webhook(webhook_id, body, request.app.state, session, user)


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
    _wake(request.app.state, result)
    out = DeliveryResult(
        outcome=result.outcome, detail=result.detail, task_id=result.task.id if result.task else None
    )
    return JSONResponse(out.model_dump(), status_code=result.status_code)
