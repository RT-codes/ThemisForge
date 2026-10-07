"""Tool servers (MCP) for an agent: the settings Codex reads from $CODEX_HOME/config.toml.

The file is built for each run and goes into the cell as an in-memory file next to the Codex login, because it may
hold the values of keys. Codex reads it, starts every stdio server it lists and offers the tools to the agent
(checked against the real CLI).
"""

import json
import re
import shlex
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .harness import CODEX_HOME
from .keys import ENV_NAME

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
CONFIG_PATH = f"{CODEX_HOME}/config.toml"


class McpIn(BaseModel):
    """What a tool server is made of, as the API takes it and as the file in the config folder is checked."""

    name: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=2000)  # for people: what the tool is for
    kind: Literal["stdio", "http"] = "stdio"
    command: str = Field(default="", max_length=1000)
    args: list[str] = Field(default_factory=list, max_length=50)
    url: str = Field(default="", max_length=2000)
    env: dict[str, str] = Field(default_factory=dict)
    secret_env: dict[str, int] = Field(default_factory=dict)  # environment variable -> key id
    bearer_secret_id: int | None = None  # http: a key sent as a bearer token

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str) -> str:
        v = v.strip().lower()
        if not NAME.match(v):
            raise ValueError("Use lowercase letters, digits and dashes, starting with a letter or digit")
        return v

    @field_validator("args")
    @classmethod
    def short_args(cls, v: list[str]) -> list[str]:
        if any(len(a) > 2000 for a in v):
            raise ValueError("An argument is too long")
        return v

    @field_validator("env", "secret_env")
    @classmethod
    def valid_variable_names(cls, v: dict) -> dict:
        if len(v) > 50 or any(not ENV_NAME.match(k) for k in v):
            raise ValueError("Environment variable names use letters, digits and underscores")
        return v

    @model_validator(mode="after")
    def valid_for_kind(self) -> "McpIn":
        if self.kind == "http":
            if not self.url.strip().startswith(("http://", "https://")):
                raise ValueError("A web tool needs a URL that starts with http:// or https://")
            self.url, self.command, self.args = self.url.strip(), "", []
            self.env, self.secret_env = {}, {}
        else:
            command = self.command.strip()
            if not command:
                raise ValueError(
                    "A tool needs the command that starts it, such as: npx -y @scope/some-server"
                )
            if not self.args and any(c.isspace() for c in command):
                parts = shlex.split(command)  # "npx -y pkg" typed into the command box
                command, self.args = parts[0], parts[1:]
            self.command, self.url, self.bearer_secret_id = command, "", None
        return self


@dataclass(frozen=True)
class McpSpec:
    name: str
    kind: str  # "stdio" | "http"
    command: str = ""
    args: tuple[str, ...] = ()
    url: str = ""
    env: dict[str, str] = field(default_factory=dict)
    secret_env: dict[str, int] = field(default_factory=dict)  # environment variable -> key id
    bearer_secret_id: int | None = None

    @property
    def key_ids(self) -> set[int]:
        return set(self.secret_env.values()) | ({self.bearer_secret_id} if self.bearer_secret_id else set())


def _str(value: str) -> str:
    # a JSON string is a valid TOML basic string, so quotes, backslashes and newlines in a value cannot break out
    return json.dumps(value)


def config_toml(servers: list[McpSpec], values: dict[int, str], env_names: dict[int, str]) -> str:
    """Codex's config for these servers. `values` are the decrypted keys by id, `env_names` the variable each key is
    exported as (used for a bearer token, which Codex reads from the environment)."""
    out: list[str] = []
    for s in servers:
        out.append(f"[mcp_servers.{s.name}]")
        if s.kind == "http":
            out.append(f"url = {_str(s.url)}")
            if s.bearer_secret_id is not None:
                out.append(f"bearer_token_env_var = {_str(env_names[s.bearer_secret_id])}")
        else:
            out.append(f"command = {_str(s.command)}")
            out.append("args = [" + ", ".join(_str(a) for a in s.args) + "]")
            env = {**s.env, **{k: values[i] for k, i in s.secret_env.items()}}
            if env:
                out.append("")
                out.append(f"[mcp_servers.{s.name}.env]")
                out += [f"{k} = {_str(v)}" for k, v in env.items()]
        out.append("")
    return "\n".join(out)


