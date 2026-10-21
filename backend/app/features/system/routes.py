from typing import Annotated

from fastapi import APIRouter, Query, Request, status

import app.features.system.service as operations
from app.api.dependencies import AdminUser, CurrentUser, SessionDep
from app.features.system.schemas import (
    CellPackageDefaults,
    CellPackageInUse,
    Resources,
    SecretIn,
    SecretOut,
    SystemStatus,
)
from app.features.system.settings import AppSettings
from app.persistence.models import Secret

router = APIRouter(tags=["system"])


@router.get("/system/status", response_model=SystemStatus)
async def system_status(request: Request, session: SessionDep, user: CurrentUser) -> SystemStatus:
    return await operations.system_status(request.app.state, session, user)


@router.post("/system/update-check")
async def check_for_updates(request: Request, session: SessionDep, _: AdminUser) -> dict:
    """Look for a newer release now. Repeated presses within a few seconds reuse the last answer."""

    return await operations.check_for_updates(request.app.state, session, _)


@router.get("/system/docker")
async def docker_status(
    session: SessionDep, _: AdminUser, host: Annotated[str | None, Query(max_length=300)] = None
) -> dict:
    """Live Docker check. Pass ?host= to test a value before saving it."""

    return await operations.docker_status(session, _, host)


@router.get("/system/resources", response_model=Resources)
async def system_resources(session: SessionDep, _: AdminUser) -> Resources:
    """The machine's CPUs and memory as the Docker daemon sees them (which may be another machine), the disk
    under ThemisForge's data folder, and the budget we would suggest for them."""

    return await operations.system_resources(session, _)


@router.get("/settings", response_model=AppSettings)
async def get_settings(session: SessionDep, _: AdminUser) -> AppSettings:
    return await operations.get_settings(session, _)


@router.get("/settings/cell-package", response_model=CellPackageDefaults)
async def cell_package_defaults(_: AdminUser) -> CellPackageDefaults:
    """The built-in text of the Themis package, shown in Settings next to whatever has been changed."""

    return await operations.cell_package_defaults(_)


@router.get("/cell-package", response_model=CellPackageInUse)
async def cell_package_in_use(session: SessionDep, _: CurrentUser) -> CellPackageInUse:
    """Readable by every signed-in user (the text holds no secrets) so an agent's Skills tab can show the package it
    gets; only an administrator can change it, in Settings."""

    return await operations.cell_package_in_use(session, _)


@router.put("/settings", response_model=AppSettings)
async def put_settings(body: AppSettings, request: Request, session: SessionDep, _: AdminUser) -> AppSettings:
    return await operations.put_settings(body, request.app.state, session, _)


@router.get("/secrets", response_model=list[SecretOut])
async def list_secrets(session: SessionDep, _: AdminUser) -> list[Secret]:
    return await operations.list_secrets(session, _)


@router.post("/secrets", response_model=SecretOut, status_code=status.HTTP_201_CREATED)
async def create_secret(body: SecretIn, session: SessionDep, _: AdminUser) -> Secret:
    return await operations.create_secret(body, session, _)


@router.delete("/secrets/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(secret_id: int, session: SessionDep, _: AdminUser) -> None:
    return await operations.delete_secret(secret_id, session, _)
