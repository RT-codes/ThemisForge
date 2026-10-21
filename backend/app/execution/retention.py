import asyncio
import logging
import shutil
from datetime import timedelta

from sqlalchemy import or_, select

from app.config import settings
from app.features.system.settings import load_settings
from app.persistence.models import (
    Attempt,
    AttemptStatus,
    utcnow,
)

log = logging.getLogger("themis.scheduler")


async def prune_workspaces(maker) -> int:
    """Remove the working folders that nothing has used for the retention period, and those that no attempt
    refers to any more. A folder that later steps continued in lives as long as the last of them. Returns how many
    folders were removed."""
    folders = [d for d in (settings.data_dir / "projects").glob("*/workspaces/*") if d.name.isdigit()]
    if not folders:
        return 0
    ids = [int(d.name) for d in folders]
    async with maker() as s:
        cfg = await load_settings(s)
        # a folder is named by the attempt that made it; attempts that continued in it say so in workdir_id
        users = (
            await s.execute(
                select(Attempt.id, Attempt.workdir_id, Attempt.status, Attempt.finished_at).where(
                    or_(Attempt.id.in_(ids), Attempt.workdir_id.in_(ids))
                )
            )
        ).all()
    cutoff = utcnow() - timedelta(days=cfg.keep_workspaces_days)
    busy: set[int] = set()  # in use, or used recently enough; a folder no attempt names is not in here at all
    for attempt_id, workdir_id, status, finished_at in users:
        folder = workdir_id or attempt_id
        if status == AttemptStatus.RUNNING or finished_at is None or finished_at > cutoff:
            busy.add(folder)
    stale = [d for d in folders if int(d.name) not in busy]
    for d in stale:
        await asyncio.to_thread(shutil.rmtree, d, True)
    if stale:
        log.info("removed %d old working folder(s)", len(stale))
    return len(stale)