# ----- trying a connection -----

PROBE_SECONDS = 15
MAX_REPLY = 1_000_000  # bytes read from a server being tried: a test must not be able to fill memory
PROTOCOL = "2025-03-26"


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    message: str  # for people
    tools: tuple[str, ...] = ()  # what the server offers, when it answered


def _rpc(method: str, params: dict | None = None, request_id: int | None = None) -> dict:
    body: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if request_id is not None:
        body["id"] = request_id
    return body


def _reply(content_type: str, raw: bytes, request_id: int) -> dict | None:
    """The JSON-RPC answer in a reply, which a web MCP server sends either as JSON or as a server-sent event."""
    text = raw.decode(errors="replace")
    candidates = (
        [line.removeprefix("data:").strip() for line in text.splitlines() if line.startswith("data:")]
        if "text/event-stream" in content_type
        else [text]
    )
    for candidate in candidates:
        try:
            message = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(message, dict) and message.get("id") == request_id:
            return message
    return None


async def probe_http(url: str, bearer: str | None) -> ProbeResult:
    """Starts a session with a web MCP server and asks what it offers, like an agent's first minute with it.

    Redirects are not followed and only the server's name and its tools' names are kept from the answers."""
    import httpx  # imported here: only a connection test needs it

    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    async def call(client: httpx.AsyncClient, body: dict, request_id: int | None):
        async with client.stream("POST", url, headers=headers, json=body) as response:
            raw = b""
            async for chunk in response.aiter_bytes():
                raw += chunk
                if len(raw) > MAX_REPLY:
                    break
            return response, (
                _reply(response.headers.get("content-type", ""), raw, request_id) if request_id else None
            )

    try:
        async with httpx.AsyncClient(timeout=PROBE_SECONDS, follow_redirects=False) as client:
            first, hello = await call(
                client,
                _rpc(
                    "initialize",
                    {
                        "protocolVersion": PROTOCOL,
                        "capabilities": {},
                        "clientInfo": {"name": "themis", "version": "1"},
                    },
                    1,
                ),
                1,
            )
            if first.status_code in (401, 403):
                return ProbeResult(
                    False, f"The server refused the connection (HTTP {first.status_code}). Check the key."
                )
            if first.status_code >= 300:
                return ProbeResult(
                    False, f"The address answered with HTTP {first.status_code}, which is not an MCP server."
                )
            if hello is None or "result" not in hello:
                return ProbeResult(False, "The address answered, but not like an MCP server.")
            if session := first.headers.get("mcp-session-id"):
                headers["Mcp-Session-Id"] = session
            await call(client, _rpc("notifications/initialized"), None)
            _, listing = await call(client, _rpc("tools/list", {}, 2), 2)
    except httpx.TimeoutException:
        return ProbeResult(False, f"The server did not answer within {PROBE_SECONDS} seconds.")
    except httpx.ConnectError:
        return ProbeResult(
            False, "Could not connect to that address. Check it, and that the server is running."
        )
    except httpx.HTTPError as e:
        return ProbeResult(False, f"The connection failed: {str(e)[:200] or type(e).__name__}")
    info = hello["result"].get("serverInfo") or {}
    who = f"{info.get('name')} {info.get('version', '')}".strip() if info.get("name") else "The server"
    tools = tuple(
        t["name"]
        for t in ((listing or {}).get("result") or {}).get("tools", [])
        if isinstance(t, dict) and "name" in t
    )
    return ProbeResult(
        True, f"Connected to {who}. It offers {len(tools)} tool{'s' if len(tools) != 1 else ''}.", tools
    )
