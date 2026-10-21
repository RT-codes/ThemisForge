from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.errors import ApplicationError
from app.features.identity.schemas import (
    AcceptInviteIn,
    AccessRequestIn,
    InviteCreated,
    InviteIn,
    InviteInfo,
    Received,
)
from app.persistence.models import AccessRequest, Invite, RequestStatus, User, utcnow
from app.security import hash_password, hash_secret, new_secret

INVITE_DAYS = 7


MAX_PENDING_REQUESTS = 100  # the form is public: do not let it grow without bound


async def _email_taken(session, email: str) -> bool:
    return await session.scalar(select(User.id).where(User.email == email)) is not None


async def _new_invite(session, email: str, admin: User) -> InviteCreated:
    """One live invite per email: a new one replaces the old."""
    if await _email_taken(session, email):
        raise ApplicationError(status.HTTP_409_CONFLICT, "This email already has an account")
    await session.execute(delete(Invite).where(Invite.email == email, Invite.used_at.is_(None)))
    token, token_hash, _ = new_secret()
    invite = Invite(
        email=email,
        token_hash=token_hash,
        created_by=admin.id,
        expires_at=utcnow() + timedelta(days=INVITE_DAYS),
    )
    session.add(invite)
    await session.flush()
    return InviteCreated(
        id=invite.id, email=email, created_at=invite.created_at, expires_at=invite.expires_at, token=token
    )


async def request_access(body: AccessRequestIn, session: AsyncSession) -> Received:
    """Always answers the same way, so it cannot be used to find out who has an account."""
    pending = await session.scalar(
        select(func.count()).select_from(AccessRequest).where(AccessRequest.status == RequestStatus.PENDING)
    )
    already = await session.scalar(
        select(AccessRequest.id).where(
            AccessRequest.email == body.email, AccessRequest.status == RequestStatus.PENDING
        )
    )
    if (
        (pending or 0) < MAX_PENDING_REQUESTS
        and already is None
        and not await _email_taken(session, body.email)
    ):
        session.add(AccessRequest(name=body.name, email=body.email, reason=body.reason))
        await session.commit()
    return Received()


async def list_requests(session: AsyncSession, _: User) -> list[AccessRequest]:
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    rows = await session.scalars(select(AccessRequest).order_by(AccessRequest.id.desc()).limit(200))
    return list(rows.all())


async def _pending_request(session, request_id: int) -> AccessRequest:
    req = await session.get(AccessRequest, request_id)
    if req is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Request not found")
    if req.status != RequestStatus.PENDING:
        raise ApplicationError(status.HTTP_409_CONFLICT, f"This request was already {req.status}")
    return req


async def approve_request(request_id: int, session: AsyncSession, admin: User) -> InviteCreated:
    if not admin.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    req = await _pending_request(session, request_id)
    invite = await _new_invite(session, req.email, admin)
    req.status = RequestStatus.APPROVED
    req.decided_at = utcnow()
    await session.commit()
    return invite


async def deny_request(request_id: int, session: AsyncSession, _: User) -> AccessRequest:
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    req = await _pending_request(session, request_id)
    req.status = RequestStatus.DENIED
    req.decided_at = utcnow()
    await session.commit()
    return req


async def list_invites(session: AsyncSession, _: User) -> list[Invite]:
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    rows = await session.scalars(
        select(Invite)
        .where(Invite.used_at.is_(None), Invite.expires_at > utcnow())
        .order_by(Invite.id.desc())
    )
    return list(rows.all())


async def create_invite(body: InviteIn, session: AsyncSession, admin: User) -> InviteCreated:
    if not admin.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    invite = await _new_invite(session, body.email, admin)
    await session.commit()
    return invite


async def revoke_invite(invite_id: int, session: AsyncSession, _: User) -> None:
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    invite = await session.get(Invite, invite_id)
    if invite is None or invite.used_at is not None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Invite not found")
    await session.delete(invite)
    await session.commit()


async def _live_invite(session, token: str) -> Invite:
    invite = await session.scalar(select(Invite).where(Invite.token_hash == hash_secret(token)))
    if invite is None or invite.used_at is not None or invite.expires_at <= utcnow():
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "This invite link is invalid or has expired")
    return invite


async def check_invite(token: str, session: AsyncSession) -> InviteInfo:
    return InviteInfo(email=(await _live_invite(session, token)).email)


async def accept_invite(token: str, body: AcceptInviteIn, session: AsyncSession) -> User:
    invite = await _live_invite(session, token)
    user = User(
        email=invite.email,
        name=body.name.strip(),
        password_hash=await hash_password(body.password),
        is_admin=False,
    )
    session.add(user)
    invite.used_at = utcnow()
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ApplicationError(status.HTTP_409_CONFLICT, "This email already has an account") from None
    return user
