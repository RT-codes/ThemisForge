from fastapi import APIRouter, Response, status

import app.features.identity.access_service as operations
from app.api.cookies import set_session_cookie
from app.api.dependencies import AdminUser, SessionDep
from app.features.identity.schemas import (
    AcceptInviteIn,
    AccessRequestIn,
    AccessRequestOut,
    InviteCreated,
    InviteIn,
    InviteInfo,
    InviteOut,
    Received,
    UserOut,
)
from app.persistence.models import AccessRequest, Invite, User

router = APIRouter(tags=["access"])


@router.post("/access-requests", response_model=Received, status_code=status.HTTP_201_CREATED)
async def request_access(body: AccessRequestIn, session: SessionDep) -> Received:
    """Always answers the same way, so it cannot be used to find out who has an account."""
    return await operations.request_access(body, session)


@router.get("/access-requests", response_model=list[AccessRequestOut])
async def list_requests(session: SessionDep, _: AdminUser) -> list[AccessRequest]:
    return await operations.list_requests(session, _)


@router.post("/access-requests/{request_id}/approve", response_model=InviteCreated)
async def approve_request(request_id: int, session: SessionDep, admin: AdminUser) -> InviteCreated:
    return await operations.approve_request(request_id, session, admin)


@router.post("/access-requests/{request_id}/deny", response_model=AccessRequestOut)
async def deny_request(request_id: int, session: SessionDep, _: AdminUser) -> AccessRequest:
    return await operations.deny_request(request_id, session, _)


@router.get("/invites", response_model=list[InviteOut])
async def list_invites(session: SessionDep, _: AdminUser) -> list[Invite]:
    return await operations.list_invites(session, _)


@router.post("/invites", response_model=InviteCreated, status_code=status.HTTP_201_CREATED)
async def create_invite(body: InviteIn, session: SessionDep, admin: AdminUser) -> InviteCreated:
    return await operations.create_invite(body, session, admin)


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: int, session: SessionDep, _: AdminUser) -> None:
    return await operations.revoke_invite(invite_id, session, _)


@router.get("/invites/by-token/{token}", response_model=InviteInfo)
async def check_invite(token: str, session: SessionDep) -> InviteInfo:
    return await operations.check_invite(token, session)


@router.post("/invites/by-token/{token}/accept", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def accept_invite(token: str, body: AcceptInviteIn, response: Response, session: SessionDep) -> User:
    user = await operations.accept_invite(token, body, session)
    set_session_cookie(response, user)
    return user
