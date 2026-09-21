from typing import Dict, List, Optional
from pydantic import BaseModel


class AgentTierOut(BaseModel):
    key: str
    name: str
    tagline: str
    price_usd: int
    price_nok: Optional[int]
    features: List[str]


class AgentProductOut(BaseModel):
    key: str
    name: str
    price_usd: int
    multi_tenant: bool
    tiers: Optional[List[AgentTierOut]] = None


class AgentAccessGrantRequest(BaseModel):
    agent_key: str
