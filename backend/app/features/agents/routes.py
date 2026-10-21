from fastapi import APIRouter, status

import app.features.agents.service as operations
from app.api.dependencies import CurrentUser, SessionDep
from app.features.agents.schemas import AgentIn, AgentOut, AgentPatch, CheckIn, CheckOut, HarnessOut
from app.persistence.models import Agent

router = APIRouter(tags=["agents"])


@router.post("/projects/{project_id}/agents/check", response_model=CheckOut)
async def check_agent_tools(
    project_id: int, body: CheckIn, session: SessionDep, user: CurrentUser
) -> CheckOut:
    """Before saving: would the agent's tool servers start in the image it will run in?"""

    return await operations.check_agent_tools(project_id, body, session, user)


@router.get("/harnesses", response_model=list[HarnessOut])
async def list_harnesses(session: SessionDep, _: CurrentUser) -> list[HarnessOut]:
    return await operations.list_harnesses(session, _)


@router.get("/projects/{project_id}/agents", response_model=list[AgentOut])
async def list_agents(project_id: int, session: SessionDep, user: CurrentUser) -> list[Agent]:
    return await operations.list_agents(project_id, session, user)


@router.post("/projects/{project_id}/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(project_id: int, body: AgentIn, session: SessionDep, user: CurrentUser) -> Agent:
    return await operations.create_agent(project_id, body, session, user)


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: int, session: SessionDep, user: CurrentUser) -> Agent:
    return await operations.get_agent(agent_id, session, user)


@router.patch("/agents/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: int, body: AgentPatch, session: SessionDep, user: CurrentUser) -> Agent:
    return await operations.update_agent(agent_id, body, session, user)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: int, session: SessionDep, user: CurrentUser) -> None:
    return await operations.delete_agent(agent_id, session, user)
