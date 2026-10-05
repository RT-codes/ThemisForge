import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.config import settings
from app.db import Base, make_engine

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    url = context.config.get_main_option("sqlalchemy.url") or settings.database_url
    engine = make_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


asyncio.run(_run_async())
