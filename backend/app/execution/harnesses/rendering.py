from app.execution.harnesses.types import TokenUsage

_NOISE = {"Reading additional input from stdin..."}  # printed by codex exec whenever stdin is not a terminal


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
