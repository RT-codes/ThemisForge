from collections.abc import Sequence
from dataclasses import dataclass


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
    parts.extend(notes)  # what the agent's connections give it (app/features/connections/service.py)
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
    if (
        rules.strip()
    ):  # the Themis package's rules (app/execution/cell_package.py), switched off or edited in Settings
        parts.append(rules.strip())
    return "\n\n".join(parts) + "\n"
