from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

import app.features.notifications.delivery as notifications
from app.errors import ApplicationError
from app.features.notifications.schemas import (
    NotificationEventOut,
    NotificationFieldOut,
    NotificationIn,
    NotificationKindOut,
    NotificationOptions,
    NotificationPatch,
    NotificationTestOut,
)
from app.features.projects.access import require_project
from app.persistence.models import NotificationTarget, Project, User, utcnow


def _bad(detail: str) -> ApplicationError:
    return ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


async def _target(session: AsyncSession, target_id: int, user: User) -> NotificationTarget:
    target = await session.get(NotificationTarget, target_id)
    project = await session.get(Project, target.project_id) if target else None
    if target is None or project is None or project.owner_id != user.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Notification not found")
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


async def options(user: User) -> NotificationOptions:
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


async def list_notifications(project_id: int, session: AsyncSession, user: User) -> list[NotificationTarget]:
    await require_project(session, project_id, user)
    rows = await session.scalars(
        select(NotificationTarget)
        .where(NotificationTarget.project_id == project_id)
        .order_by(NotificationTarget.id)
    )
    return list(rows)


async def create_notification(
    project_id: int, body: NotificationIn, session: AsyncSession, user: User
) -> NotificationTarget:
    await require_project(session, project_id, user)
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


async def update_notification(
    target_id: int, body: NotificationPatch, session: AsyncSession, user: User
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


async def delete_notification(target_id: int, session: AsyncSession, user: User) -> None:
    await session.delete(await _target(session, target_id, user))
    await session.commit()


async def test_notification(target_id: int, session: AsyncSession, user: User) -> NotificationTestOut:
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
