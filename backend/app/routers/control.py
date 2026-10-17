import json
import re

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import security
from ..crypto import decrypt, encrypt
from ..deps import CurrentUser, SessionDep
from ..models import ControlToken, Project
from ..schemas import ControlConnect, ControlTokenIn, ControlTokenOut

# The tokens an owner hands to outside agents so they can use a project through MCP (see app/control.py)
router = APIRouter(tags=["control"])


async def _project(session: AsyncSession, project_id: int, user: CurrentUser) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


async def _token(session: AsyncSession, token_id: int, user: CurrentUser) -> tuple[ControlToken, Project]:
    token = await session.get(ControlToken, token_id)
    project = await session.get(Project, token.project_id) if token else None
    if token is None or project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    return token, project


@router.get("/projects/{project_id}/control/tokens", response_model=list[ControlTokenOut])
async def list_tokens(project_id: int, session: SessionDep, user: CurrentUser) -> list[ControlToken]:
    await _project(session, project_id, user)
    rows = await session.scalars(
        select(ControlToken).where(ControlToken.project_id == project_id).order_by(ControlToken.id)
    )
    return list(rows)


@router.post(
    "/projects/{project_id}/control/tokens",
    response_model=ControlTokenOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_token(
    project_id: int, body: ControlTokenIn, session: SessionDep, user: CurrentUser
) -> ControlToken:
    await _project(session, project_id, user)
    secret, secret_hash, hint = security.new_secret()
    token = ControlToken(
        project_id=project_id,
        name=body.name,
        scope=body.scope,
        token_hash=secret_hash,
        token_encrypted=encrypt(secret),
        token_hint=hint,
    )
    session.add(token)
    await session.commit()
    return token


@router.get("/control/tokens/{token_id}/connect", response_model=ControlConnect)
async def connect(token_id: int, request: Request, session: SessionDep, user: CurrentUser) -> ControlConnect:
    """The command and config that connect an agent with this token. The secret is in them, so it is only given to the
    project's owner, who can ask again whenever they need it."""
    token, project = await _token(session, token_id, user)
    secret = decrypt(token.token_encrypted)
    if secret is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This token cannot be read any more because THEMIS_SECRET_KEY changed. Delete it and make a new one.",
        )
    url = f"{str(request.base_url).rstrip('/')}/mcp"
    # one name per project, so several projects can be connected to the same agent side by side
    name = "themis-" + (re.sub(r"[^a-z0-9]+", "-", project.name.lower()).strip("-") or str(project.id))
    return ControlConnect(
        url=url,
        token=secret,
        claude_code=f'claude mcp add --transport http {name} {url} --header "Authorization: Bearer {secret}"',
        config_json=json.dumps(
            {
                "mcpServers": {
                    name: {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {secret}"}}
                }
            },
            indent=2,
        ),
    )


@router.delete("/control/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(token_id: int, session: SessionDep, user: CurrentUser) -> None:
    token, _ = await _token(session, token_id, user)
    await session.delete(token)
    await session.commit()
