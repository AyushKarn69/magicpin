"""Decision Card model - the structured output before LLM composition."""

from typing import Literal

from pydantic import BaseModel, Field


class DecisionCard(BaseModel):
    """
    Structured decision representation passed to the LLM.
    
    This is the ONLY object the LLM sees - no raw context JSON.
    All business reasoning is complete before this is created.
    """

    decision: str = Field(..., description="The core decision/action to communicate")
    priority: int = Field(..., ge=1, le=5, description="Priority level 1-5")
    facts: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="3-5 verifiable facts to anchor the message",
    )
    reason: str = Field(..., description="Why this decision was made (single sentence)")
    cta: Literal["binary_yes_stop", "open_ended", "none"] = Field(
        ..., description="Call to action type"
    )
    tone: str = Field(..., description="Tone to use (peer_clinical, warm_retail, etc.)")
    audience: Literal["merchant", "customer"] = Field(..., description="Who receives this")
    send_as: Literal["vera", "merchant_on_behalf"] = Field(
        ..., description="Attribution for the message"
    )
    constraints: dict[str, str | list[str] | int] = Field(
        default_factory=dict, description="Message constraints (length, taboos, language)"
    )
    suppression_key: str = Field(..., description="Deduplication key")
    merchant_id: str = Field(..., description="Associated merchant")
    customer_id: str | None = Field(None, description="Associated customer if applicable")
    trigger_id: str = Field(..., description="Trigger that initiated this")
