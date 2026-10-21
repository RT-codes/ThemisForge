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
from dataclasses import astuple, dataclass, fields
from typing import Literal

from .app_settings import AppSettings
from .cells import SECRETS_DIR
from .keys import ENV_NAME, key_path

HARNESSES = ("", "codex", "claude")  # "" = the placeholder program
AGENT_HARNESSES = ("codex", "claude")
AgentHarness = Literal[
    "codex", "claude"
]  # the same list, for schemas  # the ones that run an AI agent (so get keys, tools and a login)

# Every reasoning effort a Codex model can have, weakest first. A model supports some of them (CodexModel.efforts).
Effort = Literal["low", "medium", "high", "xhigh", "max", "ultra"]


@dataclass(frozen=True)
class ModelInfo:
    """A model the editors offer in a dropdown, with the reasoning efforts it accepts."""

    id: str
    label: str
    efforts: tuple[str, ...]
    default_effort: str  # what Codex itself uses when no effort is asked for


@dataclass(frozen=True)
class HarnessInfo:
    """What the agent editor needs to know about a harness, so it only offers what the harness can do."""

    id: str
    label: str
    description: str
    supports_skills: bool = False
    supports_mcp: bool = False
    supports_keys: bool = False
    models: tuple[ModelInfo, ...] = ()  # empty: the harness has no model to choose


_BASE = ("low", "medium", "high", "xhigh", "max")

# The models Codex lists for a ChatGPT login (the `models` of ~/.codex/models_cache.json, hidden ones left out), newest
# first. A model that is not here still works when typed into an agent file or Settings; the editors keep showing it.
# Keep this in step with the Codex CLI when it gets new models.
CODEX_MODELS = (
    ModelInfo("gpt-6.1-sol", "GPT-6.1 Sol", (*_BASE, "ultra"), "low"),
    ModelInfo("gpt-6-astra", "GPT-6 Astra", (*_BASE, "ultra"), "low"),
    ModelInfo("gpt-6-sol", "GPT-6 Sol", (*_BASE, "ultra"), "medium"),
    ModelInfo("gpt-6-luna", "GPT-6 Luna", _BASE, "medium"),
    ModelInfo("gpt-5.6-sol", "GPT-5.6 Sol", (*_BASE, "ultra"), "low"),
    ModelInfo("gpt-5.6-terra", "GPT-5.6 Terra", (*_BASE, "ultra"), "medium"),
    ModelInfo("gpt-5.6-luna", "GPT-5.6 Luna", _BASE, "medium"),
)

# The Claude models Claude Code can run. Like the list above, a model that is not here still works when typed into an
# agent file or Settings.
CLAUDE_MODELS = (
    ModelInfo("claude-fable-5-1", "Fable 5.1", _BASE, "high"),
    ModelInfo("claude-opus-5-5", "Opus 5.5", _BASE, "high"),
    ModelInfo("claude-sonnet-5-5", "Sonnet 5.5", _BASE, "medium"),
    ModelInfo("claude-haiku-5-5", "Haiku 5.5", ("low", "medium", "high"), "medium"),
)


def effort_for(model: str, effort: str) -> str:
    """The effort a run really gets. The model, the effort or both can come from different layers (a workflow step
    overriding the model of an agent that asks for `ultra`), so an effort the model does not accept falls back to the
    model's own default instead of failing the run. A model that is not in the list is trusted as it is."""
    known = next((m for m in (*CODEX_MODELS, *CLAUDE_MODELS) if m.id == model), None)
    return known.default_effort if known and effort not in known.efforts else effort


CATALOG = (
    HarnessInfo(
        "codex",
        "Codex",
        "OpenAI's Codex CLI, signed in with your ChatGPT account (Settings, Codex).",
        supports_skills=True,
        supports_mcp=True,
        supports_keys=True,
        models=CODEX_MODELS,
    ),
    HarnessInfo(
        "claude",
        "Claude Code",
        "Anthropic's Claude Code CLI, signed in with your Claude subscription (Settings, Claude).",
        supports_skills=True,
        supports_mcp=True,
        supports_keys=True,
        models=CLAUDE_MODELS,
    ),
)


def defaults_for(harness: str, cfg: AppSettings) -> tuple[str, str, str]:
    """The (image, model, effort) Settings give a harness when an agent does not choose its own."""
    if harness == "claude":
        return cfg.claude_image, cfg.claude_model, cfg.claude_reasoning_effort
    return cfg.codex_image, cfg.codex_model, cfg.codex_reasoning_effort


