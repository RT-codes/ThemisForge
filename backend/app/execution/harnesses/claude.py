import json
import shlex
from collections.abc import Sequence

from app.execution.cells.contract import SECRETS_DIR
from app.execution.harnesses.rendering import HarnessRenderer, trim_output
from app.execution.harnesses.types import TokenUsage
from app.features.tools.keys import ENV_NAME, key_path

CLAUDE_MCP = f"{SECRETS_DIR}/claude-mcp.json"  # written by the scheduler when the agent has tool servers (app/features/tools/mcp.py)


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
