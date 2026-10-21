from app.execution.cells.contract import CellResult
from app.execution.harnesses.prompts import parse_blocked
from app.execution.harnesses.rendering import HarnessRenderer
from app.features.tools.keys import Redactor
from app.persistence.models import (
    AttemptStatus,
)

_EXIT_UNKNOWN = "The program in the cell stopped with exit code {code} and did not say why."


def _themis_failure(reason: str, action: str = "") -> dict:
    return {"source": "themis", "reason": reason, "action": action}


def _run_failure(renderer: HarnessRenderer | None, exit_code: int, retries: int) -> dict:
    """Why a run that ended with a failing exit code failed, from what the harness's own output said."""
    error = renderer.error if renderer is not None else ""
    if renderer is None or not error:
        return _themis_failure(_EXIT_UNKNOWN.format(code=exit_code))
    if renderer.login_rejected:
        return _themis_failure(
            f"{renderer.name} refused the saved login ({error})",
            f"Connect {renderer.name} again in Settings. Until then runs that use {renderer.name} will fail the same way.",
        )
    if renderer.transient_error:
        return _themis_failure(
            f"The model provider could not serve this run ({error})"
            + (f", also after {retries} more {'try' if retries == 1 else 'tries'}." if retries else "."),
            "Try again later, or choose another model for the agent (its Model field, or the harness's defaults in Settings).",
        )
    return _themis_failure(f"The agent stopped with an error: {error}")


def _judge(
    res: CellResult, renderer: HarnessRenderer | None, retries: int, redact: Redactor
) -> tuple[AttemptStatus, dict | None]:
    """How a run that finished ended, and why when it failed. An agent that stopped and said why (see parse_blocked)
    decides the outcome by what it wrote, whatever the exit code of the program was."""
    if res.blocked.strip():
        reason, fix = parse_blocked(redact(res.blocked))
        return AttemptStatus.FAILED, {
            "source": "agent",
            "reason": reason or "The agent stopped without saying why.",
            "action": fix,
        }
    if res.exit_code == 0:
        return AttemptStatus.SUCCEEDED, None
    return AttemptStatus.FAILED, _run_failure(renderer, res.exit_code, retries)
