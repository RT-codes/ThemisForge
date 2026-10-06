"""Harnesses: what runs inside a cell for a task.

A harness turns a task into a plan (image, command, files to hand over) and turns the cell's raw output back into
a readable log. The cell contract (app/cells.py) stays the same for every harness, so adding another one (Pi, Claude
Code...) means adding a plan and a renderer here, nothing else.

Cells run the agent without the agent's own sandbox: the container is the sandbox, which is the one that works for
every harness.
"""

import json
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass

from .app_settings import AppSettings
from .cells import SECRETS_DIR
from .keys import ENV_NAME, key_path

HARNESSES = ("", "codex")  # "" = the placeholder program


@dataclass(frozen=True)
class HarnessInfo:
    """What the agent editor needs to know about a harness, so it only offers what the harness can do."""

    id: str
    label: str
    description: str
    supports_skills: bool = False
    supports_mcp: bool = False
    supports_keys: bool = False


CATALOG = (
    HarnessInfo(
        "codex",
        "Codex",
        "OpenAI's Codex CLI, signed in with your ChatGPT account (Settings, Codex).",
        supports_skills=True,
        supports_mcp=True,
        supports_keys=True,
    ),
)

CODEX_HOME = f"{SECRETS_DIR}/codex"
CODEX_AUTH = f"{CODEX_HOME}/auth.json"


# Codex may refresh its login while it runs. The refreshed file is printed (base64, between markers) on exit so the
# host can store it: the cell has nowhere durable to put it, and a lost refresh would force a reconnect.
def codex_script(model: str, effort: str, key_envs: Sequence[str] = ()) -> str:
    # model and effort are validated settings (no shell metacharacters), still quoted for good measure
    # Keys are exported from their in-memory files, so only the names are in this script (it is visible on the host).
    # Codex hides variables with KEY, SECRET or TOKEN in their name from the commands the agent runs, unless told not to.
    for env in key_envs:
        if not ENV_NAME.match(env):
            raise ValueError(f"Not a valid variable name: {env}")
    exports = "".join(f'export {env}="$(cat {key_path(env)})"\n' for env in key_envs)
    policy = "-c shell_environment_policy.ignore_default_excludes=true " if key_envs else ""
    return f"""\
export CODEX_HOME={CODEX_HOME}
{exports}echo "[codex] model {shlex.quote(model)}, reasoning effort {shlex.quote(effort)}"
trap 'echo "@@THEMIS-WRITEBACK-BEGIN {CODEX_AUTH}@@"; base64 < "$CODEX_HOME/auth.json" | tr -d "\\n"; echo; echo "@@THEMIS-WRITEBACK-END@@"' EXIT
codex exec -m {shlex.quote(model)} {policy}-c model_reasoning_effort={shlex.quote(effort)} -c model_reasoning_summary=detailed -c show_raw_agent_reasoning=true \\
  --json --skip-git-repo-check --ephemeral --dangerously-bypass-approvals-and-sandbox \\
  -C /workspace -o /cell/result.md -- "$(cat /cell/prompt.md)" < /dev/null
"""


@dataclass(frozen=True)
class HarnessPlan:
    image: str
    script: str
    writeback: tuple[str, ...] = ()
    uses_codex: bool = False


def plan_for(
    harness: str, cfg: AppSettings, *, model: str = "", effort: str = "", key_envs: Sequence[str] = ()
) -> HarnessPlan | None:
    """None means the placeholder program, which needs nothing special. An agent may choose its own model and
    reasoning effort (empty means the ones in Settings) and be given keys, available as these variables."""
    if harness == "codex":
        return HarnessPlan(
            image=cfg.codex_image,
            script=codex_script(model or cfg.codex_model, effort or cfg.codex_reasoning_effort, key_envs),
            writeback=(CODEX_AUTH,),
            uses_codex=True,
        )
    return None


def agent_preamble(name: str, role: str, instructions: str) -> str:
    """Who the agent is, put in front of every task it is given."""
    lines = [f"You are {name}" + (f", {role.strip()}." if role.strip() else ".")]
    if instructions.strip():
        lines.append(instructions.strip())
    return "\n\n".join(lines)


def folders_note(folders: Sequence[tuple[str, bool]]) -> str:
    """Tells the agent which shared folders exist (name, read only) and what they are for."""
    if not folders:
        return ""
    lines = [
        f"- /workspace/{name} ({'read only' if read_only else 'read and write'})"
        for name, read_only in folders
    ]
    return (
        "Shared folders. These are kept after this run, and other runs can see them, so put files others need "
        "there:\n" + "\n".join(lines)
    )


