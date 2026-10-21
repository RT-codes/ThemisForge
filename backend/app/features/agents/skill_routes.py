from fastapi import APIRouter, status

import app.features.agents.skill_service as operations
from app.api.dependencies import CurrentUser, SessionDep
from app.features.agents.skill_schemas import SkillDetail, SkillIn, SkillOut

router = APIRouter(tags=["skills"])


@router.get("/projects/{project_id}/skills", response_model=list[SkillOut])
async def list_skills(project_id: int, session: SessionDep, user: CurrentUser) -> list[SkillOut]:
    return await operations.list_skills(project_id, session, user)


@router.get("/projects/{project_id}/skills/{name}", response_model=SkillDetail)
async def get_skill(project_id: int, name: str, session: SessionDep, user: CurrentUser) -> SkillDetail:
    return await operations.get_skill(project_id, name, session, user)


@router.put("/projects/{project_id}/skills/{name}", response_model=SkillOut)
async def save_skill(
    project_id: int, name: str, body: SkillIn, session: SessionDep, user: CurrentUser
) -> SkillOut:
    """Creates the skill or replaces its SKILL.md."""

    return await operations.save_skill(project_id, name, body, session, user)


@router.delete("/projects/{project_id}/skills/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(project_id: int, name: str, session: SessionDep, user: CurrentUser) -> None:
    """Removes the skill's folder, and the skill from the agents that had it."""

    return await operations.delete_skill(project_id, name, session, user)
