"""Output validation for composed messages."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.models.contexts import CategoryContext, CustomerContext, MerchantContext, TriggerContext
from app.models.decision import DecisionCard
from app.utils.logging import get_logger

logger = get_logger(__name__)


class LLMMessage(BaseModel):
    """Structured response expected from the LLM."""

    message: str
    cta: str
    rationale: str


class ValidationResult(BaseModel):
    """Result of output validation."""

    valid: bool
    errors: list[str] = Field(default_factory=list)


class OutputValidator:
    """Validate schema, CTA shape, category constraints, and hallucination risk."""

    PRICE_PATTERN = re.compile(r"(?:rs\.?|inr|₹)\s?[\d,]+|[\d,]+\s?/-", re.IGNORECASE)
    PERCENT_PATTERN = re.compile(r"[+-]?\d+(?:\.\d+)?\s?%")
    DATE_PATTERN = re.compile(
        r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s?"
        r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|"
        r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s?\d{1,2})\b",
        re.IGNORECASE,
    )

    def parse_response(self, raw_response: str) -> tuple[LLMMessage | None, list[str]]:
        """Parse and validate the LLM JSON schema."""
        try:
            parsed = json.loads(raw_response)
            return LLMMessage(**parsed), []
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            return None, [f"Invalid LLM JSON schema: {exc}"]

    def validate(
        self,
        message: str,
        card: DecisionCard,
        category: CategoryContext | None = None,
        merchant: MerchantContext | None = None,
        customer: CustomerContext | None = None,
        trigger: TriggerContext | None = None,
        response_cta: str | None = None,
        rationale: str | None = None,
    ) -> ValidationResult:
        """Validate a composed message against deterministic inputs."""
        errors: list[str] = []

        if not message or not message.strip():
            errors.append("Message body is empty")

        if rationale is not None and not rationale.strip():
            errors.append("Rationale is required")

        if response_cta is not None and response_cta != card.cta:
            errors.append("LLM changed the deterministic CTA")

        max_length = card.constraints.get("max_body_length", 2000)
        if isinstance(max_length, int) and len(message) > max_length:
            errors.append(f"Message exceeds max length: {len(message)} > {max_length}")

        self._validate_category_tone(message, card, category, errors)
        self._validate_cta(message, card, errors)
        self._validate_hallucinations(message, card, category, merchant, customer, trigger, errors)

        is_valid = len(errors) == 0
        logger.debug(
            "message_validated",
            merchant_id=card.merchant_id,
            valid=is_valid,
            error_count=len(errors),
        )

        if not is_valid:
            logger.warning(
                "message_validation_failed",
                merchant_id=card.merchant_id,
                errors=errors,
            )

        return ValidationResult(valid=is_valid, errors=errors)

    def validate_raw_response(
        self,
        raw_response: str,
        card: DecisionCard,
        category: CategoryContext | None = None,
        merchant: MerchantContext | None = None,
        customer: CustomerContext | None = None,
        trigger: TriggerContext | None = None,
    ) -> tuple[LLMMessage | None, ValidationResult]:
        """Parse a raw JSON response, then validate the message payload."""
        parsed, parse_errors = self.parse_response(raw_response)
        if parsed is None:
            return None, ValidationResult(valid=False, errors=parse_errors)

        result = self.validate(
            message=parsed.message,
            card=card,
            category=category,
            merchant=merchant,
            customer=customer,
            trigger=trigger,
            response_cta=parsed.cta,
            rationale=parsed.rationale,
        )
        return parsed, result

    def _validate_category_tone(
        self,
        message: str,
        card: DecisionCard,
        category: CategoryContext | None,
        errors: list[str],
    ) -> None:
        taboos = card.constraints.get("taboos", [])
        if category is not None:
            taboos = list(taboos) + category.voice.taboos

        if isinstance(taboos, list):
            message_lower = message.lower()
            for taboo in set(str(item).lower() for item in taboos):
                if taboo and taboo in message_lower:
                    errors.append(f"Contains forbidden word: '{taboo}'")

        if card.tone == "peer_clinical":
            if message.count("!") > 2:
                errors.append("Excessive exclamation marks for clinical tone")
            for word in ["amazing", "incredible", "best ever"]:
                if word in message.lower():
                    errors.append(f"Promotional language '{word}' inappropriate for clinical tone")

    def _validate_cta(
        self,
        message: str,
        card: DecisionCard,
        errors: list[str],
    ) -> None:
        question_count = message.count("?")
        lower = message.lower()

        if card.cta == "none":
            if question_count > 0 or "reply " in lower:
                errors.append("CTA is none but message asks for a response")
            return

        if question_count > 1:
            errors.append("Message contains multiple question-style CTAs")

        if card.cta == "binary_yes_stop":
            has_yes = re.search(r"\byes\b", lower) is not None
            has_stop = re.search(r"\bstop\b", lower) is not None
            if not (has_yes and has_stop):
                errors.append("Binary CTA must offer YES/STOP")
        elif card.cta == "open_ended" and question_count != 1:
            errors.append("Open-ended CTA must contain exactly one question")

    def _validate_hallucinations(
        self,
        message: str,
        card: DecisionCard,
        category: CategoryContext | None,
        merchant: MerchantContext | None,
        customer: CustomerContext | None,
        trigger: TriggerContext | None,
        errors: list[str],
    ) -> None:
        allowed_text = self._allowed_text(card, category, merchant, customer, trigger)
        lower_allowed = allowed_text.lower()
        lower_message = message.lower()

        self._reject_unbacked_matches(
            "price",
            self.PRICE_PATTERN.findall(message),
            lower_allowed,
            errors,
        )
        self._reject_unbacked_matches(
            "statistic",
            self.PERCENT_PATTERN.findall(message),
            lower_allowed,
            errors,
        )
        self._reject_unbacked_matches(
            "date",
            self.DATE_PATTERN.findall(message),
            lower_allowed,
            errors,
        )

        if "research" in lower_message or "trial" in lower_message or "study" in lower_message:
            has_research_fact = any(
                word in lower_allowed for word in ["research", "trial", "study", "jida", "digest"]
            )
            if not has_research_fact:
                errors.append("Research claim is not supported by provided facts")

        if merchant is not None:
            active_offer_titles = [offer.title.lower() for offer in merchant.offers]
            mentions_offer_language = any(word in lower_message for word in ["offer", "discount", "free"])
            if mentions_offer_language and active_offer_titles:
                message_contains_known_offer = any(title in lower_message for title in active_offer_titles)
                message_has_backed_offer_fact = any("offer" in fact.lower() for fact in card.facts)
                if not message_contains_known_offer and not message_has_backed_offer_fact:
                    errors.append("Offer language is not tied to a known merchant offer")

    def _reject_unbacked_matches(
        self,
        label: str,
        matches: list[str],
        lower_allowed: str,
        errors: list[str],
    ) -> None:
        for match in set(matches):
            normalized = match.lower().replace(",", "")
            allowed_normalized = lower_allowed.replace(",", "")
            digits = re.sub(r"\D", "", normalized)
            if normalized not in allowed_normalized and (digits and digits not in allowed_normalized):
                errors.append(f"Hallucinated {label}: {match}")

    def _allowed_text(
        self,
        card: DecisionCard,
        category: CategoryContext | None,
        merchant: MerchantContext | None,
        customer: CustomerContext | None,
        trigger: TriggerContext | None,
    ) -> str:
        chunks: list[str] = [
            card.decision,
            card.reason,
            card.cta,
            " ".join(card.facts),
            json.dumps(card.constraints, ensure_ascii=False),
        ]
        if category is not None:
            chunks.extend(
                [
                    category.slug,
                    category.voice.tone,
                    " ".join(category.voice.vocab_allowed),
                    " ".join(category.voice.taboos),
                    " ".join(item.title for item in category.digest),
                    " ".join(item.source for item in category.digest),
                    " ".join(item.summary for item in category.digest),
                    " ".join(offer.title for offer in category.offer_catalog),
                ]
            )
        if merchant is not None:
            chunks.extend(
                [
                    merchant.identity.name,
                    merchant.identity.owner_first_name or "",
                    merchant.identity.locality,
                    merchant.identity.city,
                    " ".join(merchant.identity.languages),
                    " ".join(offer.title for offer in merchant.offers),
                ]
            )
        if customer is not None:
            chunks.extend(
                [
                    customer.identity.name,
                    customer.identity.language_pref,
                    customer.state,
                    json.dumps(customer.preferences.model_dump(), ensure_ascii=False),
                    json.dumps(customer.relationship.model_dump(), ensure_ascii=False),
                ]
            )
        if trigger is not None:
            chunks.extend(
                [
                    trigger.id,
                    trigger.kind,
                    trigger.suppression_key,
                    json.dumps(trigger.payload, ensure_ascii=False),
                ]
            )
        return " ".join(chunks)
