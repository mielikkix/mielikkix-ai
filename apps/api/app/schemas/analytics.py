from pydantic import BaseModel
from typing import Dict, List


class TopQuestion(BaseModel):
    question: str
    count: int


class AnalyticsSummary(BaseModel):
    conversation_count: int
    lead_count: int
    message_count: int
    analytics_tier: str  # "basic" | "standard" | "advanced" -- drives what's populated below
    # Empty on the "basic" tier (Free plan) -- populated from "standard" up.
    top_questions: List[TopQuestion]
    # Only populated on the "advanced" tier (Business/Growth).
    intent_breakdown: Dict[str, int]
