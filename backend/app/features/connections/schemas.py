from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MethodOut(BaseModel):
    id: Literal["token", "oauth"]
    available: bool
    reason: str  # why it is not available, in words for the person


class FieldOut(BaseModel):
    key: str
    label: str
    placeholder: str
    help: str


class ProviderOut(BaseModel):
    id: str
    name: str
    category: str
    description: str
    icon: str
    token_help: str
    harness: str  # the harness this is the login of: used by all its agents, not chosen per project or agent
    methods: list[MethodOut]
    config_fields: list[FieldOut]


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    method: str
    account: str
    settings: dict[str, Any]
    connected_at: datetime
    checked_at: datetime | None
    needs_reconnect: bool = False  # stored, but unreadable (the secret key changed)


class ConnectionsOut(BaseModel):
    secret_key_secure: bool  # a credential is only stored under a real THEMIS_SECRET_KEY
    providers: list[ProviderOut]
    connections: list[ConnectionOut]


class TokenIn(BaseModel):
    provider: str
    token: str = Field(min_length=1, max_length=4096)


class LoginState(BaseModel):
    status: Literal["starting", "waiting", "connected", "failed", "cancelled"]
    verification_url: str
    code: str
    expires_at: datetime | None
    error: str


class BindingIn(BaseModel):
    connection_id: int
    config: dict[str, Any] = Field(default_factory=dict)


class BindingOut(BaseModel):
    provider: str
    connection_id: int
    account: str
    config: dict[str, Any]
