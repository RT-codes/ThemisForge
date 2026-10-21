from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crypto import decrypt
from app.execution.active_runs import ActiveRuns
from app.execution.cells.contract import CellError, CellManager, CellResult, CellSpec, CellTimeout
from app.execution.cells.files import changes_between, snapshot_workdir
from app.execution.failures import _EXIT_UNKNOWN, _judge, _themis_failure
from app.execution.harnesses.catalog import AGENT_HARNESSES
from app.execution.harnesses.codex import CODEX_AUTH
from app.execution.harnesses.prompts import RETRY_NOTE, log_tail
from app.execution.harnesses.rendering import HarnessRenderer
from app.execution.harnesses.service import renderer_for
from app.execution.harnesses.types import TokenUsage
from app.execution.logs import _LogBuffer
from app.features.connections.codex import CodexError, CodexLease, lease_codex, lease_is_busy
from app.features.connections.service import ConnectionProblem, secret_values
from app.features.notifications.delivery import notify
from app.features.system.settings import load_settings
from app.features.tasks.scheduling import finish_task
from app.features.tools.keys import Redactor, key_path
from app.features.tools.mcp import config_file
from app.persistence.models import (
    Attempt,
    AttemptStatus,
    Secret,
    Task,
    TaskStatus,
    utcnow,
)

if TYPE_CHECKING:
    from app.features.tools.auth import McpLogins
    from app.features.workflows.runner import WorkflowRunner


log = logging.getLogger("themis.scheduler")


