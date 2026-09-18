from typing import Dict
from pydantic import BaseModel


class AgentProductOut(BaseModel):
    key: str
    name: str
    price_usd: int
    multi_tenant: bool


class AgentAccessGrantRequest(BaseModel):
    agent_key: str
