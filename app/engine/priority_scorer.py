"""Priority scorer using weighted ranking."""

from app.models.features import ExtractedFeatures
from app.models.opportunities import Opportunity
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PriorityScorer:
    """Rank opportunities using weighted scoring criteria."""

    # Scoring weights
    WEIGHTS = {
        "trigger_relevance": 0.30,
        "merchant_benefit": 0.25,
        "category_fit": 0.20,
        "novelty": 0.15,
        "engagement_potential": 0.10,
    }

    def score_and_rank(
        self, opportunities: list[Opportunity], features: ExtractedFeatures
    ) -> list[Opportunity]:
        """Compute weighted scores and rank opportunities."""
        for opp in opportunities:
            # Calculate component scores
            trigger_rel = self._score_trigger_relevance(opp, features)
            merchant_ben = self._score_merchant_benefit(opp, features)
            category_fit = self._score_category_fit(opp, features)
            novelty = self._score_novelty(opp, features)
            engagement = self._score_engagement_potential(opp, features)

            # Weighted sum
            weighted = (
                trigger_rel * self.WEIGHTS["trigger_relevance"]
                + merchant_ben * self.WEIGHTS["merchant_benefit"]
                + category_fit * self.WEIGHTS["category_fit"]
                + novelty * self.WEIGHTS["novelty"]
                + engagement * self.WEIGHTS["engagement_potential"]
            )

            # Multiply by adjusted score from business rules
            opp.weighted_score = weighted * opp.adjusted_score

            logger.debug(
                "opportunity_scored",
                merchant_id=opp.merchant_id,
                opportunity=opp.kind.value,
                trigger_rel=trigger_rel,
                merchant_ben=merchant_ben,
                category_fit=category_fit,
                novelty=novelty,
                engagement=engagement,
                weighted_score=opp.weighted_score,
            )

        # Sort by weighted score descending, then by urgency
        sorted_opps = sorted(
            opportunities,
            key=lambda o: (
                o.weighted_score,
                features.trigger_urgency or 0,
            ),
            reverse=True,
        )

        logger.info(
            "opportunities_ranked",
            merchant_id=features.merchant_id,
            count=len(sorted_opps),
            top_opportunity=sorted_opps[0].kind.value if sorted_opps else None,
            top_score=sorted_opps[0].weighted_score if sorted_opps else 0,
        )

        return sorted_opps

    def _score_trigger_relevance(
        self, opp: Opportunity, features: ExtractedFeatures
    ) -> float:
        """Score how relevant the opportunity is to the trigger."""
        # Direct trigger match
        if opp.trigger_id == features.trigger_id:
            return 10.0

        # Trigger kind alignment
        trigger_kind_alignment = {
            "research_digest": ["research_digest", "education"],
            "recall_due": ["patient_recall"],
            "renewal_due": ["renewal"],
            "festival_upcoming": ["festival_campaign"],
            "regulation_change": ["compliance_alert"],
        }

        if features.trigger_kind:
            aligned_kinds = trigger_kind_alignment.get(features.trigger_kind, [])
            if opp.kind.value in aligned_kinds:
                return 9.0

        # Default
        return 5.0

    def _score_merchant_benefit(
        self, opp: Opportunity, features: ExtractedFeatures
    ) -> float:
        """Score potential merchant benefit."""
        high_benefit_opportunities = [
            "renewal",
            "offer_creation",
            "campaign",
            "winback",
            "active_planning",
        ]

        medium_benefit_opportunities = [
            "offer_promotion",
            "profile_optimization",
            "research_digest",
            "compliance_alert",
        ]

        if opp.kind.value in high_benefit_opportunities:
            return 10.0
        elif opp.kind.value in medium_benefit_opportunities:
            return 7.0
        else:
            return 5.0

    def _score_category_fit(
        self, opp: Opportunity, features: ExtractedFeatures
    ) -> float:
        """Score category appropriateness."""
        # Category-specific opportunity fit
        category_fit_map = {
            "dentists": [
                "research_digest",
                "patient_recall",
                "compliance_alert",
                "education",
            ],
            "salons": [
                "festival_campaign",
                "customer_followup",
                "curious_ask",
            ],
            "restaurants": [
                "festival_campaign",
                "offer_promotion",
                "review_response",
            ],
            "gyms": ["customer_followup", "winback", "curious_ask"],
            "pharmacies": [
                "patient_recall",
                "compliance_alert",
                "customer_followup",
            ],
        }

        fit_opportunities = category_fit_map.get(features.category_slug, [])
        if opp.kind.value in fit_opportunities:
            return 10.0

        # Universal opportunities
        universal = ["renewal", "profile_optimization", "active_planning"]
        if opp.kind.value in universal:
            return 8.0

        return 6.0

    def _score_novelty(
        self, opp: Opportunity, features: ExtractedFeatures
    ) -> float:
        """Score novelty (avoiding repetition)."""
        # Check last engagement type
        if features.last_engagement_type:
            # If last engagement was the same kind, reduce novelty
            if opp.kind.value in features.last_engagement_type:
                return 3.0

        # New types have higher novelty
        return 8.0

    def _score_engagement_potential(
        self, opp: Opportunity, features: ExtractedFeatures
    ) -> float:
        """Score likelihood of merchant engagement."""
        # Opportunities with strong CTAs tend to engage better
        if opp.suggested_cta == "binary_yes_stop":
            base_score = 8.0
        elif opp.suggested_cta == "open_ended":
            base_score = 7.0
        else:
            base_score = 5.0

        # Boost if merchant has recent engagement
        if features.days_since_last_vera_contact and features.days_since_last_vera_contact < 7:
            base_score += 2.0

        return min(base_score, 10.0)
