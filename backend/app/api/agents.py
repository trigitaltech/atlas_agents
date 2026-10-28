from app.api.schemas import AgentResponse
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database.session import get_db
from app.models.entities import Agent, Job
from app.agents.web_scraper.schemas import AgentInput
from app.api.dependencies import require, serialize
from app.core.tool_registry import registry

router = APIRouter(prefix="/api/agents", tags=["Agents"])


def check_tools(body):
    unknown = set(body.configuration.tools) - set(registry)
    if unknown:
        raise HTTPException(422, "Unknown tool selection")


@router.post("", status_code=201, response_model=AgentResponse)
def create(body: AgentInput, db: Session = Depends(get_db)):
    check_tools(body)
    agent = Agent(**body.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return serialize(agent)


@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    return [
        serialize(row)
        for row in db.scalars(
            select(Agent).order_by(Agent.created_at.desc()).limit(200)
        )
    ]


@router.get("/{agent_id}", response_model=AgentResponse)
def get(agent_id: str, db: Session = Depends(get_db)):
    return serialize(require(db, Agent, agent_id))


@router.put("/{agent_id}", response_model=AgentResponse)
def update(agent_id: str, body: AgentInput, db: Session = Depends(get_db)):
    check_tools(body)
    agent = require(db, Agent, agent_id)
    for key, value in body.model_dump().items():
        setattr(agent, key, value)
    db.commit()
    return serialize(agent)


@router.delete("/{agent_id}", status_code=204)
def delete(agent_id: str, db: Session = Depends(get_db)):
    agent = require(db, Agent, agent_id)
    if db.scalar(select(Job.id).where(Job.agent_id == agent_id).limit(1)):
        raise HTTPException(
            409, "Agent has execution history; disable it to retain records"
        )
    db.delete(agent)
    db.commit()
    return Response(status_code=204)
