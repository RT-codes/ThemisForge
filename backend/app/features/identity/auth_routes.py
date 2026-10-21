from fastapi import APIRouter, Response, status

import app.features.identity.auth_service as operations
from app.api.cookies import set_session_cookie
from app.api.dependencies import COOKIE_NAME, CurrentUser, SessionDep
from app.features.identity.schemas import LoginIn, RegisterIn, SetupOut, UserOut
from app.persistence.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/setup", response_model=SetupOut)
async def setup(session: SessionDep) -> SetupOut:
    return await operations.setup(session)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, response: Response, session: SessionDep) -> User:
    """Creates the administrator. Everyone after that joins through an invite."""
    user = await operations.register(body, session)
    set_session_cookie(response, user)
    return user


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, response: Response, session: SessionDep) -> User:
    user = await operations.login(body, session)
    set_session_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