def clean_model_name(v: str) -> str:
    """A model name ends up on a command line, so nothing a shell would treat specially gets through."""
    v = v.strip()
    if v and (v.startswith("-") or any(c.isspace() or c in "'\"$`\\;&|<>" for c in v)):
        raise ValueError("Invalid model name")
    return v


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


CLAUDE_MCP = (
    f"{SECRETS_DIR}/claude-mcp.json"  # written by the scheduler when the agent has tool servers (app/mcp.py)
)

# Claude Code has no flag for "write the final answer to a file", so the cell does it: the stream is kept, and its
# last `result` event holds the answer. The program's exit code is 1 when that event says the run failed, so a run that
# Claude Code ended with an error is a failed run even when the CLI itself exited 0.
_CLAUDE_RESULT = (
    'let r;for(const l of require("fs").readFileSync("/tmp/claude-stream.jsonl","utf8").split("\\n"))'
    '{try{const e=JSON.parse(l);if(e.type==="result")r=e}catch{}}'
    'if(r&&typeof r.result==="string"&&r.result)require("fs").writeFileSync("/cell/result.md",r.result);'
    "process.exit(!r||r.is_error?1:0)"
)


def claude_script(model: str, effort: str, key_envs: Sequence[str] = ()) -> str:
    """The shell script of a Claude Code cell. Claude Code reads the prompt from stdin, runs without its permission
    prompts (the cell is the sandbox, and it refuses to do so as root, which cells never are) and prints one JSON event
    per line. The login is the variable exported from the key file the connection provides (app/claude.py)."""
    for env in key_envs:
        if not ENV_NAME.match(env):
            raise ValueError(f"Not a valid variable name: {env}")
    exports = "".join(f'export {env}="$(cat {key_path(env)})"\n' for env in key_envs)
    # no updater, no telemetry: a cell has no use for either, and both would only add noise or delay to a run
    return f"""\
export DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
{exports}echo "[claude] model {shlex.quote(model)}, effort {shlex.quote(effort)}"
cd /workspace
mcp=; [ -f {CLAUDE_MCP} ] && mcp="--strict-mcp-config --mcp-config {CLAUDE_MCP}"
{{ claude -p --model {shlex.quote(model)} --effort {shlex.quote(effort)} --output-format stream-json --verbose \\
  --dangerously-skip-permissions --no-session-persistence $mcp < /cell/prompt.md; echo $? > /tmp/claude-status; }} \\
  | tee /tmp/claude-stream.jsonl
node -e {shlex.quote(_CLAUDE_RESULT)}; found=$?
code=$(cat /tmp/claude-status 2>/dev/null || echo 1)
[ "$code" -ne 0 ] && exit "$code"
exit "$found"
"""


