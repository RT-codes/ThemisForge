from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import notifications
from ..deps import CurrentUser, SessionDep
from ..models import NotificationTarget, Project, utcnow
from ..schemas import (
    NotificationEventOut,
    NotificationFieldOut,
    NotificationIn,
    NotificationKindOut,
    NotificationOptions,
    NotificationOut,
    NotificationPatch,
    NotificationTestOut,
)

router = APIRouter(tags=["notifications"])


def _bad(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


async def _project(session: AsyncSession, project_id: int, user: CurrentUser) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


async def _target(session: AsyncSession, target_id: int, user: CurrentUser) -> NotificationTarget:
    target = await session.get(NotificationTarget, target_id)
    project = await session.get(Project, target.project_id) if target else None
    if target is None or project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return target


def _events(events: list[str]) -> list[str]:
    if unknown := [e for e in events if e not in notifications.EVENTS]:
        raise _bad(f"Unknown event: {unknown[0]}")
    return [e for e in notifications.EVENTS if e in events]  # in the order the app lists them, each once


def _packed(kind: str, config: dict[str, str]) -> tuple[str, str]:
    try:
        return notifications.pack(kind, config)
    except ValueError as e:
        raise _bad(str(e)) from None


@router.get("/notification-options", response_model=NotificationOptions)
async def options(user: CurrentUser) -> NotificationOptions:
    return NotificationOptions(
        kinds=[
            NotificationKindOut(
                key=key,
                label=kind.label,
                description=kind.description,
                fields=[NotificationFieldOut(**vars(f)) for f in kind.fields],
            )
            for key, kind in notifications.KINDS.items()
        ],
        events=[NotificationEventOut(key=k, label=label) for k, label in notifications.EVENTS.items()],
    )


@router.get("/projects/{project_id}/notifications", response_model=list[NotificationOut])
async def list_notifications(
    project_id: int, session: SessionDep, user: CurrentUser
) -> list[NotificationTarget]:
    await _project(session, project_id, user)
    rows = await session.scalars(
        select(NotificationTarget)
        .where(NotificationTarget.project_id == project_id)
        .order_by(NotificationTarget.id)
    )
    return list(rows)


@router.post(
    "/projects/{project_id}/notifications",
    response_model=NotificationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification(
    project_id: int, body: NotificationIn, session: SessionDep, user: CurrentUser
) -> NotificationTarget:
    await _project(session, project_id, user)
    encrypted, hint = _packed(body.kind, body.config)
    target = NotificationTarget(
        project_id=project_id,
        name=body.name,
        kind=body.kind,
        enabled=body.enabled,
        config_encrypted=encrypted,
        hint=hint,
        events=_events(body.events),
    )
    session.add(target)
    await session.commit()
    return target


@router.patch("/notifications/{target_id}", response_model=NotificationOut)
async def update_notification(
    target_id: int, body: NotificationPatch, session: SessionDep, user: CurrentUser
) -> NotificationTarget:
    target = await _target(session, target_id, user)
    if body.name is not None:
        target.name = body.name.strip() or target.name
    if body.enabled is not None:
        target.enabled = body.enabled
    if body.events is not None:
        target.events = _events(body.events)
    if body.config is not None:
        target.config_encrypted, target.hint = _packed(target.kind, body.config)
        target.last_error = ""  # a new address gets a fresh start
    await session.commit()
    return target


@router.delete("/notifications/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(target_id: int, session: SessionDep, user: CurrentUser) -> None:
    await session.delete(await _target(session, target_id, user))
    await session.commit()


@router.post("/notifications/{target_id}/test", response_model=NotificationTestOut)
async def test_notification(target_id: int, session: SessionDep, user: CurrentUser) -> NotificationTestOut:
    """Send a message of its own to the target, so the owner sees where it lands. It is sent even when the target is
    switched off or heard the same thing a moment ago."""
    target = await _target(session, target_id, user)
    project = await session.get(Project, target.project_id)
    assert project is not None
    error = await notifications.deliver(
        target, notifications.Notice("test", "Themis can reach this place.", "", project.name)
    )
    target.last_error = error
    if not error:
        target.last_sent_at = utcnow()
    await session.commit()
    return NotificationTestOut(ok=not error, detail=error)
