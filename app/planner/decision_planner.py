"""Decision planner - converts opportunities into Decision Cards."""

from app.adapters.category_adapter import CategoryAdapterRegistry
from app.models.contexts import CategoryContext, MerchantContext
from app.models.decision import DecisionCard
from app.models.opportunities import Opportunity
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DecisionPlanner:
    """Convert winning opportunity into a Decision Card."""

    def __init__(self, adapter_registry: CategoryAdapterRegistry) -> None:
        self.adapter_registry = adapter_registry

    def plan(
        self,
        opportunity: Opportunity,
        merchant: MerchantContext,
        category: CategoryContext,
        customer_id: str | None = None,
    ) -> DecisionCard:
        """Create a Decision Card from the top opportunity."""
        adapter = self.adapter_registry.get_adapter(category.slug)
        voice = adapter.get_voice()

        # Determine audience and send_as
        if opportunity.customer_id or customer_id:
            audience = "customer"
            send_as = "merchant_on_behalf"
        else:
            audience = "merchant"
            send_as = "vera"

        # Build constraints
        constraints = {
            "max_body_length": 2000,
            "taboos": voice.taboos,
            "language": self._get_language_instruction(merchant),
            "tone": voice.tone,
        }

        # Map opportunity priority
        priority = self._map_priority(opportunity)

        # Create decision card
        card = DecisionCard(
            decision=self._create_decision_text(opportunity),
            priority=priority,
            facts=opportunity.facts[:5],  # Limit to 5 facts
            reason=opportunity.reason,
            cta=opportunity.suggested_cta,  # type: ignore
            tone=voice.tone,
            audience=audience,  # type: ignore
            send_as=send_as,  # type: ignore
            constraints=constraints,
            suppression_key=opportunity.suppression_key or f"default:{merchant.merchant_id}",
            merchant_id=merchant.merchant_id,
            customer_id=opportunity.customer_id or customer_id,
            trigger_id=opportunity.trigger_id or "manual",
        )

        logger.info(
            "decision_card_created",
            merchant_id=merchant.merchant_id,
            opportunity=opportunity.kind.value,
            priority=priority,
            cta=card.cta,
            audience=audience,
        )

        return card

    def _create_decision_text(self, opportunity: Opportunity) -> str:
        """Create the core decision text from opportunity."""
        decision_templates = {
            "research_digest": "Share relevant research digest with merchant",
            "renewal": "Encourage subscription renewal",
            "campaign": "Propose marketing campaign",
            "offer_promotion": "Promote existing offer to boost CTR",
            "offer_creation": "Suggest creating a new offer",
            "profile_optimization": "Recommend profile content update",
            "festival_campaign": "Suggest festival-specific campaign",
            "patient_recall": "Send appointment recall to customer",
            "education": "Educate merchant on category best practices",
            "customer_followup": "Suggest customer retention strategy",
            "review_response": "Highlight review themes to address",
            "compliance_alert": "Alert merchant to regulatory change",
            "curious_ask": "Ask curious question to engage merchant",
            "winback": "Re-engage inactive merchant",
            "milestone_celebration": "Celebrate merchant milestone",
            "active_planning": "Support merchant's active planning",
        }

        return decision_templates.get(
            opportunity.kind.value,
            f"Engage merchant about {opportunity.kind.value}",
        )

    def _map_priority(self, opportunity: Opportunity) -> int:
        """Map opportunity score to priority 1-5."""
        score = opportunity.weighted_score

        if score >= 80:
            return 5
        elif score >= 60:
            return 4
        elif score >= 40:
            return 3
        elif score >= 20:
            return 2
        else:
            return 1

    def _get_language_instruction(self, merchant: MerchantContext) -> str:
        """Get language instruction for constraints."""
        languages = merchant.identity.languages

        if "hi" in languages and "en" in languages:
            return "Use Hindi-English code-mix"
        elif "hi" in languages:
            return "Use Hindi"
        elif len(languages) > 1 and "en" in languages:
            return f"Use English with {languages[0]} code-mix if appropriate"
        else:
            return "Use English"