@dataclass(frozen=True)
class TokenUsage:
    """The tokens a run spent, as the harness reports them. Cached input is part of the input and reasoning part of
    the output, so the four numbers are not meant to be added up. Prices are worked out from these later, which is
    why they are kept as reported and not as money."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0

    @classmethod
    def from_event(cls, usage: dict) -> "TokenUsage":
        return cls(**{f.name: v for f in fields(cls) if isinstance(v := usage.get(f.name), int)})

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(*(a + b for a, b in zip(astuple(self), astuple(other), strict=True)))


@dataclass(frozen=True)
class HarnessPlan:
    image: str
    script: str
    writeback: tuple[str, ...] = ()
    # what the run is recorded under (see Attempt.model and Attempt.billing): the model after the defaults were filled
    # in, and how the harness is paid for
    model: str = ""
    billing: Literal["subscription", "api"] = "subscription"


def plan_for(
    harness: str, cfg: AppSettings, *, model: str = "", effort: str = "", key_envs: Sequence[str] = ()
) -> HarnessPlan | None:
    """None means the placeholder program, which needs nothing special. An agent may choose its own model and
    reasoning effort (empty means the ones in Settings) and be given keys, available as these variables."""
    if harness == "codex":
        image, default_model, default_effort = defaults_for(harness, cfg)
        model = model or default_model
        return HarnessPlan(
            image=image,
            script=codex_script(model, effort_for(model, effort or default_effort), key_envs),
            writeback=(CODEX_AUTH,),
            model=model,
            billing="subscription",  # Codex runs on the user's ChatGPT login, never on an API key
        )
    if harness == "claude":
        image, default_model, default_effort = defaults_for(harness, cfg)
        model = model or default_model
        return HarnessPlan(
            image=image,
            script=claude_script(model, effort_for(model, effort or default_effort), key_envs),
            model=model,
            # a subscription token bills the plan; an API key bills per token. The login says which (see the scheduler)
            billing="subscription",
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


@dataclass(frozen=True)
class EarlierStep:
    """One run that already worked in the working folder this run continues in."""

    title: str
    status: str
    changes: dict | None  # see Attempt.changes; None for runs from before changes were kept
    result: str


_NOTE_STEPS = 8  # the most recent steps are told, older ones would only be noise
_NOTE_FILES = 15  # files named per kind and step
_NOTE_RESULT = 300  # characters of each step's own summary


def workdir_note(steps: Sequence[EarlierStep], top_level: Sequence[str]) -> str:
    """Tells an agent that its /workspace is the folder of earlier steps, and what they did in it, so it builds on that
    instead of starting over. This is the answer to "which files belong to this job": Themis keeps the record."""
    intro = (
        "This working folder is continued from earlier steps of the same job. /workspace already holds their work: "
        "build on it, and do not delete or redo what you did not make. What they did, oldest first:"
    )
    lines = [intro]
    for step in steps[-_NOTE_STEPS:]:
        parts = []
        for verb in ("added", "changed", "removed"):
            files = (step.changes or {}).get(verb) or []
            if files:
                shown = ", ".join(files[:_NOTE_FILES]) + (" and more" if len(files) > _NOTE_FILES else "")
                parts.append(f"{verb} {shown}")
        did = "; ".join(parts) or (
            "no file changes" if step.changes is not None else "no record of its changes"
        )
        line = f'- "{step.title}" ({step.status}): {did}'
        if step.result.strip():
            summary = " ".join(step.result.split())
            line += f'. It reported: "{summary[:_NOTE_RESULT]}{"..." if len(summary) > _NOTE_RESULT else ""}"'
        lines.append(line)
    if top_level:
        lines.append("The top level of the folder now holds: " + ", ".join(top_level))
    return "\n".join(lines)


# A run that is started again after a provider error finds the work of the one before it in /workspace
RETRY_NOTE = (
    "An earlier run of this job stopped early because the model provider had a problem, not because of anything you "
    "did. /workspace holds what it already did: continue from there instead of starting over."
)

_BLOCKED_FIELD_CHARS = 400  # a reason is a sentence or two; the log has the rest


def parse_blocked(text: str) -> tuple[str, str]:
    """(reason, fix) from what an agent wrote to /cell/blocked.md. Lines other than `Reason:` and `Fix:` count as the
    reason, so an agent that wrote free text is still understood."""
    reason: list[str] = []
    fix: list[str] = []
    into = reason
    for line in text.strip().splitlines():
        head, _, rest = line.partition(":")
        key = head.strip().lower().lstrip("*-# ").rstrip("*")
        if key in ("reason", "fix"):
            into, line = (reason if key == "reason" else fix), rest.lstrip("*")  # "**Reason:** ..."
        into.append(line.strip())

    def clean(lines: list[str]) -> str:
        return " ".join(" ".join(lines).split())[:_BLOCKED_FIELD_CHARS]

    return clean(reason), clean(fix)


_TAIL_LINES = 80  # what the ticket shows of the end of the log of a failure
_TAIL_LINE_CHARS = 300


def log_tail(log: str) -> str:
    """The last lines of a log, each shortened: what a person looks at first when something failed."""
    lines = log.rstrip().split("\n")[-_TAIL_LINES:]
    return "\n".join(
        line if len(line) <= _TAIL_LINE_CHARS else f"{line[:_TAIL_LINE_CHARS]} [...]" for line in lines
    )


def build_prompt(
    title: str,
    description: str,
    properties: dict,
    *,
    preamble: str = "",
    folders: Sequence[tuple[str, bool]] = (),
    notes: Sequence[str] = (),
    continuing: bool = False,
    rules: str = "",
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
    parts.extend(notes)  # what the agent's connections give it (app/connections.py)
    scope = (
        "is the working folder of this job, continued from earlier steps (see above)"
        if continuing
        else "is private to this run"
    )
    parts.append(
        f"You are running unattended inside a throwaway container. Your working directory /workspace {scope}. Do the "
        "task, then finish with a short summary of what you did and what you produced. Never read or print anything "
        "under /run/themis-secrets: it holds credentials, and everything you print is stored in the log."
    )
    if rules.strip():  # the Themis package's rules (app/cell_package.py), switched off or edited in Settings
        parts.append(rules.strip())
    return "\n\n".join(parts) + "\n"


_NOISE = {"Reading additional input from stdin..."}  # printed by codex exec whenever stdin is not a terminal

# What the log keeps of one command's output. The agent saw all of it; the log is for the person watching, and a single
# `cat` of a few documents would otherwise fill the whole log and hide the next ten minutes of what the agent did.
_OUT_HEAD_LINES = 40
_OUT_TAIL_LINES = 12
_OUT_LINE_CHARS = 500  # a minified file is one enormous line


def trim_output(out: str) -> str:
    """The start and the end of a long command output, with a note of how much was left out between them."""
    lines = [
        line
        if len(line) <= _OUT_LINE_CHARS
        else f"{line[:_OUT_LINE_CHARS]} [... {len(line) - _OUT_LINE_CHARS:,} more characters]"
        for line in out.split("\n")
    ]
    if len(lines) <= _OUT_HEAD_LINES + _OUT_TAIL_LINES:
        return "\n".join(lines)
    hidden = lines[_OUT_HEAD_LINES:-_OUT_TAIL_LINES]
    note = f"[... {len(hidden):,} more lines not shown in this log: the agent saw all of the output ...]"
    return "\n".join([*lines[:_OUT_HEAD_LINES], note, *lines[-_OUT_TAIL_LINES:]])


# Codex errors that mean the provider could not serve the run right now, so the same run may well work in a minute.
# Matched on the message Codex prints. Not a usage or plan limit ("try again at ..." can be days away) and not a
# rejected login or model name: those need a person.
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


# What Codex says when its copy of the login is one whose refresh token another run already used up (or that was
# revoked). Which of the two it is only the stored login can tell: see Scheduler._execute.
_CODEX_LOGIN_REJECTED = (
    "refresh token was already used",
    "refresh token has already been used",
    "refresh_token_reused",
    "log out and sign in again",
)


class HarnessRenderer:
    """Turns a harness's JSON event stream into a readable log, line by line. What the events look like is the
    subclass's business (`_line`); what a run reports afterwards (usage, the error that ended it, whether that error
    is worth a retry or means the login was refused) is the same for every harness, because the scheduler only
    reads these."""

    name = ""  # how the harness is called in messages ("Codex")
    transient_markers: tuple[
        str, ...
    ] = ()  # messages that mean the provider could not serve the run right now
    login_markers: tuple[str, ...] = ()  # messages that mean the harness's login was refused

    def __init__(self) -> None:
        self._buf = ""
        self._emitted = False
        # What the run spent, once the harness has reported it (None until then: a run that crashed or was cancelled
        # before finishing its turn reports nothing). A later report replaces an earlier one: harnesses report the
        # total so far, not a step.
        self.usage: TokenUsage | None = None
        self.error = ""  # the message of the last error event: why the run ended, when it did not end well

    @property
    def transient_error(self) -> str:
        """The error that ended this run when it is one worth starting the run again for, else ''."""
        lowered = self.error.lower()
        return self.error if any(marker in lowered for marker in self.transient_markers) else ""

    @property
    def login_rejected(self) -> bool:
        """The run ended because the harness's login was refused: nothing the agent did, and not worth a plain retry."""
        lowered = self.error.lower()
        return any(marker in lowered for marker in self.login_markers)

    def feed(self, text: str) -> str:
        self._buf += text
        *lines, self._buf = self._buf.split("\n")
        return "".join(self._line(line) for line in lines)

    def flush(self) -> str:
        rest, self._buf = self._buf, ""
        return self._line(rest) if rest else ""

    def _line(self, line: str) -> str:
        raise NotImplementedError


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


