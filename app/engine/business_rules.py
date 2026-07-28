"""Business rule engine for deterministic opportunity scoring adjustments."""

from app.memory.conversation_store import ConversationStore
from app.models.features import ExtractedFeatures
from app.models.opportunities import Opportunity
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BusinessRuleEngine:
    """Apply deterministic business rules to adjust opportunity scores."""

    def __init__(self, conversation_store: ConversationStore) -> None:
        self.conversation_store = conversation_store

    def apply_rules(
        self, opportunities: list[Opportunity], features: ExtractedFeatures
    ) -> list[Opportunity]:
        """Apply all business rules to opportunities."""
        adjusted = []

        for opp in opportunities:
            # Start with raw score
            score = opp.raw_score

            # Rule: Existing offer boosts promotion
            if (
                opp.kind.value == "offer_promotion"
                and features.active_offer_count > 0
            ):
                score *= 1.5
                logger.debug(
                    "rule_applied",
                    rule="existing_offer_boost",
                    opportunity=opp.kind.value,
                    multiplier=1.5,
                )

            # Rule: No offer boosts creation
            if (
                opp.kind.value == "offer_creation"
                and features.active_offer_count == 0
            ):
                score *= 2.0
                logger.debug(
                    "rule_applied",
                    rule="no_offer_boost",
                    opportunity=opp.kind.value,
                    multiplier=2.0,
                )

            # Rule: Performance decline boosts campaigns
            if features.calls_declining or features.views_declining:
                if opp.kind.value in ["campaign", "offer_promotion", "offer_creation"]:
                    score *= 1.3
                    logger.debug(
                        "rule_applied",
                        rule="performance_decline_boost",
                        opportunity=opp.kind.value,
                        multiplier=1.3,
                    )

            # Rule: Dormant merchant penalty
            if (
                features.days_since_last_vera_contact
                and features.days_since_last_vera_contact >= 14
            ):
                score *= 0.7
                logger.debug(
                    "rule_applied",
                    rule="dormant_penalty",
                    opportunity=opp.kind.value,
                    multiplier=0.7,
                )

            # Rule: Suppression check
            if opp.suppression_key:
                if self.conversation_store.is_suppressed(opp.suppression_key):
                    score = 0.0
                    logger.debug(
                        "rule_applied",
                        rule="suppression",
                        opportunity=opp.kind.value,
                        suppression_key=opp.suppression_key,
                    )

            # Rule: Trigger urgency boost
            if features.trigger_urgency and features.trigger_urgency >= 4:
                urgency_boost = features.trigger_urgency * 0.2
                score *= (1.0 + urgency_boost)
                logger.debug(
                    "rule_applied",
                    rule="urgency_boost",
                    opportunity=opp.kind.value,
                    urgency=features.trigger_urgency,
                    boost=urgency_boost,
                )

            # Update adjusted score
            opp.adjusted_score = score
            adjusted.append(opp)

        return adjusted
