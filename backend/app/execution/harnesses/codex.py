import json
import re
import shlex
from collections.abc import Sequence

from app.execution.cells.contract import SECRETS_DIR
from app.execution.harnesses.rendering import _NOISE, HarnessRenderer, trim_output
from app.execution.harnesses.types import TokenUsage
from app.features.tools.keys import ENV_NAME, key_path

CODEX_HOME = f"{SECRETS_DIR}/codex"


CODEX_AUTH = f"{CODEX_HOME}/auth.json"


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


_CODEX_TRANSIENT = (
    "at capacity",
    "overloaded",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "internal server error",
    "stream disconnected",
)


_CODEX_LOGIN_REJECTED = (
    "refresh token was already used",
    "refresh token has already been used",
    "refresh_token_reused",
    "log out and sign in again",
)


class CodexRenderer(HarnessRenderer):
    """Turns `codex exec --json` events into a readable log. Unknown events are kept, shortened."""

    name = "Codex"
    transient_markers = _CODEX_TRANSIENT
    login_markers = _CODEX_LOGIN_REJECTED

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
            self.usage = TokenUsage.from_event(u)
            return f"[codex] done - {u.get('input_tokens', 0)} tokens in, {u.get('output_tokens', 0)} out\n"
        if kind in ("turn.failed", "error"):
            detail = e.get("message") or (e.get("error") or {}).get("message") or ""
            self.error = detail
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
                out = trim_output((item.get("aggregated_output") or "").rstrip())
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
