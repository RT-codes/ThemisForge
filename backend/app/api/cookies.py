"""Session-cookie details shared by authentication HTTP adapters."""

from fastapi import Response

from app.api.dependencies import COOKIE_NAME
from app.config import settings
from app.persistence.models import User
from app.security import create_token


def set_session_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_token(user.id),
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
