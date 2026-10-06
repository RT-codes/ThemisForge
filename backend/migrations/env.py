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
        if engine.dialect.name == "sqlite":
            # SQLite changes a table by recreating it. With foreign keys enforced, dropping the old table would
            # cascade-delete the rows of every table that points at it (attempts, node runs...).
            await connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            await (
                connection.commit()
            )  # end the transaction the pragma started, so the migration runs in its own
        await connection.run_sync(_run)
        if engine.dialect.name == "sqlite":
            broken = (await connection.exec_driver_sql("PRAGMA foreign_key_check")).fetchall()
            if broken:
                raise RuntimeError(f"The migration left rows pointing at nothing: {broken[:5]}")
    await engine.dispose()


asyncio.run(_run_async())
