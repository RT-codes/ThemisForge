import asyncio
import json
import random

from app.execution.cells.contract import CellResult, CellSpec, LogSink
from app.execution.cells.files import prepare_dirs, read_blocked, read_result


class FakeCellManager:
    """Simulates a cell without Docker. A title containing 'fail' makes the cell fail."""

    def __init__(self, duration: float = 0.0) -> None:
        self.duration = duration
        self.specs: list[CellSpec] = []  # every cell started, for tests
        self.writeback: dict[str, str] = {}  # what a cell "prints" on exit, for tests
        self.log_text = ""  # extra output a cell "prints", for tests
        # what a cell "writes" into /workspace, for tests: task title -> {relative path: content}
        self.files: dict[str, dict[str, str]] = {}
        # for tests: how many runs of a task (by title) end in the provider saying it is at capacity before one works,
        # and what a task's agent writes to /cell/blocked.md
        self.capacity_errors: dict[str, int] = {}
        self.blocked: dict[str, str] = {}
        # for tests: the usage a task's runs report, as Codex's turn.completed event does (Claude Code's result event
        # for its runs), task title -> tokens
        self.usage: dict[str, dict[str, int]] = {}
        self._runs: dict[str, int] = {}

    async def run(self, spec: CellSpec, on_log: LogSink) -> CellResult:
        self.specs.append(spec)
        prepare_dirs(spec)
        if self.log_text:
            await on_log(self.log_text)
        await on_log(f"[fake cell] started for task {spec.task_id}: {spec.title}\n")
        await asyncio.sleep(self.duration * (0.5 + random.random()))
        for rel, content in self.files.get(spec.title, {}).items():
            target = spec.workspace_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self._runs[spec.title] = self._runs.get(spec.title, 0) + 1
        # the events a harness prints are its own (Codex's turn.completed and error, Claude Code's result)
        claude = spec.harness == "claude"
        if spec.title in self.usage:
            usage = self.usage[spec.title]
            event = (
                {"type": "result", "is_error": False, "result": "", "usage": usage}
                if claude
                else {
                    "type": "turn.completed",
                    "usage": usage,
                }
            )
            await on_log(json.dumps(event) + "\n")
        if self._runs[spec.title] <= self.capacity_errors.get(spec.title, 0):
            event = (
                {"type": "result", "is_error": True, "result": "API Error: 529 overloaded_error"}
                if claude
                else {
                    "type": "error",
                    "message": "Selected model is at capacity. Please try a different model.",
                }
            )
            await on_log(json.dumps(event) + "\n")
            return CellResult(exit_code=1)
        if "fail" in spec.title.lower():
            await on_log("[fake cell] simulated failure\n")
            return CellResult(exit_code=1)
        if spec.title in self.blocked:
            (spec.cell_dir / "blocked.md").write_text(
                self.blocked[spec.title], encoding="utf-8", newline="\n"
            )
        (spec.cell_dir / "result.md").write_text(
            f"Task {spec.task_id} ({spec.title}) finished.\n", encoding="utf-8", newline="\n"
        )
        await on_log("[fake cell] finished\n")
        wb = {p: c for p, c in self.writeback.items() if p in spec.writeback}
        return CellResult(exit_code=0, result=read_result(spec), blocked=read_blocked(spec), writeback=wb)

    async def kill(self, spec: CellSpec) -> None:
        return None

    async def cleanup_orphans(self, docker_host: str) -> int:
        return 0
