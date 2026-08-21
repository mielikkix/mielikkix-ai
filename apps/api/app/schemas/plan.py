from typing import Dict, List, Optional
from pydantic import BaseModel


class PlanLimitsOut(BaseModel):
    max_websites: Optional[int]
    max_conversations_per_month: Optional[int]
    max_document_uploads: Optional[int]
    max_products: Optional[int]
    max_languages: Optional[int]
    conversation_history_days: Optional[int]


class PlanFeaturesOut(BaseModel):
    knowledge_base: bool
    lead_capture: bool
    analytics_tier: str
    email_notifications: bool
    whatsapp_notifications: bool
    instagram_integration: bool
    multi_currency: bool
    custom_branding: bool
    api_access: bool
    api_access_addon_available: bool
    priority_support: bool


class PlanCatalogEntry(BaseModel):
    key: str
    name: str
    price_usd: int
    tagline: str
    limits: PlanLimitsOut
    features: PlanFeaturesOut


class PlanUsageOut(BaseModel):
    websites: int
    conversations_this_month: int
    documents: int
    products: int


class PlanStatusOut(BaseModel):
    plan: str
    plan_name: str
    price_usd: int
    limits: PlanLimitsOut
    usage: PlanUsageOut
    features: Dict[str, bool | str]
    api_access_addon: bool
    not_yet_implemented: List[str]


class PlanSelectRequest(BaseModel):
    plan: str


class ApiAccessAddonRequest(BaseModel):
    enabled: bool


class ApiKeyOut(BaseModel):
    api_key: Optional[str]


class NotificationChannelRequest(BaseModel):
    channel: str  # "whatsapp" | "instagram"
    enabled: bool
