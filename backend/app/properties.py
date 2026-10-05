"""Custom Kanban properties: each project defines its own fields; tasks hold the values."""

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

PropertyType = Literal["text", "number", "select", "checkbox", "date"]


class PropertyDef(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    type: PropertyType = "text"
    options: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("options")
    @classmethod
    def clean_options(cls, v: list[str]) -> list[str]:
        cleaned = [o.strip() for o in v if o.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Select options must be unique")
        return cleaned


def validate_definitions(defs: list[PropertyDef]) -> list[dict[str, Any]]:
    keys = [d.key for d in defs]
    if len(set(keys)) != len(keys):
        raise ValueError("Property keys must be unique")
    for d in defs:
        if d.type == "select" and not d.options:
            raise ValueError(f"Select property '{d.name}' needs at least one option")
        if d.type != "select":
            d.options = []
    return [d.model_dump() for d in defs]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "property"


def clean_values(defs: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    """Validate task property values against the project definitions; unknown keys are dropped."""
    by_key = {d["key"]: d for d in defs}
    out: dict[str, Any] = {}
    for key, value in values.items():
        d = by_key.get(key)
        if d is None or value is None or value == "":
            continue
        kind = d["type"]
        if kind == "text":
            if not isinstance(value, str):
                raise ValueError(f"'{d['name']}' must be text")
            out[key] = value
        elif kind == "number":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"'{d['name']}' must be a number")
            out[key] = value
        elif kind == "checkbox":
            if not isinstance(value, bool):
                raise ValueError(f"'{d['name']}' must be true or false")
            out[key] = value
        elif kind == "select":
            if value not in d["options"]:
                raise ValueError(f"'{value}' is not an option of '{d['name']}'")
            out[key] = value
        elif kind == "date":
            try:
                date.fromisoformat(str(value))
            except ValueError:
                raise ValueError(f"'{d['name']}' must be a YYYY-MM-DD date") from None
            out[key] = str(value)
    return out
