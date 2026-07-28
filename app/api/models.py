"""API request/response models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# POST /v1/context
class ContextPushRequest(BaseModel):
    """Request body for POST /v1/context."""

    scope: str
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
    details: str | None = None


# POST /v1/tick
class TickRequest(BaseModel):
    """Request body for POST /v1/tick."""

    now: str
    available_triggers: list[str] = Field(default_factory=list)


class TickAction(BaseModel):
    """Single action in tick response."""

    conversation_id: str
    merchant_id: str
    customer_id: str | None
    send_as: str
    trigger_id: str
    template_name: str
    template_params: list[str]
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    """Response for POST /v1/tick."""

    actions: list[TickAction] = Field(default_factory=list)


# POST /v1/reply
class ReplyRequest(BaseModel):
    """Request body for POST /v1/reply."""

    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str
    message: str
    received_at: str
    turn_number: int


class ReplyResponse(BaseModel):
    """Response for POST /v1/reply."""

    action: Literal["send", "wait", "end"]
    body: str | None = None
    cta: str | None = None
    rationale: str
    wait_seconds: int | None = None


# GET /v1/healthz
class HealthResponse(BaseModel):
    """Response for GET /v1/healthz."""

    status: str
    uptime_seconds: int
    contexts_loaded: dict[str, int]


# GET /v1/metadata
class MetadataResponse(BaseModel):
    """Response for GET /v1/metadata."""

    team_name: str
    team_members: list[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str
