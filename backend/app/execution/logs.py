import time

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.persistence.models import (
    Attempt,
)

MAX_LOG_CHARS = 200_000

LOG_HEAD_CHARS = 20_000  # kept for good: how the run began (the prompt, the first commands)

LOG_FLUSH_SECONDS = 1.0


class _LogBuffer:
    """Collects cell output and writes it to the attempt row at most once a second."""

    def __init__(self, maker: async_sessionmaker[AsyncSession], attempt_id: int) -> None:
        self.maker, self.attempt_id = maker, attempt_id
        # A run's log is its beginning plus its most recent output, never "the first N characters": a log that stops
        # at a limit is blind for the rest of a long run, which is exactly when someone is watching it.
        self._head = ""
        self._tail = ""
        self._dropped = 0  # characters between the head and the tail that were not kept
        self._changed = False
        self._last_flush = 0.0

    @property
    def text(self) -> str:
        if not self._dropped:
            return self._head + self._tail
        note = f"\n[... {self._dropped:,} characters from the middle of this log were not kept ...]\n"
        return self._head + note + self._tail

    async def write(self, chunk: str) -> None:
        if chunk:
            if not self._tail and len(self._head) < LOG_HEAD_CHARS:
                room = LOG_HEAD_CHARS - len(self._head)
                self._head, chunk = self._head + chunk[:room], chunk[room:]
            self._tail += chunk
            if (over := len(self._tail) - (MAX_LOG_CHARS - LOG_HEAD_CHARS)) > 0:
                self._tail, self._dropped = self._tail[over:], self._dropped + over
            self._changed = True
        if time.monotonic() - self._last_flush >= LOG_FLUSH_SECONDS:
            await self.flush()

    async def flush(self) -> None:
        self._last_flush = time.monotonic()
        if not self._changed:
            return
        self._changed = False
        text = self.text
        async with self.maker() as s:
            attempt = await s.get(Attempt, self.attempt_id)
            if attempt is not None:
                attempt.log = text
                await s.commit()