class AttemptExecutor:
    """Run attempts; retain credential leases, retries and finalization in order."""

    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        cells: CellManager,
        runs: ActiveRuns,
        mcp_logins: Callable[[], McpLogins | None],
        workflows: Callable[[], WorkflowRunner | None],
    ) -> None:
        self.maker, self.cells, self.runs = maker, cells, runs
        self._mcp_logins, self._workflows = mcp_logins, workflows

    @property
    def mcp_logins(self) -> McpLogins | None:
        return self._mcp_logins()

    @property
    def workflows(self) -> WorkflowRunner | None:
        return self._workflows()

    async def execute(
        self, attempt_id: int, spec: CellSpec, tz: str, retry_waits: tuple[int, ...] = ()
    ) -> None:
        """Run the cell and record how it ended. When the model provider could not serve a run for a moment (the
        harness says so, see HarnessRenderer.transient_error) the run starts again in the same attempt after each of
        `retry_waits`: whether an error is such a moment is the harness's call, how patient to be is the setting."""
        buf = _LogBuffer(self.maker, attempt_id)
        outcome, exit_code, result = AttemptStatus.FAILED, None, ""
        failure: dict | None = None  # why it failed, once it has (see Attempt.failure)
        before: dict[str, tuple[int, int]] | None = None  # the working folder as the cell found it
        renderers: list[
            HarnessRenderer
        ] = []  # one per run of this attempt: each remembers what its run spent
        try:
            async with AsyncExitStack() as stack:
                lease, redact = await self._harness_login(stack, spec, buf)
                if spec.harness != "workflow":
                    before = await asyncio.to_thread(snapshot_workdir, spec)
                res, renderer, retries = await self._run_cell(
                    attempt_id, spec, buf, redact, lease, retry_waits, renderers
                )
            exit_code, result = res.exit_code, redact(res.result)
            outcome, failure = _judge(res, renderer, retries, redact)
        # no error escapes: each one ends the attempt with a recorded reason (_explain logs the unexpected ones)
        except (Exception, asyncio.CancelledError) as e:  # noqa: BLE001
            outcome, failure = await self._explain(e, attempt_id, buf)
        # every run counts, also the ones that were started again: the provider billed them all. A run that was
        # cancelled or timed out mid-turn has reported nothing, so what it spent is not in here.
        reported = [r.usage for r in renderers if r.usage is not None]
        usage = sum(reported, TokenUsage()) if reported else None
        changes = None
        if before is not None:  # a failed or cancelled run may have left files too: the next step should know
            changes = changes_between(before, await asyncio.to_thread(snapshot_workdir, spec))
        if outcome == AttemptStatus.FAILED and spec.harness == "workflow" and self.workflows is not None:
            # a task that plays workflows failed because of a step: that step's reason is the one to show
            failure = await self.workflows.failure_for_attempt(attempt_id) or failure
        await self._finish(
            attempt_id, spec.task_id, buf, outcome, exit_code, result, tz, changes, failure, usage
        )

    async def _harness_login(
        self, stack: AsyncExitStack, spec: CellSpec, buf: _LogBuffer
    ) -> tuple[CodexLease | None, Redactor]:
        """Put everything an agent run needs in the cell's secret files (keys, tool sign ins, connections, the
        harness's own login) and return a Redactor that hides those values in everything that is stored. Codex's login
        rotates, so a Codex run also waits for a turn on the user's login and holds it for the run (`stack` lets it
        go); that lease is returned. Other harnesses have a login that does not rotate: it is only a secret file."""
        redact = Redactor([])
        if spec.harness not in AGENT_HARNESSES:
            return None, redact
        lease = None
        if spec.harness == "codex":
            async with self.maker() as session:
                parallel = (await load_settings(session)).codex_max_parallel
            if lease_is_busy(spec.owner_id, parallel):
                await buf.write(
                    "[Waiting for the user's other Codex runs: they share one login, "
                    f"at most {parallel} at a time]\n"
                )
            lease = await stack.enter_async_context(
                lease_codex(
                    self.maker, spec.owner_id, max_parallel=parallel, run_seconds=spec.timeout_seconds
                )
            )
            spec.secret_files[CODEX_AUTH] = lease.auth_json
        if spec.keys or spec.mcp or spec.connections:
            values = await self._key_values(spec)
            for key_id, env in spec.keys.items():
                spec.secret_files[key_path(env)] = values[key_id]
            if spec.mcp:
                path, text = config_file(spec.harness, spec.mcp, values, spec.keys)
                spec.secret_files[path] = text
            # connections hand over their secrets the same way a key does: a file, exported as a variable
            from_connections = await secret_values(self.maker, spec.connections)
            for env, value in from_connections.items():
                spec.secret_files[key_path(env)] = value
            # a tool that signs in gets a token that lasts the whole run, renewed first when it would not
            tokens = await self._login_tokens(spec)
            for env, value in tokens.items():
                spec.secret_files[key_path(env)] = value
            redact = Redactor([*values.values(), *from_connections.values(), *tokens.values()])
        return lease, redact

    async def _run_cell(
        self,
        attempt_id: int,
        spec: CellSpec,
        buf: _LogBuffer,
        redact: Redactor,
        lease: CodexLease | None,
        retry_waits: tuple[int, ...],
        renderers: list[HarnessRenderer],
    ) -> tuple[CellResult, HarnessRenderer | None, int]:
        """Run the cell (or play the workflow) and, when that is the right call, run it again in the same attempt:
        once with a newer login when another run refreshed it first, and after each of `retry_waits` when the provider
        could not serve it. Every run's renderer is added to `renderers` as it starts, so what each spent is counted
        even if a later run is cut short. Returns the last run's result and renderer, and how many provider retries
        it took."""
        retries = 0  # how many times the provider's trouble made this attempt start its run again
        login_retried = (
            False  # whether a rejected login was already swapped for a newer one (once per attempt)
        )
        while True:
            # one renderer per run: it remembers the error that ended it
            renderer = renderer_for(spec.harness)
            if renderer is not None:
                renderers.append(renderer)

            async def sink(chunk: str, renderer=renderer) -> None:
                if renderer is None:
                    await buf.write(redact(chunk))
                elif text := renderer.feed(chunk):
                    await buf.write(redact(text))

            sent = spec.secret_files.get(CODEX_AUTH)  # the login this run started with
            res = await self._play_or_run(spec, attempt_id, sink)
            if renderer is not None and (tail := renderer.flush()):
                await buf.write(redact(tail))
            if lease is not None and (fresh := res.writeback.get(CODEX_AUTH)) and fresh != lease.auth_json:
                try:
                    await lease.save_back(fresh)
                except CodexError as e:
                    await buf.write(f"\n[The refreshed Codex login was not stored: {e}]\n")
            rejected = res.exit_code != 0 and renderer is not None and renderer.login_rejected
            if lease is not None and rejected:
                await lease.adopt_newer()  # a cell that wrote nothing back left the lease as it was
            if lease is not None and rejected and not login_retried and lease.auth_json != sent:
                # another run refreshed the login while this one held the old copy: the stored one is the
                # one that works, so start again with it (once; a login that still fails is dead)
                login_retried = True
                await buf.write(
                    "\n[Themis] Another run refreshed the Codex login first. Starting this one "
                    "again with the new login.\n"
                )
                spec.secret_files[CODEX_AUTH] = lease.auth_json
                continue
            trouble = renderer.transient_error if renderer is not None and res.exit_code != 0 else ""
            if not trouble or retries >= len(retry_waits):
                return res, renderer, retries
            wait = retry_waits[retries]
            retries += 1
            await buf.write(
                f"\n[Themis] The provider could not serve this run: {redact(trouble)}\n"
                f"[Themis] Starting it again in {wait} s (retry {retries} of {len(retry_waits)}). "
                "What it already did stays in the working folder.\n"
            )
            await asyncio.sleep(wait)
            # the next run starts from the login the last one refreshed, and is told it is a continuation
            if lease is not None:
                spec.secret_files[CODEX_AUTH] = lease.auth_json
            if RETRY_NOTE not in spec.prompt:
                spec.prompt = f"{spec.prompt.rstrip()}\n\n{RETRY_NOTE}\n"

    async def _explain(
        self, error: BaseException, attempt_id: int, buf: _LogBuffer
    ) -> tuple[AttemptStatus, dict | None]:
        """What an error that cut a run short means for its attempt: how it ended and why, also written to its log.
        A cancel the person asked for is not a failure; Themis shutting down, a timeout, a cell or login problem and a
        bug in Themis each fail it with their own reason."""
        if isinstance(error, asyncio.CancelledError):
            reason = self.runs.live[attempt_id].cancel_reason if attempt_id in self.runs.live else None
            if reason == "shutdown":
                await buf.write("\n[Themis shut down while this attempt was running]\n")
                return AttemptStatus.FAILED, _themis_failure(
                    "Themis shut down while this attempt was running.", "Run it again with Run now."
                )
            await buf.write("\n[Cancelled]\n")
            return AttemptStatus.CANCELLED, None
        if isinstance(error, CellTimeout):
            await buf.write(f"\n[Cell error] {error}\n")
            return AttemptStatus.FAILED, _themis_failure(
                str(error), "Raise the cell time limit in Settings, or give the agent a smaller job."
            )
        if isinstance(error, (CellError, CodexError, ConnectionProblem)):
            await buf.write(f"\n[Cell error] {error}\n")
            return AttemptStatus.FAILED, _themis_failure(str(error))
        log.error("attempt %s crashed", attempt_id, exc_info=error)
        await buf.write(f"\n[Unexpected error] {error}\n")
        return AttemptStatus.FAILED, _themis_failure(
            f"Themis hit an unexpected error: {error}",
            "This is a bug in Themis: the server log has the details.",
        )

    async def _login_tokens(self, spec: CellSpec) -> dict[str, str]:
        """The bearer token of each tool of the run that signs in, by the variable the cell reads it from."""
        wanted = [server for server in spec.mcp if server.login_id is not None]
        if not wanted:
            return {}
        if self.mcp_logins is None:
            raise CellError("Signing in to tools is not set up in this Themis")
        return {
            server.login_env: await self.mcp_logins.bearer(server.login_id, spec.timeout_seconds)
            for server in wanted
        }

    async def _key_values(self, spec: CellSpec) -> dict[int, str]:
        """The readable values of the keys this run uses, by id."""
        need = set(spec.keys) | {i for server in spec.mcp for i in server.key_ids}
        async with self.maker() as s:
            rows = (await s.scalars(select(Secret).where(Secret.id.in_(need)))).all()
        values: dict[int, str] = {}
        for row in rows:
            value = decrypt(row.value_encrypted)
            if value is None:
                raise CellError(
                    "A stored key could not be read. If THEMIS_SECRET_KEY changed, add the keys again."
                )
            values[row.id] = value
        if set(values) != need:
            raise CellError("A key this agent uses was removed before its run started")
        return values

    async def _play_or_run(self, spec: CellSpec, attempt_id: int, sink) -> CellResult:
        """A task that plays a workflow hands it to the workflow engine; everything else runs in a cell."""
        if spec.harness != "workflow":
            return await self.cells.run(spec, sink)
        if self.workflows is None:
            raise CellError("Workflows are not available")
        ok, result = await self.workflows.run_for_task(spec.project_id, spec.task_id, attempt_id, sink)
        return CellResult(exit_code=0 if ok else 1, result=result)

    async def _finish(
        self,
        attempt_id: int,
        task_id: int,
        buf: _LogBuffer,
        outcome: AttemptStatus,
        exit_code: int | None,
        result: str,
        tz: str,
        changes: dict | None = None,
        failure: dict | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        if outcome == AttemptStatus.FAILED:
            # a failure always says something, even when nobody worked out why: the last lines of the log are then the
            # best there is. One that came from a workflow step brings that step's lines.
            failure = {
                "source": "themis",
                "action": "",
                **(failure or {"reason": _EXIT_UNKNOWN.format(code=exit_code)}),
            }
            failure.setdefault("tail", log_tail(buf.text))
        else:
            failure = None
        async with self.maker() as s:
            attempt = await s.get(Attempt, attempt_id)
            task = await s.get(Task, task_id)
            now = utcnow()
            if attempt is not None:
                attempt.status = outcome
                attempt.finished_at = now
                attempt.exit_code = exit_code
                attempt.log = buf.text
                attempt.result = result
                attempt.changes = changes
                attempt.failure = failure
                if usage is not None:
                    attempt.input_tokens = usage.input_tokens
                    attempt.cached_input_tokens = usage.cached_input_tokens
                    attempt.output_tokens = usage.output_tokens
                    attempt.reasoning_output_tokens = usage.reasoning_output_tokens
            told = None
            if task is not None and task.status == TaskStatus.RUNNING:
                finish_task(task, outcome, tz, now)
                # The steps of a workflow are internal tasks: the task that plays the workflow speaks for them. A
                # cancelled attempt was the person's own doing, so it says nothing.
                if not task.internal and outcome == AttemptStatus.FAILED:
                    told = (task.project_id, "failed", task.title, (failure or {}).get("reason", ""))
                elif not task.internal and outcome == AttemptStatus.SUCCEEDED:
                    event = "attention" if task.status == TaskStatus.REVIEW else "done"
                    told = (task.project_id, event, task.title, "")
            await s.commit()
        if told is not None:
            notify(self.maker, *told)
