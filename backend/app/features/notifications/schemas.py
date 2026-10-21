from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: str = Field(max_length=20)
    # what the kind needs (see notifications.KINDS), by field name; stored encrypted and never returned
    config: dict[str, str] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=lambda: ["failed", "attention"], max_length=10)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("Name cannot be empty")
        return v


class NotificationPatch(BaseModel):
    """Only what is sent changes. `config` replaces the whole secret (it is never shown, so it cannot be edited)."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    config: dict[str, str] | None = None
    events: list[str] | None = Field(default=None, max_length=10)
    enabled: bool | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    kind: str
    enabled: bool
    hint: str  # the end of the secret, to tell targets apart; the rest is never shown
    events: list[str]
    last_sent_at: datetime | None
    last_error: str
    created_at: datetime


class NotificationTestOut(BaseModel):
    ok: bool
    detail: str = ""


class NotificationFieldOut(BaseModel):
    name: str
    label: str
    placeholder: str
    help: str


class NotificationKindOut(BaseModel):
    key: str
    label: str
    description: str
    fields: list[NotificationFieldOut]


class NotificationEventOut(BaseModel):
    key: str
    label: str


class NotificationOptions(BaseModel):
    """What a target can be: the services Themis can talk to and the events it can listen for. The form is built from
    this, so a new service needs no change in the app."""

    kinds: list[NotificationKindOut]
    events: list[NotificationEventOut]
