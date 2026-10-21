from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.execution.harnesses.catalog import clean_model_name
from app.execution.harnesses.types import AgentHarness, Effort
from app.execution.profiles import ProfileOverrides
from app.features.project_config.common import ConfigError


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(
            flow, False
        )  # list items are indented under their setting, as people write them


def _long_text_as_block(dumper: yaml.SafeDumper, value: str):
    # a description with line breaks reads as written instead of as one quoted line full of \n
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


_Dumper.add_representer(str, _long_text_as_block)


def _dump(data: dict[str, Any]) -> str:
    return yaml.dump(
        data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
    )


def _load(text: str, what: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as e:
        problem = getattr(e, "problem", None) or "it is not valid"
        line = f" (line {e.problem_mark.line + 1})" if getattr(e, "problem_mark", None) else ""
        raise ConfigError(f"The {what} cannot be read{line}: {problem}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"The {what} must be a list of 'setting: value' lines")
    return {k: v for k, v in data.items() if v is not None}  # "model:" with nothing after it means "not set"


def _checked[T: BaseModel](model: type[T], data: dict[str, Any]) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0]
        where = ".".join(str(p) for p in err["loc"])
        if err["type"] == "extra_forbidden":
            raise ConfigError(f"'{where}' is not a setting here") from None
        raise ConfigError(
            f"{where}: {err['msg'].removeprefix('Value error, ')}" if where else err["msg"]
        ) from None


def split_frontmatter(text: str) -> tuple[str, str]:
    """The lines between the two --- lines at the top, and the text after them."""
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    if lines[0].strip() != "---":
        raise ConfigError("The file must start with a --- line, then the settings, then another --- line")
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ConfigError("The first --- line is never closed: add a --- line after the settings")
    body = "\n".join(lines[end + 1 :])
    return "\n".join(lines[1:end]), body.removeprefix("\n").removesuffix("\n")


class FolderRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    mode: Literal["ro", "rw"] = "rw"


class AgentFile(BaseModel):
    """An agent.md, by names (a row refers to the same things by id)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    harness: AgentHarness = "codex"
    model: str = Field(default="", max_length=100)
    reasoning_effort: Effort | Literal[""] = ""
    cell: ProfileOverrides | None = None
    folders: list[FolderRef] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=50)
    tools: list[str] = Field(default_factory=list, max_length=50)
    keys: list[str] = Field(default_factory=list, max_length=50)
    connections: list[str] = Field(
        default_factory=list, max_length=50
    )  # providers, see app/features/connections/service.py
    instructions: str = Field(default="", max_length=20_000)  # the text below the settings

    @field_validator("name", "role")
    @classmethod
    def trimmed(cls, v: str) -> str:
        return v.strip()

    @field_validator("name")
    @classmethod
    def named(cls, v: str) -> str:
        if not v:
            raise ValueError("The name cannot be empty")
        return v

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str) -> str:
        return clean_model_name(v)


def parse_agent(text: str) -> AgentFile:
    settings_text, body = split_frontmatter(text)
    data = _load(settings_text, "settings at the top of the file")
    if "instructions" in data:
        raise ConfigError("The instructions are the text below the settings, not a setting")
    return _checked(AgentFile, {**data, "instructions": body})


def render_agent(af: AgentFile) -> str:
    meta: dict[str, Any] = {
        "name": af.name,
        "role": af.role,
        "description": af.description,
        "harness": af.harness,
        "model": af.model,
        "reasoning_effort": af.reasoning_effort,
    }
    if af.cell and (cell := af.cell.clean()):
        meta["cell"] = cell  # left out when the agent just uses the project's cell
    meta["folders"] = [f.model_dump() for f in af.folders]
    meta["skills"], meta["tools"], meta["keys"] = af.skills, af.tools, af.keys
    meta["connections"] = af.connections
    return f"---\n{_dump(meta)}---\n\n{af.instructions}\n" if af.instructions else f"---\n{_dump(meta)}---\n"


class McpFile(BaseModel):
    """A mcp/<name>.yaml. The name is the file's name, so a tool cannot be called one thing and filed as another."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(default="", max_length=2000)
    kind: Literal["stdio", "http"] = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    keys: dict[str, str] = Field(default_factory=dict)  # environment variable -> the name of a stored key
    bearer_key: str = ""  # http: the stored key sent as a bearer token
    auth: str = ""  # http: the way the server signs people in (app/mcp_auth), instead of a key; "" for none

    @field_validator("args", mode="before")
    @classmethod
    def args_as_text(cls, v: Any) -> Any:
        return [str(a) for a in v] if isinstance(v, list) else v  # `- 8080` is a number to YAML

    @field_validator("env", mode="before")
    @classmethod
    def values_as_text(cls, v: Any) -> Any:
        return {k: str(x) for k, x in v.items()} if isinstance(v, dict) else v


def parse_mcp(text: str) -> McpFile:
    return _checked(McpFile, _load(text, "file"))


def render_mcp(mf: McpFile) -> str:
    meta: dict[str, Any] = {"description": mf.description, "kind": mf.kind}
    if mf.kind == "http":
        meta["url"] = mf.url
        if mf.bearer_key:
            meta["bearer_key"] = mf.bearer_key
        if mf.auth:
            meta["auth"] = mf.auth
    else:
        meta["command"], meta["args"] = mf.command, mf.args
        if mf.env:
            meta["env"] = mf.env
        if mf.keys:
            meta["keys"] = mf.keys
    return _dump(meta)
