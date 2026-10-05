from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..app_settings import AppSettings, load_settings, save_settings
from ..config import DEFAULT_SECRET_KEY
from ..config import settings as boot_settings
from ..crypto import encrypt, hint_for
from ..deps import AdminUser, CurrentUser, SessionDep
from ..docker_check import check_docker
from ..models import AccessRequest, Secret
from ..schemas import SecretIn, SecretOut

router = APIRouter(tags=["system"])


class SchedulerStatus(BaseModel):
    running: bool
    active_cells: int
    max_cells: int


class SystemStatus(BaseModel):
    scheduler: SchedulerStatus
    timezone: str
    pending_access_requests: int  # only filled in for administrators
    insecure_secret_key: bool
    cell_backend: str


@router.get("/system/status", response_model=SystemStatus)
async def system_status(request: Request, session: SessionDep, user: CurrentUser) -> SystemStatus:
    scheduler = request.app.state.scheduler
    cfg = await load_settings(session)
    pending = 0
    if user.is_admin:
        pending = await session.scalar(
            select(func.count()).select_from(AccessRequest).where(AccessRequest.status == "pending")
        )
    return SystemStatus(
        scheduler=SchedulerStatus(
            running=scheduler.running, active_cells=scheduler.active_cells, max_cells=cfg.max_concurrent_cells
        ),
        timezone=cfg.timezone,
        pending_access_requests=pending or 0,
        insecure_secret_key=boot_settings.secret_key == DEFAULT_SECRET_KEY,
        cell_backend=boot_settings.cell_backend,
    )


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


@router.get("/settings", response_model=AppSettings)
async def get_settings(session: SessionDep, _: AdminUser) -> AppSettings:
    return await load_settings(session)


@router.put("/settings", response_model=AppSettings)
async def put_settings(body: AppSettings, request: Request, session: SessionDep, _: AdminUser) -> AppSettings:
    saved = await save_settings(session, body)
    request.app.state.scheduler.wake()  # e.g. a raised concurrency limit applies immediately
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
    await session.delete(secret)
    await session.commit()
