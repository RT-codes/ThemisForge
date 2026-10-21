from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.errors import ApplicationError
from app.features.identity.schemas import LoginIn, RegisterIn, SetupOut
from app.persistence.models import User
from app.security import hash_password, verify_password


async def setup(session: AsyncSession) -> SetupOut:
    return SetupOut(needs_admin=await session.scalar(select(User.id).limit(1)) is None)


async def register(body: RegisterIn, session: AsyncSession) -> User:
    """Creates the administrator. Everyone after that joins through an invite."""
    if await session.scalar(select(User.id).limit(1)) is not None:
        raise ApplicationError(
            status.HTTP_403_FORBIDDEN, "Registration is invite only. Request access instead."
        )
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
        raise ApplicationError(
            status.HTTP_403_FORBIDDEN, "Registration is invite only. Request access instead."
        ) from None
    return user


async def login(body: LoginIn, session: AsyncSession) -> User:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not await verify_password(body.password, user.password_hash):
        raise ApplicationError(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return user
