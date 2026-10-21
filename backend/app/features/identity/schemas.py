from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    is_admin: bool


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class RegisterIn(LoginIn):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class SetupOut(BaseModel):
    needs_admin: bool  # no account exists yet: the next registration creates the administrator


class AccessRequestIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("name", "reason")
    @classmethod
    def strip_text(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("This field cannot be empty")
        return v


class AccessRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    reason: str
    status: str
    created_at: datetime
    decided_at: datetime | None


class InviteIn(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime
    expires_at: datetime


class InviteCreated(InviteOut):
    token: str  # shown once: only its hash is stored


class InviteInfo(BaseModel):
    email: str


class AcceptInviteIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class Received(BaseModel):
    status: str = "received"
