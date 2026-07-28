"""Context models matching the challenge specification."""

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


# Category Context Models
class VoiceProfile(BaseModel):
    """Voice and tone guidelines for a category."""

    model_config = ConfigDict(populate_by_name=True)

    tone: str = Field(..., description="Tone style (e.g., peer_clinical, warm_retail)")
    vocab_allowed: list[str] = Field(default_factory=list)
    vocab_taboo: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("vocab_taboo", "taboos"),
    )

    @property
    def taboos(self) -> list[str]:
        """Compatibility alias for call sites that use challenge terminology."""
        return self.vocab_taboo


class PeerStats(BaseModel):
    """Peer benchmark statistics."""

    model_config = ConfigDict(populate_by_name=True)

    avg_rating: float
    avg_review_count: int = Field(validation_alias=AliasChoices("avg_review_count", "avg_reviews"))
    avg_ctr: float
    scope: str = Field(..., description="Scope of peer group (e.g., delhi_solo_practices)")


class DigestItem(BaseModel):
    """Research or news digest item."""

    id: str
    kind: str = Field(..., description="research, compliance, trend, etc.")
    title: str
    source: str
    summary: str = ""
    trial_n: int | None = None
    patient_segment: str | None = None


class ContentItem(BaseModel):
    """Patient-facing content item."""

    id: str
    title: str
    channel: str
    body: str


class SeasonalBeat(BaseModel):
    """Seasonal pattern for a category."""

    month_range: str
    note: str


class TrendSignal(BaseModel):
    """Search trend signal."""

    query: str
    delta_yoy: float
    segment_age: str | None = None


class OfferTemplate(BaseModel):
    """Canonical offer template for a category."""

    title: str
    value: str | None = None
    audience: str = "general"


class CategoryContext(BaseModel):
    """Category-level context (slow-changing knowledge)."""

    slug: str
    offer_catalog: list[OfferTemplate] = Field(default_factory=list)
    voice: VoiceProfile
    peer_stats: PeerStats
    digest: list[DigestItem] = Field(default_factory=list)
    patient_content_library: list[ContentItem] = Field(default_factory=list)
    seasonal_beats: list[SeasonalBeat] = Field(default_factory=list)
    trend_signals: list[TrendSignal] = Field(default_factory=list)


# Merchant Context Models
class Identity(BaseModel):
    """Merchant identity information."""

    name: str
    city: str
    locality: str
    place_id: str
    verified: bool
    languages: list[str]
    owner_first_name: str | None = None
    established_year: int | None = None


class Subscription(BaseModel):
    """Subscription status."""

    status: str
    plan: str
    days_remaining: int | None = None
    days_since_expiry: int | None = None
    renewed_at: str | None = None


class PerformanceDelta(BaseModel):
    """Performance change metrics."""

    views_pct: float = 0.0
    calls_pct: float = 0.0
    ctr_pct: float = 0.0


class PerformanceSnapshot(BaseModel):
    """Performance metrics."""

    window_days: int
    views: int
    calls: int
    directions: int
    ctr: float
    leads: int = 0
    delta_7d: PerformanceDelta = Field(default_factory=PerformanceDelta)


class MerchantOffer(BaseModel):
    """Merchant's offer."""

    id: str
    title: str
    status: str
    started: str | None = None
    ended: str | None = None


class ConversationHistoryItem(BaseModel):
    """Single conversation turn."""

    ts: str
    from_: str = Field(..., alias="from")
    body: str
    engagement: str

    class Config:
        populate_by_name = True


class CustomerAggregate(BaseModel):
    """Aggregated customer statistics."""

    total_unique_ytd: int = 0
    lapsed_180d_plus: int = 0
    lapsed_90d_plus: int = 0
    retention_6mo_pct: float = 0.0
    retention_3mo_pct: float = 0.0
    high_risk_adult_count: int = 0
    total_active_members: int = 0
    monthly_churn_pct: float = 0.0
    trial_to_paid_pct: float = 0.0
    repeat_customer_pct: float = 0.0
    chronic_rx_count: int = 0


class ReviewTheme(BaseModel):
    """Review sentiment theme."""

    theme: str
    sentiment: str
    occurrences_30d: int
    common_quote: str | None = None


class MerchantContext(BaseModel):
    """Merchant-specific context."""

    merchant_id: str
    category_slug: str
    identity: Identity
    subscription: Subscription
    performance: PerformanceSnapshot
    offers: list[MerchantOffer] = Field(default_factory=list)
    conversation_history: list[ConversationHistoryItem] = Field(default_factory=list)
    customer_aggregate: CustomerAggregate = Field(default_factory=CustomerAggregate)
    signals: list[str] = Field(default_factory=list)
    review_themes: list[ReviewTheme] = Field(default_factory=list)


# Customer Context Models
class CustomerIdentity(BaseModel):
    """Customer identity."""

    name: str
    phone_redacted: str | None = None
    language_pref: str = "english"
    age_band: str = "unknown"
    senior_citizen: bool = False


class Relationship(BaseModel):
    """Customer-merchant relationship."""

    first_visit: str
    last_visit: str
    visits_total: int
    services_received: list[str] = Field(default_factory=list)
    lifetime_value: int = 0
    favourite_dish: str | None = None
    chronic_conditions: list[str] = Field(default_factory=list)


class Preferences(BaseModel):
    """Customer preferences."""

    preferred_slots: str | None = None
    channel: str = "whatsapp"
    reminder_opt_in: bool = False
    preferred_stylist: str | None = None
    wedding_date: str | None = None
    office_nearby: bool = False
    family_size: int | None = None
    delivery_address: str | None = None
    training_focus: str | None = None
    health_focus: str | None = None
    household_size: int | None = None


class Consent(BaseModel):
    """Customer consent information."""

    opted_in_at: str | None = None
    scope: list[str] = Field(default_factory=list)


class CustomerContext(BaseModel):
    """Customer-specific context."""

    customer_id: str
    merchant_id: str
    identity: CustomerIdentity
    relationship: Relationship
    state: Literal["new", "active", "lapsed_soft", "lapsed_hard", "churned"]
    preferences: Preferences = Field(default_factory=Preferences)
    consent: Consent = Field(default_factory=Consent)


# Trigger Context Models
class TriggerContext(BaseModel):
    """Event that prompts a message."""

    id: str
    scope: Literal["merchant", "customer"]
    kind: str
    source: Literal["external", "internal"]
    merchant_id: str
    customer_id: str | None = None
    payload: dict[str, Any]
    urgency: int = Field(..., ge=1, le=5)
    suppression_key: str
    expires_at: str


# Context Push Request/Response Models
class ContextPushRequest(BaseModel):
    """Request body for POST /v1/context."""

    scope: Literal["category", "merchant", "customer", "trigger"]
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class ContextPushResponse(BaseModel):
    """Response for POST /v1/context."""

    accepted: bool
    ack_id: str | None = None
    stored_at: str | None = None
    reason: str | None = None
    current_version: int | None = None
