"""Feature extraction models."""

from pydantic import BaseModel, Field


class ExtractedFeatures(BaseModel):
    """Structured business features extracted from contexts."""

    merchant_id: str
    category_slug: str
    
    # Performance features
    ctr_delta_vs_peer: float | None = None
    calls_declining: bool = False
    views_declining: bool = False
    performance_spike: bool = False
    
    # Offer features
    active_offer_count: int = 0
    expired_offer_count: int = 0
    has_recent_offer: bool = False
    offer_recency_days: int | None = None
    
    # Subscription features
    subscription_risk: bool = False
    days_until_renewal: int | None = None
    subscription_expired: bool = False
    
    # Engagement features
    days_since_last_vera_contact: int | None = None
    last_engagement_type: str | None = None
    has_stale_posts: bool = False
    stale_posts_days: int | None = None
    
    # Customer features
    lapse_rate: float | None = None
    retention_rate: float | None = None
    high_risk_cohort_count: int = 0
    
    # Review features
    negative_review_themes: list[str] = Field(default_factory=list)
    positive_review_themes: list[str] = Field(default_factory=list)
    
    # Language
    language_preference: str = "english"
    supports_hindi: bool = False
    
    # Signals
    signals: list[str] = Field(default_factory=list)
    
    # Trigger relevance
    trigger_id: str | None = None
    trigger_kind: str | None = None
    trigger_urgency: int | None = None
    trigger_scope: str | None = None
