from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..deps import COOKIE_NAME, CurrentUser, SessionDep
from ..models import User
from ..schemas import LoginIn, RegisterIn, SetupOut, UserOut
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_token(user.id),
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


@router.get("/setup", response_model=SetupOut)
async def setup(session: SessionDep) -> SetupOut:
    return SetupOut(needs_admin=await session.scalar(select(User.id).limit(1)) is None)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, response: Response, session: SessionDep) -> User:
    """Creates the administrator. Everyone after that joins through an invite."""
    if await session.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is invite only. Request access instead.")
    user = User(
        email=body.email,
        name=body.name.strip(),
        password_hash=await hash_password(body.password),
        is_admin=True,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:  # two first registrations at once: the loser is just another stranger
        await session.rollback()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Registration is invite only. Request access instead."
        ) from None
    set_session_cookie(response, user)
    return user


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, response: Response, session: SessionDep) -> User:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not await verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    set_session_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
