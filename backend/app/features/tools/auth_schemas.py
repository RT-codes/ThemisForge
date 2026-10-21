from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LoginOut(BaseModel):
    """A stored sign in as people see it. Which of their tools use it is told by the tools, not here."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    resource: str
    scheme: str
    status: Literal["active", "needs_sign_in"]
    error: str
    account: str
    expires_at: datetime | None
    refreshed_at: datetime | None
    connected_at: datetime


class ToolSignIn(BaseModel):
    """Where a tool that signs in stands, for the owner of its project."""

    state: Literal["signed_in", "needs_sign_in", "not_signed_in"]
    method: str  # the scheme's label, such as "Sign in with the service"
    login_id: int | None
    account: str
    error: str
    expires_at: datetime | None


class SignInIn(BaseModel):
    return_to: str = "/"  # the page to come back to, as a path


class SignInOut(BaseModel):
    url: str  # where to send the person's browser