# What Claude Code says when the provider could not serve the run right now (an overloaded API is the usual one)
_CLAUDE_TRANSIENT = (
    "overloaded",
    "api error: 5",
    "internal server error",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "temporarily unavailable",
    "request timed out",
    "econnreset",
    "socket hang up",
)
# ... and when the login it was given is not accepted
_CLAUDE_LOGIN_REJECTED = (
    "failed to authenticate",  # what the CLI prints for a rejected token (seen against the real CLI: HTTP 401)
    "api error: 401",
    "invalid api key",
    "please run /login",
    "oauth token has expired",
    "invalid bearer token",
    "invalid authentication credentials",
    "authentication_error",
)


class ClaudeRenderer(HarnessRenderer):
    """Turns `claude -p --output-format stream-json` events into the same kind of log Codex runs have: what the agent
    said and thought, each command or tool call, what it printed, and a closing line with the tokens spent."""

    name = "Claude Code"
    transient_markers = _CLAUDE_TRANSIENT
    login_markers = _CLAUDE_LOGIN_REJECTED

    def _line(self, line: str) -> str:
        line = line.rstrip("\r")
        if not line.strip():
            return ""
        try:
            event = json.loads(line)
        except ValueError:
            return line + "\n"  # a warning or anything else that is not an event
        if not isinstance(event, dict):
            return line + "\n"
        text = self._event(event)
        # blocks (what the agent said, thought, ran, and the summary) are set apart by a blank line
        starts_block = bool(text) and text.startswith(("$ ", "[tool] ", "[thinking]", "[claude] done"))
        starts_block = starts_block or self._says(event)
        if text and starts_block and self._emitted:
            text = "\n" + text
        self._emitted = self._emitted or bool(text)
        return text

    @staticmethod
    def _blocks(event: dict) -> list[dict]:
        content = (event.get("message") or {}).get("content")
        return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []

    def _says(self, event: dict) -> bool:
        return event.get("type") == "assistant" and any(b.get("type") == "text" for b in self._blocks(event))

    def _event(self, e: dict) -> str:
        kind = e.get("type", "")
        if kind == "system":
            if e.get("subtype") == "init":
                return f"[claude] session {e.get('session_id', '')}, model {e.get('model', '')}\n"
            if (
                e.get("subtype") == "api_retry"
            ):  # the CLI's own retries; without this a long wait looks like a hang
                return (
                    f"[claude] retrying ({e.get('attempt')} of {e.get('max_retries')}): "
                    f"{e.get('error', 'API error')}\n"
                )
            return ""  # hooks and the like: nothing a reader needs
        if kind == "assistant":
            return "".join(self._assistant_block(b) for b in self._blocks(e))
        if kind == "user":
            return "".join(self._tool_result(b) for b in self._blocks(e) if b.get("type") == "tool_result")
        if kind == "result":
            return self._result(e)
        return f"[claude] {kind}\n" if kind else ""

    @staticmethod
    def _assistant_block(block: dict) -> str:
        kind = block.get("type")
        if kind == "text":
            return str(block.get("text", "")).rstrip() + "\n"
        if kind == "thinking":
            text = str(block.get("thinking", "")).strip()
            return f"[thinking] {text}\n" if text else ""
        if kind == "tool_use":
            args = block.get("input") if isinstance(block.get("input"), dict) else {}
            if block.get("name") == "Bash" and args.get("command"):
                return f"$ {args['command']}\n"
            # the one argument that says what the tool works on, else the whole input, kept short
            detail = next(
                (str(args[k]) for k in ("file_path", "path", "pattern", "url", "query") if args.get(k)),
                json.dumps(args, ensure_ascii=False) if args else "",
            )
            return f"[tool] {block.get('name', '')} {trim_output(detail)}".rstrip() + "\n"
        return ""

    @staticmethod
    def _tool_result(block: dict) -> str:
        content = block.get("content")
        if isinstance(content, list):  # a list of {"type": "text", "text": ...} parts
            content = "\n".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        out = trim_output(str(content or "").rstrip())
        tail = "[error]" if block.get("is_error") else ""
        return "".join(f"{s}\n" for s in (out, tail) if s)

    def _result(self, e: dict) -> str:
        u = e.get("usage") or {}
        if isinstance(u, dict) and u:
            cached = int(u.get("cache_read_input_tokens") or 0)
            # Claude reports fresh and cached input apart; TokenUsage counts the cached part inside the input
            fresh = int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
            self.usage = TokenUsage(
                input_tokens=fresh + cached,
                cached_input_tokens=cached,
                output_tokens=int(u.get("output_tokens") or 0),
            )
        if e.get("is_error") or str(e.get("subtype", "")).startswith("error"):
            detail = str(e.get("result") or e.get("subtype") or "")
            self.error = detail
            return f"[claude] error: {detail}\n"
        tokens_in = self.usage.input_tokens if self.usage else 0
        tokens_out = self.usage.output_tokens if self.usage else 0
        return f"[claude] done - {tokens_in} tokens in, {tokens_out} out\n"


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


def renderer_for(harness: str) -> HarnessRenderer | None:
    return {"codex": CodexRenderer, "claude": ClaudeRenderer}.get(harness, lambda: None)()
