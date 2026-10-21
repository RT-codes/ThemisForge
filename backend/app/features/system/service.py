import shutil
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

import app.features.project_config.store as project_config
from app.config import DEFAULT_SECRET_KEY
from app.config import settings as boot_settings
from app.crypto import encrypt, hint_for
from app.errors import ApplicationError
from app.execution.budget import Cost, cells_that_fit, recommend_budget
from app.execution.cell_package import (
    DEFAULT_RULES,
    DEFAULT_SKILL,
    SKILL_NAME,
    effective_rules,
    effective_skill,
)
from app.features.agents.skills import SkillError, parse_frontmatter
from app.features.system.docker_check import check_docker
from app.features.system.schemas import (
    CellDefaults,
    CellPackageDefaults,
    CellPackageInUse,
    Resources,
    SchedulerStatus,
    SecretIn,
    SystemStatus,
)
from app.features.system.settings import AppSettings, Budget, load_settings, save_settings
from app.features.system.version import build_info
from app.persistence.models import AccessRequest, Agent, McpServer, Secret, User
from app.runtime import Runtime


async def system_status(runtime: Runtime, session: AsyncSession, user: User) -> SystemStatus:
    scheduler = runtime.scheduler
    preflight = runtime.preflight
    cfg = await load_settings(session)
    pending = 0
    if user.is_admin:
        pending = await session.scalar(
            select(func.count()).select_from(AccessRequest).where(AccessRequest.status == "pending")
        )
    return SystemStatus(
        scheduler=SchedulerStatus(
            running=scheduler.running,
            active_cells=scheduler.active_cells,
            max_cells=cells_that_fit(cfg.budget.as_cost(), Cost(cfg.cell_cpus, cfg.cell_memory_mb)),
        ),
        cell_defaults=CellDefaults(
            image=cfg.cell_image,
            cpus=cfg.cell_cpus,
            memory_mb=cfg.cell_memory_mb,
            timeout_seconds=cfg.cell_timeout_seconds,
        ),
        timezone=cfg.timezone,
        pending_access_requests=pending or 0,
        insecure_secret_key=boot_settings.secret_key == DEFAULT_SECRET_KEY,
        cell_backend=boot_settings.cell_backend,
        version=build_info().version,
        platform={"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux"),
        cells_ready=preflight.cells_ready,
        problems=[c.to_dict() for c in preflight.problems] if user.is_admin else [],
        update=runtime.updates.info(cfg).to_dict() if user.is_admin else None,
    )


async def check_for_updates(runtime: Runtime, session: AsyncSession, _: User) -> dict:
    """Look for a newer release now. Repeated presses within a few seconds reuse the last answer."""
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    cfg = await load_settings(session)
    updates = runtime.updates
    await updates.check(cfg)
    return updates.info(cfg).to_dict()


async def docker_status(session: AsyncSession, _: User, host: str | None = None) -> dict:
    """Live Docker check. Pass ?host= to test a value before saving it."""
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    if host is None:
        host = (await load_settings(session)).docker_host
    else:
        try:
            host = AppSettings(docker_host=host).docker_host
        except ValidationError as e:
            raise ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, e.errors()[0]["msg"]) from None
    return (await check_docker(host)).to_dict()


def _disk_usage(path: Path) -> tuple[int, int]:
    """(total, free) in MB of the drive holding `path`, or the nearest folder above it that exists."""
    while not path.exists() and path != path.parent:
        path = path.parent
    usage = shutil.disk_usage(path)
    return usage.total // 1024 // 1024, usage.free // 1024 // 1024


async def system_resources(session: AsyncSession, _: User) -> Resources:
    """The machine's CPUs and memory as the Docker daemon sees them (which may be another machine), the disk
    under ThemisForge's data folder, and the budget we would suggest for them."""
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    docker = await check_docker((await load_settings(session)).docker_host)
    total, free = _disk_usage(boot_settings.data_dir)
    out = Resources(
        ok=docker.ok, error=docker.error, hint=docker.hint, disk_total_mb=total, disk_free_mb=free
    )
    if docker.ok and docker.cpus and docker.memory_mb:
        out.host_cpus, out.host_memory_mb = docker.cpus, docker.memory_mb
        suggestion = recommend_budget(docker.cpus, docker.memory_mb)
        out.recommended = Budget(cpus=suggestion.cpus, memory_mb=suggestion.memory_mb)
    return out


async def get_settings(session: AsyncSession, _: User) -> AppSettings:
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    return await load_settings(session)


async def cell_package_defaults(_: User) -> CellPackageDefaults:
    """The built-in text of the Themis package, shown in Settings next to whatever has been changed."""
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    return CellPackageDefaults(rules=DEFAULT_RULES, skill=DEFAULT_SKILL)


async def cell_package_in_use(session: AsyncSession, _: User) -> CellPackageInUse:
    """Readable by every signed-in user (the text holds no secrets) so an agent's Skills tab can show the package it
    gets; only an administrator can change it, in Settings."""
    package = (await load_settings(session)).cell_package
    skill = effective_skill(package)
    try:
        description = parse_frontmatter(skill).get("description", "") if skill else ""
    except SkillError:
        description = ""
    return CellPackageInUse(
        skill_name=SKILL_NAME,
        skill_enabled=package.skill_enabled,
        skill=skill,
        description=description,
        rules_enabled=package.rules_enabled,
        rules=effective_rules(package),
    )


async def put_settings(body: AppSettings, runtime: Runtime, session: AsyncSession, _: User) -> AppSettings:
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    for root in body.mount_roots:
        if not Path(root.path).is_dir():
            raise ApplicationError(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{root.path} is not a folder on this machine"
            )
    saved = await save_settings(session, body)
    runtime.scheduler.wake()  # e.g. a raised budget applies immediately
    runtime.preflight.wake()  # and a new Docker host is checked right away
    runtime.updates.wake()  # and a switched on update check, or another channel, looks right away
    return saved


async def list_secrets(session: AsyncSession, _: User) -> list[Secret]:
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    return list((await session.scalars(select(Secret).order_by(Secret.name))).all())


async def create_secret(body: SecretIn, session: AsyncSession, _: User) -> Secret:
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    secret = Secret(
        name=body.name.strip(),
        kind=body.kind.strip(),
        value_encrypted=encrypt(body.value),
        hint=hint_for(body.value),
    )
    session.add(secret)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ApplicationError(status.HTTP_409_CONFLICT, "A secret with this name already exists") from None
    return secret


async def delete_secret(secret_id: int, session: AsyncSession, _: User) -> None:
    if not _.is_admin:
        raise ApplicationError(403, "Only an administrator can do this")
    secret = await session.get(Secret, secret_id)
    if secret is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Secret not found")
    # agents and tools that used the key stop referring to it; a run never starts with a key that is gone
    async with project_config.lock:
        agents, servers = [], []
        for agent in await session.scalars(select(Agent)):
            if secret.id in agent.secrets:
                agent.secrets = [i for i in agent.secrets if i != secret.id]
                agents.append(agent)
        for server in await session.scalars(select(McpServer)):
            if secret.id in server.secret_env.values() or server.bearer_secret_id == secret.id:
                server.secret_env = {k: i for k, i in server.secret_env.items() if i != secret.id}
                if server.bearer_secret_id == secret.id:
                    server.bearer_secret_id = None
                servers.append(server)
        await session.delete(secret)
        await session.flush()
        for server in servers:  # their files name keys, so they are written again without this one
            if not server.config_error:
                await project_config.write_mcp(session, server)
        await project_config.rewrite_agents(session, agents)
        await session.commit()
