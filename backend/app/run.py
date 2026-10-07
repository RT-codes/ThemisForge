"""`python -m app.run`: the server, as the installed service starts it (host and port come from the settings)."""

import atexit
import contextlib
import os

import uvicorn

from .config import settings


def _remember_process_id() -> None:
    """Writes the server's process id into the install's home. On Windows the scheduled task that starts the server may
    leave it running when the task is ended, and `themis stop` then stops it by this id."""
    if settings.home is None:
        return
    pid_file = settings.home / "run.pid"
    with contextlib.suppress(OSError):
        pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    atexit.register(lambda: pid_file.unlink(missing_ok=True))


def main() -> None:
    _remember_process_id()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