def build_prompt(
    title: str,
    description: str,
    properties: dict,
    *,
    preamble: str = "",
    folders: Sequence[tuple[str, bool]] = (),
) -> str:
    parts = [preamble] if preamble else []
    parts.append(f"# {title}")
    if description.strip():
        parts.append(description.strip())
    props = {k: v for k, v in properties.items() if v not in (None, "", [])}
    if props:
        parts.append("Task properties:\n" + "\n".join(f"- {k}: {v}" for k, v in props.items()))
    if note := folders_note(folders):
        parts.append(note)
    parts.append(
        "You are running unattended inside a throwaway container. Your working directory /workspace is private to "
        "this run. Do the task, then finish with a short summary of what you did and what you produced. Never read or "
        "print anything under /run/themis-secrets: it holds credentials, and everything you print is stored in the log."
    )
    return "\n\n".join(parts) + "\n"


_NOISE = {"Reading additional input from stdin..."}  # printed by codex exec whenever stdin is not a terminal


class CodexRenderer:
    """Turns `codex exec --json` events into a readable log, line by line. Unknown events are kept, shortened."""

    def __init__(self) -> None:
        self._buf = ""
        self._emitted = False
        self.usage: dict[str, int] = {}

    def feed(self, text: str) -> str:
        self._buf += text
        *lines, self._buf = self._buf.split("\n")
        return "".join(self._line(line) for line in lines)

    def flush(self) -> str:
        rest, self._buf = self._buf, ""
        return self._line(rest) if rest else ""

    def _line(self, line: str) -> str:
        line = line.rstrip("\r")
        if not line.strip():
            return ""
        if line.strip() in _NOISE:
            return ""
        try:
            event = json.loads(line)
        except ValueError:
            return line + "\n"  # a warning or anything else that is not an event
        if not isinstance(event, dict):
            return line + "\n"
        text = self._event(event)
        # blocks (what the agent said, thought, ran, and the summary) are set apart by a blank line
        starts_block = (
            bool(text) and text.startswith(("$ ", "[thinking]", "[codex] done")) or self._says(event)
        )
        if text and starts_block and self._emitted:
            text = "\n" + text
        self._emitted = self._emitted or bool(text)
        return text

    @staticmethod
    def _says(event: dict) -> bool:
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        return event.get("type") == "item.completed" and item.get("type") == "agent_message"

    def _event(self, e: dict) -> str:
        kind = e.get("type", "")
        item = e.get("item") if isinstance(e.get("item"), dict) else {}
        if kind == "thread.started":
            return f"[codex] session {e.get('thread_id', '')}\n"
        if kind == "turn.started":
            return ""
        if kind == "turn.completed":
            u = e.get("usage") or {}
            self.usage = {k: int(v) for k, v in u.items() if isinstance(v, int)}
            return f"[codex] done - {u.get('input_tokens', 0)} tokens in, {u.get('output_tokens', 0)} out\n"
        if kind in ("turn.failed", "error"):
            detail = e.get("message") or (e.get("error") or {}).get("message") or ""
            return f"[codex] error: {detail}\n"
        item_type = item.get("type", "")
        if kind == "item.started":
            if item_type == "command_execution":
                return f"$ {_shell(item.get('command', ''))}\n"
            return ""
        if kind == "item.completed":
            if item_type == "agent_message":
                return item.get("text", "").rstrip() + "\n"
            if item_type == "command_execution":
                out = (item.get("aggregated_output") or "").rstrip()
                code = item.get("exit_code")
                tail = f"[exit {code}]" if code not in (0, None) else ""
                return "".join(f"{s}\n" for s in (out, tail) if s)
            if item_type == "reasoning":
                text = (item.get("text") or "").strip()
                return f"[thinking] {text}\n" if text else ""
            return f"[codex] {item_type or kind}\n"
        return f"[codex] {kind}\n" if kind else ""


def _shell(command: str) -> str:
    """Codex wraps commands as `/bin/bash -lc "..."`; show the part a person wrote."""
    for prefix in ("/bin/bash -lc ", "bash -lc ", "/bin/sh -c ", "sh -c "):
        if command.startswith(prefix):
            inner = command[len(prefix) :].strip()
            if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "\"'":
                quote, inner = inner[0], inner[1:-1]
                if quote == '"':  # undo the escaping that quoting a command inside double quotes needs
                    inner = re.sub(r'\\(["\\$`])', r"\1", inner)
            return inner
    return command


def renderer_for(harness: str) -> CodexRenderer | None:
    return CodexRenderer() if harness == "codex" else None
