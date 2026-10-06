"""Skills of a project: SKILL.md folders agents can be given. See app/skills.py."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import skills as store
from ..deps import CurrentUser, SessionDep
from ..models import Agent
from .projects import _bad, _project

router = APIRouter(tags=["skills"])


class SkillOut(BaseModel):
    name: str
    description: str
    files: int  # in its folder, SKILL.md included


class SkillDetail(SkillOut):
    content: str


class SkillIn(BaseModel):
    content: str = Field(max_length=400_000)


@router.get("/projects/{project_id}/skills", response_model=list[SkillOut])
async def list_skills(project_id: int, session: SessionDep, user: CurrentUser) -> list[SkillOut]:
    await _project(session, project_id, user)
    return [
        SkillOut(name=s.name, description=s.description, files=s.files) for s in store.list_skills(project_id)
    ]


@router.get("/projects/{project_id}/skills/{name}", response_model=SkillDetail)
async def get_skill(project_id: int, name: str, session: SessionDep, user: CurrentUser) -> SkillDetail:
    await _project(session, project_id, user)
    try:
        content = store.read_skill(project_id, name)
    except store.SkillError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    info = next(s for s in store.list_skills(project_id) if s.name == name)
    return SkillDetail(name=name, description=info.description, files=info.files, content=content)


@router.put("/projects/{project_id}/skills/{name}", response_model=SkillOut)
async def save_skill(
    project_id: int, name: str, body: SkillIn, session: SessionDep, user: CurrentUser
) -> SkillOut:
    """Creates the skill or replaces its SKILL.md."""
    await _project(session, project_id, user)
    try:
        description = store.write_skill(project_id, name, body.content)
    except store.SkillError as e:
        raise _bad(str(e)) from None
    files = next(s.files for s in store.list_skills(project_id) if s.name == name)
    return SkillOut(name=name, description=description, files=files)


@router.delete("/projects/{project_id}/skills/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(project_id: int, name: str, session: SessionDep, user: CurrentUser) -> None:
    """Removes the skill's folder, and the skill from the agents that had it."""
    await _project(session, project_id, user)
    try:
        store.delete_skill(project_id, name)
    except store.SkillError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    for agent in await session.scalars(select(Agent).where(Agent.project_id == project_id)):
        if name in agent.skills:
            agent.skills = [n for n in agent.skills if n != name]
    await session.commit()
