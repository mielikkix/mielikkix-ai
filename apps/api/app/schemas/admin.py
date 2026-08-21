from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel

from .plan import PlanLimitsOut


class AdminBusinessStatusUpdate(BaseModel):
    # "trial" is the automatic default for a free-plan business (see
    # businesses.py:choose_plan) -- not something an admin sets by hand, so
    # it's deliberately excluded here.
    status: Literal["active", "suspended"]


class AdminBusinessPlanUpdate(BaseModel):
    # No payment processor exists yet -- this is the only way a business
    # ever ends up on a paid plan today (self-serve is Free-only, see
    # businesses.py:choose_plan). Manual, admin-only, for testing/demos or
    # activating a customer who paid through some other channel.
    plan: Literal["free", "basic", "business", "growth"]


class AdminBusinessListItem(BaseModel):
    id: UUID
    name: str
    slug: str
    industry: str
    plan: str
    plan_name: str
    status: str
    owner_email: Optional[str]
    owner_name: Optional[str]
    created_at: datetime
    websites: int
    conversations_this_month: int
    documents: int
    products: int


class AdminBusinessListOut(BaseModel):
    items: List[AdminBusinessListItem]
    total: int
    page: int
    page_size: int


class AdminOwnerOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AdminLLMUsageSummary(BaseModel):
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AdminBusinessDetailOut(BaseModel):
    id: UUID
    name: str
    slug: str
    industry: str
    logo_url: Optional[str]
    primary_color: str
    plan: str
    plan_name: str
    status: str
    api_access_addon: bool
    created_at: datetime
    updated_at: datetime

    settings: Optional[dict]
    owners: List[AdminOwnerOut]

    plan_limits: PlanLimitsOut
    usage: Dict[str, int]
    features: Dict[str, bool | str]

    faqs: int
    leads: int
    conversations_total: int

    llm_usage_30d: AdminLLMUsageSummary


class AdminSignupDay(BaseModel):
    date: str
    count: int


class AdminOverviewOut(BaseModel):
    total_businesses: int
    businesses_by_plan: Dict[str, int]
    businesses_by_status: Dict[str, int]
    signups_last_30d: List[AdminSignupDay]
    total_conversations: int
    total_leads: int
    total_documents: int


class AdminLLMUsageByDay(BaseModel):
    date: str
    requests: int
    total_tokens: int


class AdminLLMUsageByBusiness(BaseModel):
    business_id: UUID
    business_name: str
    requests: int
    total_tokens: int


class AdminLLMUsageOut(BaseModel):
    totals: AdminLLMUsageSummary
    by_day: List[AdminLLMUsageByDay]
    by_business: List[AdminLLMUsageByBusiness]
