"""`themis doctor`: check that this machine can run Themis, and show how the last few starts went.

    themis doctor              the checks (see preflight.py), then the last runs from the run trail (see runlog.py)
    themis doctor --report     also write themis-report-<time>.txt, to attach to a bug report

Exit code 1 when something is broken.
"""

import argparse
import asyncio
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from .app_settings import AppSettings, load_settings
from .config import settings
from .preflight import FAIL, OK, WARN, Check, run_checks
from .runlog import Run, read_runs
from .version import build_info

_MARK = {OK: "\033[32m✓\033[0m", WARN: "\033[33m!\033[0m", FAIL: "\033[31m✗\033[0m"}
_PLAIN = {OK: "[ok]", WARN: "[warn]", FAIL: "[FAIL]"}


def _app_settings() -> AppSettings:
    """The Docker host the operator saved in the Settings page, if the database exists."""
    from .db import make_engine

    async def read() -> AppSettings:
        engine = make_engine(settings.database_url)
        try:
            async with async_sessionmaker(engine)() as session:
                return await load_settings(session)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(read())
    except SQLAlchemyError:  # no database yet (or no settings table): defaults apply
        return AppSettings()


def _checks_text(checks: list[Check], marks: dict[str, str]) -> list[str]:
    lines = []
    for c in checks:
        lines.append(f" {marks[c.level]} {c.message}")
        if c.hint:
            lines.append(f"     {c.hint}")
    return lines


def _runs_text(runs: list[Run]) -> list[str]:
    if not runs:
        return ["   No runs recorded yet: the trail starts the next time Themis starts."]
    lines = []
    for run in reversed(runs):  # newest first
        lines.append(f"   {run.started}  v{run.version or '?'}  {run.outcome}")
        if run.failure:
            lines.append(f"       error: {run.failure}")
        lines += [f"       - {p}" for p in run.problems]
    return lines


def _report(checks: list[Check], runs: list[Run]) -> str:
    """Everything a person helping would ask for, without secrets: setting names are listed, their values never."""
    info = build_info()
    out = [
        f"Themis report, {datetime.now(UTC):%Y-%m-%d %H:%M:%S} UTC",
        f"Version: {info.version} ({info.kind}), commit {info.commit or 'unknown'}, built {info.built_at or 'n/a'}",
        f"System: {platform.platform()} {platform.machine()}, Python {platform.python_version()}",
        f"Settings in the environment (names only): {', '.join(sorted(k for k in os.environ if k.startswith('THEMIS_'))) or 'none'}",
        "",
        "Checks:",
        *_checks_text(checks, _PLAIN),
        "",
        "Recent runs:",
        *_runs_text(runs),
        "",
        "Events of those runs:",
    ]
    out += [f"  {e}" for run in runs for e in run.events]
    log = settings.log_dir / "themis.log"
    out += ["", f"End of {log}:"]
    try:
        out += ["  " + line for line in log.read_text(encoding="utf-8", errors="replace").splitlines()[-150:]]
    except OSError:
        out.append("  (no log file yet)")
    return "\n".join(out) + "\n"


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="themis doctor", description="Check that this machine can run Themis."
    )
    parser.add_argument(
        "--report",
        nargs="?",
        const="",
        metavar="FILE",
        help="also write a report file to attach to a bug report",
    )
    args = parser.parse_args(argv)

    info = build_info()
    print(f"Themis {info.version} ({info.kind})\n")
    checks = asyncio.run(run_checks(_app_settings()))
    print("\n".join(_checks_text(checks, _MARK)))
    runs = read_runs(settings.log_dir)
    print("\n Recent runs (newest first):")
    print("\n".join(_runs_text(runs)))

    failed = sum(1 for c in checks if c.level == FAIL)
    print(f"\n{'All good.' if not failed else f'{failed} problem(s) need attention.'}")
    if args.report is not None:
        target = Path(args.report or f"themis-report-{datetime.now(UTC):%Y%m%d-%H%M%S}.txt")
        target.write_text(_report(checks, runs), encoding="utf-8")
        print(f"Report written to {target}. It has no keys or passwords; look it over before you share it.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
