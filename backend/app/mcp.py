"""Tool servers (MCP) for an agent: the settings Codex reads from $CODEX_HOME/config.toml.

The file is built for each run and goes into the cell as an in-memory file next to the Codex login, because it may
hold the values of keys. Codex reads it, starts every stdio server it lists and offers the tools to the agent
(checked against the real CLI).
"""

import json
import re
from dataclasses import dataclass, field

from .harness import CODEX_HOME

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
CONFIG_PATH = f"{CODEX_HOME}/config.toml"


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
