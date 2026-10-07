import shutil
import sys
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .. import project_config
from ..app_settings import AppSettings, Budget, load_settings, save_settings
from ..budget import Cost, cells_that_fit, recommend_budget
from ..config import DEFAULT_SECRET_KEY
from ..config import settings as boot_settings
from ..crypto import encrypt, hint_for
from ..deps import AdminUser, CurrentUser, SessionDep
from ..docker_check import check_docker
from ..models import AccessRequest, Agent, McpServer, Secret
from ..schemas import SecretIn, SecretOut
from ..version import build_info

router = APIRouter(tags=["system"])


class SchedulerStatus(BaseModel):
    running: bool
    active_cells: int
    max_cells: int


class Resources(BaseModel):
    """What the machine behind the cells has, and a budget that leaves it room to breathe."""

    ok: bool  # False when Docker could not be asked (see error and hint)
    error: str | None = None
    hint: str | None = None
    host_cpus: int | None = None
    host_memory_mb: int | None = None
    disk_total_mb: int  # the drive that holds ThemisForge's data (workspaces, results)
    disk_free_mb: int
    recommended: Budget | None = None


class CellDefaults(BaseModel):
    """The global cell defaults, which anyone who sets up a project's cell needs to see (Settings is admin only)."""

    image: str
    cpus: float
    memory_mb: int
    timeout_seconds: int


class SystemStatus(BaseModel):
    scheduler: SchedulerStatus
    cell_defaults: CellDefaults
    timezone: str
    pending_access_requests: int  # only filled in for administrators
    insecure_secret_key: bool
    cell_backend: str
    version: str
    platform: str  # "windows" | "linux" | "mac": what a folder path looks like here
    cells_ready: bool  # False while Docker cannot run cells: tasks wait instead of failing
    problems: list[
        dict[str, str]
    ]  # what the startup and background checks found; only filled in for administrators
    update: (
        dict | None
    )  # is there a newer release (see app/updates.py); only for administrators, who can act on it


@router.get("/system/status", response_model=SystemStatus)
async def system_status(request: Request, session: SessionDep, user: CurrentUser) -> SystemStatus:
    scheduler = request.app.state.scheduler
    preflight = request.app.state.preflight
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
        update=request.app.state.updates.info(cfg).to_dict() if user.is_admin else None,
    )


@router.post("/system/update-check")
async def check_for_updates(request: Request, session: SessionDep, _: AdminUser) -> dict:
    """Look for a newer release now. Repeated presses within a few seconds reuse the last answer."""
    cfg = await load_settings(session)
    updates = request.app.state.updates
    await updates.check(cfg)
    return updates.info(cfg).to_dict()


@router.get("/system/docker")
async def docker_status(
    session: SessionDep, _: AdminUser, host: Annotated[str | None, Query(max_length=300)] = None
) -> dict:
    """Live Docker check. Pass ?host= to test a value before saving it."""
    if host is None:
        host = (await load_settings(session)).docker_host
    else:
        try:
            host = AppSettings(docker_host=host).docker_host
        except ValidationError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, e.errors()[0]["msg"]) from None
    return (await check_docker(host)).to_dict()


def _disk_usage(path: Path) -> tuple[int, int]:
    """(total, free) in MB of the drive holding `path`, or the nearest folder above it that exists."""
    while not path.exists() and path != path.parent:
        path = path.parent
    usage = shutil.disk_usage(path)
    return usage.total // 1024 // 1024, usage.free // 1024 // 1024


@router.get("/system/resources", response_model=Resources)
async def system_resources(session: SessionDep, _: AdminUser) -> Resources:
    """The machine's CPUs and memory as the Docker daemon sees them (which may be another machine), the disk
    under ThemisForge's data folder, and the budget we would suggest for them."""
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


@router.get("/settings", response_model=AppSettings)
async def get_settings(session: SessionDep, _: AdminUser) -> AppSettings:
    return await load_settings(session)


@router.put("/settings", response_model=AppSettings)
async def put_settings(body: AppSettings, request: Request, session: SessionDep, _: AdminUser) -> AppSettings:
    for root in body.mount_roots:
        if not Path(root.path).is_dir():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{root.path} is not a folder on this machine"
            )
    saved = await save_settings(session, body)
    request.app.state.scheduler.wake()  # e.g. a raised budget applies immediately
    request.app.state.preflight.wake()  # and a new Docker host is checked right away
    request.app.state.updates.wake()  # and a switched on update check, or another channel, looks right away
    return saved


@router.get("/secrets", response_model=list[SecretOut])
async def list_secrets(session: SessionDep, _: AdminUser) -> list[Secret]:
    return list((await session.scalars(select(Secret).order_by(Secret.name))).all())


@router.post("/secrets", response_model=SecretOut, status_code=status.HTTP_201_CREATED)
async def create_secret(body: SecretIn, session: SessionDep, _: AdminUser) -> Secret:
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
        raise HTTPException(status.HTTP_409_CONFLICT, "A secret with this name already exists") from None
    return secret


@router.delete("/secrets/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(secret_id: int, session: SessionDep, _: AdminUser) -> None:
    secret = await session.get(Secret, secret_id)
    if secret is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Secret not found")
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
