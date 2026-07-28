"""Opportunity models."""

from enum import Enum

from pydantic import BaseModel, Field


class OpportunityKind(str, Enum):
    """Types of engagement opportunities."""

    RESEARCH_DIGEST = "research_digest"
    RENEWAL = "renewal"
    CAMPAIGN = "campaign"
    OFFER_PROMOTION = "offer_promotion"
    OFFER_CREATION = "offer_creation"
    PROFILE_OPTIMIZATION = "profile_optimization"
    FESTIVAL_CAMPAIGN = "festival_campaign"
    PATIENT_RECALL = "patient_recall"
    EDUCATION = "education"
    CUSTOMER_FOLLOWUP = "customer_followup"
    REVIEW_RESPONSE = "review_response"
    COMPLIANCE_ALERT = "compliance_alert"
    CURIOUS_ASK = "curious_ask"
    WINBACK = "winback"
    MILESTONE_CELEBRATION = "milestone_celebration"
    ACTIVE_PLANNING = "active_planning"


class Opportunity(BaseModel):
    """Candidate engagement opportunity."""

    kind: OpportunityKind
    merchant_id: str
    customer_id: str | None = None
    trigger_id: str | None = None
    raw_score: float = Field(
        0.0, description="Initial score before business rules"
    )
    adjusted_score: float = Field(
        0.0, description="Score after business rule adjustments"
    )
    weighted_score: float = Field(
        0.0, description="Final weighted score from priority scorer"
    )
    reason: str = Field(..., description="Why this opportunity exists")
    facts: list[str] = Field(default_factory=list, description="Supporting facts")
    suggested_cta: str = "open_ended"
    suppression_key: str | None = None
