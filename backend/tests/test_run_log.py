"""What the log of a run keeps: all the agent says and thinks, a trimmed view of huge command output, and always the
latest output, however long the run goes."""

import json

from app.execution.harnesses.codex import CodexRenderer
from app.execution.harnesses.rendering import trim_output
from app.execution.logs import LOG_HEAD_CHARS, MAX_LOG_CHARS, _LogBuffer


def ev(**kw) -> str:
    return json.dumps(kw) + "\n"


def test_a_short_output_is_kept_whole():
    out = "\n".join(f"line {i}" for i in range(50))
    assert trim_output(out) == out


def test_a_long_output_keeps_its_start_and_end_and_says_what_is_missing():
    out = "\n".join(f"line {i}" for i in range(1000))
    shown = trim_output(out)
    assert shown.startswith("line 0\n") and shown.endswith("line 999")
    assert "line 39\n" in shown and "line 40\n" not in shown  # the first 40 lines
    assert "line 987\n" not in shown and "line 988\n" in shown  # the last 12
    assert "948 more lines not shown" in shown  # 1000 minus the 40 at the start and the 12 at the end
    assert len(shown) < len(out) / 5


def test_one_enormous_line_is_clipped():
    shown = trim_output("x" * 100_000)
    assert len(shown) < 700 and "99,500 more characters" in shown


def test_the_renderer_trims_command_output_but_never_what_the_agent_says():
    r = CodexRenderer()
    huge = "\n".join(f"row {i}" for i in range(5000))
    said = "Here is what I found. " * 500  # long, and all of it matters
    out = r.feed(
        ev(type="item.started", item={"type": "command_execution", "command": "/bin/bash -lc 'cat docs/*'"})
        + ev(type="item.completed", item={"type": "command_execution", "command": "x", "aggregated_output": huge, "exit_code": 0})
        + ev(type="item.completed", item={"type": "reasoning", "text": said})
        + ev(type="item.completed", item={"type": "agent_message", "text": said})
    )  # fmt: skip
    assert "$ cat docs/*" in out and "row 0" in out and "row 4999" in out and "row 2500" not in out
    assert out.count(said.strip()) == 2  # thinking and message, untouched


async def test_a_long_log_keeps_recording_and_keeps_the_latest(maker):
    buf = _LogBuffer(maker, 0)
    chunk = "x" * 50_000
    await buf.write("START of the run\n")
    for i in range(10):  # 500 KB, far over the limit
        await buf.write(f"{chunk}\nblock {i}\n")
    await buf.write("the very latest line\n")
    text = buf.text
    assert text.startswith("START of the run\n")  # the beginning is kept
    assert text.endswith("the very latest line\n")  # and so is the end: it did not stop at the limit
    assert "characters from the middle of this log were not kept" in text
    assert len(text) < MAX_LOG_CHARS + 200
    assert text.index("START") < LOG_HEAD_CHARS


async def test_a_short_log_is_exactly_what_was_written(maker):
    buf = _LogBuffer(maker, 0)
    await buf.write("one\n")
    await buf.write("two\n")
    assert buf.text == "one\ntwo\n"
