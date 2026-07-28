"""Prompt compiler - converts a Decision Card plus minimal context to an LLM prompt."""

import json
from typing import Any

from app.models.contexts import CategoryContext, CustomerContext, MerchantContext, TriggerContext
from app.models.decision import DecisionCard
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PromptCompiler:
    """
    Compile a minimal prompt from deterministic planner output.

    The compiler never passes raw context JSON or complete datasets. It exposes
    only facts already selected by deterministic code and small identity/voice
    details needed for language realization.
    """

    def compile(
        self,
        card: DecisionCard,
        merchant: MerchantContext | None = None,
        category: CategoryContext | None = None,
        customer: CustomerContext | None = None,
        trigger: TriggerContext | None = None,
    ) -> str:
        """Compile a JSON-only prompt from a Decision Card and minimal facts."""
        payload = {
            "decision_card": card.model_dump(mode="json"),
            "minimal_merchant_facts": self._merchant_facts(merchant),
            "category_voice": self._category_voice(category, card),
            "trigger_facts": self._trigger_facts(trigger),
            "customer_language": self._customer_language(customer),
            "output_schema": {
                "message": "string",
                "cta": card.cta,
                "rationale": "string",
            },
            "instructions": [
                "Return valid JSON only.",
                "The cta value must exactly match the Decision Card cta.",
                "Use only the provided facts.",
                "Do not invent merchant facts, offers, prices, dates, research, or statistics.",
                "Do not include send_as or suppression_key; the backend owns those fields.",
            ],
        }
        prompt = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        logger.debug(
            "prompt_compiled",
            merchant_id=card.merchant_id,
            decision=card.decision,
            cta=card.cta,
            prompt_length=len(prompt),
            includes_customer=customer is not None,
        )

        return prompt

    def _merchant_facts(self, merchant: MerchantContext | None) -> dict[str, Any]:
        if merchant is None:
            return {}
        return {
            "merchant_id": merchant.merchant_id,
            "name": merchant.identity.name,
            "owner_first_name": merchant.identity.owner_first_name,
            "locality": merchant.identity.locality,
            "city": merchant.identity.city,
            "languages": merchant.identity.languages,
            "active_offers": [
                offer.title for offer in merchant.offers if offer.status == "active"
            ][:5],
        }

    def _category_voice(
        self,
        category: CategoryContext | None,
        card: DecisionCard,
    ) -> dict[str, Any]:
        if category is None:
            return {
                "category_slug": card.tone,
                "tone": card.tone,
                "taboos": card.constraints.get("taboos", []),
            }
        return {
            "category_slug": category.slug,
            "tone": category.voice.tone,
            "allowed_vocab": category.voice.vocab_allowed[:12],
            "taboos": category.voice.taboos,
        }

    def _trigger_facts(self, trigger: TriggerContext | None) -> dict[str, Any]:
        if trigger is None:
            return {}
        minimal_payload = {
            key: value
            for key, value in trigger.payload.items()
            if key
            in {
                "top_item_id",
                "digest_item_id",
                "deadline_iso",
                "days_remaining",
                "days_until",
                "date",
                "metric",
                "delta_pct",
                "window",
                "service_due",
                "due_date",
                "last_service_date",
                "available_slots",
                "festival",
                "match",
                "venue",
                "match_time_iso",
                "theme",
                "occurrences_30d",
                "common_quote",
            }
        }
        return {
            "trigger_id": trigger.id,
            "kind": trigger.kind,
            "urgency": trigger.urgency,
            "payload": minimal_payload,
        }

    def _customer_language(self, customer: CustomerContext | None) -> dict[str, Any]:
        if customer is None:
            return {}
        return {
            "customer_id": customer.customer_id,
            "name": customer.identity.name,
            "language_pref": customer.identity.language_pref,
            "state": customer.state,
        }
