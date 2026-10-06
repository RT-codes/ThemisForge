"""Keys given to an agent: how they are named inside the cell, and how they are kept out of the log.

A stored key reaches the cell as an in-memory file under /run/themis-secrets/keys, and the cell's start script exports it
as an environment variable (never as a docker argument, so it is not visible on the host's process list). The agent
and the tools it starts can use the variable. Everything the cell prints passes through a Redactor on its way to the
log, which replaces the key's value with [hidden]. That stops accidents (an `env` dump, an error message that echoes a
header); it cannot stop an agent that deliberately encodes the value, so only give keys to agents you trust with them.
"""

import re

from .cells import SECRETS_DIR

KEYS_DIR = f"{SECRETS_DIR}/keys"
HIDDEN = "[hidden]"
MIN_REDACTED = 4  # a shorter value would mangle ordinary text, and is not a real key anyway

# variables the cell or the tools in it rely on: a key never takes their place
RESERVED = {
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "PWD",
    "LANG",
    "TERM",
    "HOSTNAME",
    "CODEX_HOME",
    "TMPDIR",
    "NODE_ENV",
}
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def key_env_name(name: str) -> str:
    """The environment variable a key is available as: its name in capitals ("GitHub token" -> GITHUB_TOKEN)."""
    env = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
    if not env or env[0].isdigit():
        env = f"KEY_{env}".rstrip("_")
    if env in RESERVED or env.startswith("THEMIS_"):
        env = f"THEMIS_KEY_{env}"
    return env


def unique_env_names(keys: list[tuple[int, str]]) -> dict[int, str]:
    """Names for several keys at once, made different when two would come out the same."""
    used: dict[str, int] = {}
    out: dict[int, str] = {}
    for key_id, name in keys:
        base = key_env_name(name)
        env, n = base, 1
        while env in used:
            n += 1
            env = f"{base}_{n}"
        used[env] = key_id
        out[key_id] = env
    return out


def key_path(env: str) -> str:
    return f"{KEYS_DIR}/{env}"


class Redactor:
    """Replaces the values of the keys in use with [hidden] in whatever passes through."""

    def __init__(self, values: list[str]) -> None:
        # longest first, so a value that contains another one is hidden as a whole
        self.values = sorted({v for v in values if len(v) >= MIN_REDACTED}, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for value in self.values:
            if value in text:
                text = text.replace(value, HIDDEN)
        return text
