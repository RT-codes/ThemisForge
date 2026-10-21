from fastapi import APIRouter, status

import app.features.notifications.service as operations
from app.api.dependencies import CurrentUser, SessionDep
from app.features.notifications.schemas import (
    NotificationIn,
    NotificationOptions,
    NotificationOut,
    NotificationPatch,
    NotificationTestOut,
)
from app.persistence.models import NotificationTarget

router = APIRouter(tags=["notifications"])


@router.get("/notification-options", response_model=NotificationOptions)
async def options(user: CurrentUser) -> NotificationOptions:
    return await operations.options(user)


@router.get("/projects/{project_id}/notifications", response_model=list[NotificationOut])
async def list_notifications(
    project_id: int, session: SessionDep, user: CurrentUser
) -> list[NotificationTarget]:
    return await operations.list_notifications(project_id, session, user)


@router.post(
    "/projects/{project_id}/notifications",
    response_model=NotificationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification(
    project_id: int, body: NotificationIn, session: SessionDep, user: CurrentUser
) -> NotificationTarget:
    return await operations.create_notification(project_id, body, session, user)


@router.patch("/notifications/{target_id}", response_model=NotificationOut)
async def update_notification(
    target_id: int, body: NotificationPatch, session: SessionDep, user: CurrentUser
) -> NotificationTarget:
    return await operations.update_notification(target_id, body, session, user)


@router.delete("/notifications/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(target_id: int, session: SessionDep, user: CurrentUser) -> None:
    return await operations.delete_notification(target_id, session, user)


@router.post("/notifications/{target_id}/test", response_model=NotificationTestOut)
async def test_notification(target_id: int, session: SessionDep, user: CurrentUser) -> NotificationTestOut:
    """Send a message of its own to the target, so the owner sees where it lands. It is sent even when the target is
    switched off or heard the same thing a moment ago."""

    return await operations.test_notification(target_id, session, user)
