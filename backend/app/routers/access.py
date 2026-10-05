"""Invite-only access: strangers ask, the administrator approves, an invite link creates the account."""

import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from ..deps import AdminUser, SessionDep
from ..models import AccessRequest, Invite, RequestStatus, User, utcnow
from ..schemas import (
    AcceptInviteIn,
    AccessRequestIn,
    AccessRequestOut,
    InviteCreated,
    InviteIn,
    InviteInfo,
    InviteOut,
    UserOut,
)
from ..security import hash_password
from .auth import set_session_cookie

router = APIRouter(tags=["access"])

INVITE_DAYS = 7
MAX_PENDING_REQUESTS = 100  # the form is public: do not let it grow without bound


class Received(BaseModel):
    status: str = "received"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _email_taken(session, email: str) -> bool:
    return await session.scalar(select(User.id).where(User.email == email)) is not None


async def _new_invite(session, email: str, admin: User) -> InviteCreated:
    """One live invite per email: a new one replaces the old."""
    if await _email_taken(session, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "This email already has an account")
    await session.execute(delete(Invite).where(Invite.email == email, Invite.used_at.is_(None)))
    token = secrets.token_urlsafe(32)
    invite = Invite(
        email=email,
        token_hash=_hash(token),
        created_by=admin.id,
        expires_at=utcnow() + timedelta(days=INVITE_DAYS),
    )
    session.add(invite)
    await session.flush()
    return InviteCreated(
        id=invite.id, email=email, created_at=invite.created_at, expires_at=invite.expires_at, token=token
    )


# public: asking for access


@router.post("/access-requests", response_model=Received, status_code=status.HTTP_201_CREATED)
async def request_access(body: AccessRequestIn, session: SessionDep) -> Received:
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


# administrator: requests


@router.get("/access-requests", response_model=list[AccessRequestOut])
async def list_requests(session: SessionDep, _: AdminUser) -> list[AccessRequest]:
    rows = await session.scalars(select(AccessRequest).order_by(AccessRequest.id.desc()).limit(200))
    return list(rows.all())


async def _pending_request(session, request_id: int) -> AccessRequest:
    req = await session.get(AccessRequest, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if req.status != RequestStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request was already {req.status}")
    return req


@router.post("/access-requests/{request_id}/approve", response_model=InviteCreated)
async def approve_request(request_id: int, session: SessionDep, admin: AdminUser) -> InviteCreated:
    req = await _pending_request(session, request_id)
    invite = await _new_invite(session, req.email, admin)
    req.status = RequestStatus.APPROVED
    req.decided_at = utcnow()
    await session.commit()
    return invite


@router.post("/access-requests/{request_id}/deny", response_model=AccessRequestOut)
async def deny_request(request_id: int, session: SessionDep, _: AdminUser) -> AccessRequest:
    req = await _pending_request(session, request_id)
    req.status = RequestStatus.DENIED
    req.decided_at = utcnow()
    await session.commit()
    return req


# administrator: invites


@router.get("/invites", response_model=list[InviteOut])
async def list_invites(session: SessionDep, _: AdminUser) -> list[Invite]:
    rows = await session.scalars(
        select(Invite)
        .where(Invite.used_at.is_(None), Invite.expires_at > utcnow())
        .order_by(Invite.id.desc())
    )
    return list(rows.all())


@router.post("/invites", response_model=InviteCreated, status_code=status.HTTP_201_CREATED)
async def create_invite(body: InviteIn, session: SessionDep, admin: AdminUser) -> InviteCreated:
    invite = await _new_invite(session, body.email, admin)
    await session.commit()
    return invite


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: int, session: SessionDep, _: AdminUser) -> None:
    invite = await session.get(Invite, invite_id)
    if invite is None or invite.used_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")
    await session.delete(invite)
    await session.commit()


# public: using an invite


async def _live_invite(session, token: str) -> Invite:
    invite = await session.scalar(select(Invite).where(Invite.token_hash == _hash(token)))
    if invite is None or invite.used_at is not None or invite.expires_at <= utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invite link is invalid or has expired")
    return invite


@router.get("/invites/by-token/{token}", response_model=InviteInfo)
async def check_invite(token: str, session: SessionDep) -> InviteInfo:
    return InviteInfo(email=(await _live_invite(session, token)).email)


@router.post("/invites/by-token/{token}/accept", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def accept_invite(token: str, body: AcceptInviteIn, response: Response, session: SessionDep) -> User:
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
        raise HTTPException(status.HTTP_409_CONFLICT, "This email already has an account") from None
    set_session_cookie(response, user)
    return user
