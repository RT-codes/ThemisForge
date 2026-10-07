"""The trail of runs: what happened each time Themis started, kept on disk so `themis doctor` can say where it went wrong.

Two files in settings.log_dir:

  runs.jsonl   one JSON line per event ("start", "preflight", "ready", "problem", "startup_failed", "stop"), grouped by a
               run id. Only the last RUN_LIMIT runs are kept. A run with no "stop" ended without a clean shutdown (a crash,
               a kill, a power cut), which is exactly what a person wants to know, so it is told apart from the rest.
  themis.log   the application log, rotated, with the same lines the console shows.

Nothing secret goes in: events carry check results and error messages, never settings values or keys.
"""

import json
import logging
import logging.handlers
import os
import platform
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .version import build_info

RUN_LIMIT = 20
LOG_BYTES = 2_000_000
LOG_FILES = 3


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Trail:
    """Writes the events of the running process. Safe to call from any thread; never raises (a full disk must not stop Themis)."""

    def __init__(self, folder: Path) -> None:
        self.path = folder / "runs.jsonl"
        self.run_id: str | None = None
        self._lock = threading.Lock()

    def begin(self) -> str:
        """Starts a run: forgets the oldest runs beyond the limit, then records how this one started."""
        self.run_id = uuid.uuid4().hex[:8]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._trim()
        except OSError:
            pass
        info = build_info()
        self.event(
            "start",
            version=info.version,
            commit=info.commit,
            pid=os.getpid(),
            python=platform.python_version(),
            system=f"{platform.system()} {platform.release()} {platform.machine()}",
            argv=" ".join(sys.argv[:1]),
        )
        return self.run_id

    def event(self, kind: str, **data: object) -> None:
        line = json.dumps({"run": self.run_id, "t": _now(), "event": kind, **data}, default=str)
        try:
            with self._lock, self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def end(self) -> None:
        self.event("stop")

    def _trim(self) -> None:
        events = _read_events(self.path)
        runs: list[str] = list(dict.fromkeys(e["run"] for e in events if e.get("run")))
        keep = set(runs[-(RUN_LIMIT - 1) :])  # room for the run that is starting
        if len(keep) == len(runs):
            return
        lines = [json.dumps(e) for e in events if e.get("run") in keep]
        self.path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _read_events(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    events = []
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue  # a line cut short by a crash
        if isinstance(event, dict):
            events.append(event)
    return events


@dataclass
class Run:
    id: str
    started: str
    version: str
    events: list[dict] = field(default_factory=list)
    newest: bool = False

    def _last(self, kind: str) -> dict | None:
        return next((e for e in reversed(self.events) if e["event"] == kind), None)

    @property
    def problems(self) -> list[str]:
        """The checks that were not fine at the last look, as messages."""
        last = self._last("preflight")
        return [f"{c['message']}" for c in (last or {}).get("checks", []) if c.get("level") != "ok"]

    @property
    def failure(self) -> str:
        return str((self._last("startup_failed") or {}).get("error", ""))

    @property
    def outcome(self) -> str:
        if self._last("startup_failed"):
            return "failed to start"
        if self._last("stop"):
            return "stopped, with problems" if self.problems else "stopped cleanly"
        if self.newest:
            return "running now, or ended without a clean stop"
        return "ended without a clean stop (a crash, a kill or a power cut)"


def read_runs(folder: Path, last: int = 5) -> list[Run]:
    """The most recent runs, oldest first."""
    runs: dict[str, Run] = {}
    for e in _read_events(folder / "runs.jsonl"):
        rid = e.get("run")
        if not rid:
            continue
        run = runs.setdefault(rid, Run(id=rid, started=e.get("t", ""), version=""))
        if e["event"] == "start":
            run.started, run.version = e.get("t", run.started), e.get("version", "")
        run.events.append(e)
    out = list(runs.values())[-last:]
    if out:
        out[-1].newest = True
    return out


def setup_file_logging(folder: Path) -> None:
    """Adds a rotating log file next to the console output. Called once at startup."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            folder / "themis.log", maxBytes=LOG_BYTES, backupCount=LOG_FILES, encoding="utf-8"
        )
    except OSError:
        return  # the console log still works
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return
    root.addHandler(handler)
    for name in ("app", "themis", "uvicorn.error"):  # ours and the server's; libraries stay at warnings
        logging.getLogger(name).setLevel(logging.INFO)
