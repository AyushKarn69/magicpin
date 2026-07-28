"""Generate candidate engagement opportunities from features."""

from app.models.features import ExtractedFeatures
from app.models.opportunities import Opportunity, OpportunityKind
from app.utils.logging import get_logger

logger = get_logger(__name__)


class OpportunityGenerator:
    """Generate candidate opportunities (no ranking)."""

    def generate(
        self,
        features: ExtractedFeatures,
        trigger_id: str | None = None,
        customer_id: str | None = None,
    ) -> list[Opportunity]:
        """Generate all applicable opportunities."""
        opportunities: list[Opportunity] = []

        # Research digest opportunity
        if features.trigger_kind == "research_digest":
            opportunities.append(
                self._create_research_digest_opportunity(features, trigger_id)
            )

        # Renewal opportunity
        if features.subscription_risk and not features.subscription_expired:
            opportunities.append(
                self._create_renewal_opportunity(features, trigger_id)
            )

        # Offer promotion or creation
        if features.ctr_delta_vs_peer and features.ctr_delta_vs_peer < -0.005:
            if features.active_offer_count > 0:
                opportunities.append(
                    self._create_offer_promotion_opportunity(features, trigger_id)
                )
            else:
                opportunities.append(
                    self._create_offer_creation_opportunity(features, trigger_id)
                )

        # Profile optimization
        if features.has_stale_posts:
            opportunities.append(
                self._create_profile_optimization_opportunity(features, trigger_id)
            )

        # Patient recall (customer scope)
        if features.trigger_kind == "recall_due" and customer_id:
            opportunities.append(
                self._create_patient_recall_opportunity(features, trigger_id, customer_id)
            )

        # Customer followup
        if features.lapse_rate and features.lapse_rate > 0.30:
            opportunities.append(
                self._create_customer_followup_opportunity(features, trigger_id)
            )

        # Festival campaign
        if features.trigger_kind == "festival_upcoming":
            opportunities.append(
                self._create_festival_campaign_opportunity(features, trigger_id)
            )

        # Compliance alert
        if features.trigger_kind == "regulation_change":
            opportunities.append(
                self._create_compliance_alert_opportunity(features, trigger_id)
            )

        # Curious ask
        if features.trigger_kind == "curious_ask_due":
            opportunities.append(
                self._create_curious_ask_opportunity(features, trigger_id)
            )

        # Winback
        if features.subscription_expired or "winback_eligible" in features.signals:
            opportunities.append(
                self._create_winback_opportunity(features, trigger_id)
            )

        # Milestone celebration
        if features.trigger_kind == "milestone_reached":
            opportunities.append(
                self._create_milestone_opportunity(features, trigger_id)
            )

        # Active planning
        if features.trigger_kind == "active_planning_intent":
            opportunities.append(
                self._create_active_planning_opportunity(features, trigger_id)
            )

        logger.debug(
            "opportunities_generated",
            merchant_id=features.merchant_id,
            count=len(opportunities),
            kinds=[opp.kind.value for opp in opportunities],
        )

        return opportunities

    def _create_research_digest_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create research digest opportunity."""
        facts = [
            f"Category: {features.category_slug}",
            "New research digest available",
        ]
        if features.high_risk_cohort_count > 0:
            facts.append(f"High-risk patient cohort: {features.high_risk_cohort_count}")

        return Opportunity(
            kind=OpportunityKind.RESEARCH_DIGEST,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=5.0,
            reason="External research digest released for category",
            facts=facts,
            suggested_cta="open_ended",
            suppression_key=f"research:{features.category_slug}:digest",
        )

    def _create_renewal_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create subscription renewal opportunity."""
        facts = [
            f"Days until renewal: {features.days_until_renewal}",
            "Subscription at risk",
        ]
        return Opportunity(
            kind=OpportunityKind.RENEWAL,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=8.0,
            reason="Subscription expiring soon",
            facts=facts,
            suggested_cta="binary_yes_stop",
            suppression_key=f"renewal:{features.merchant_id}",
        )

    def _create_offer_promotion_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create offer promotion opportunity."""
        facts = [
            f"CTR below peer by {abs(features.ctr_delta_vs_peer or 0):.3f}",
            f"Active offers: {features.active_offer_count}",
        ]
        return Opportunity(
            kind=OpportunityKind.OFFER_PROMOTION,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=6.0,
            reason="CTR below peer with existing offers",
            facts=facts,
            suggested_cta="open_ended",
            suppression_key=f"offer_promo:{features.merchant_id}",
        )

    def _create_offer_creation_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create offer creation opportunity."""
        facts = [
            f"CTR below peer by {abs(features.ctr_delta_vs_peer or 0):.3f}",
            "No active offers",
        ]
        return Opportunity(
            kind=OpportunityKind.OFFER_CREATION,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=7.0,
            reason="CTR below peer with no offers",
            facts=facts,
            suggested_cta="binary_yes_stop",
            suppression_key=f"offer_create:{features.merchant_id}",
        )

    def _create_profile_optimization_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create profile optimization opportunity."""
        facts = [f"Stale posts: {features.stale_posts_days} days"]
        return Opportunity(
            kind=OpportunityKind.PROFILE_OPTIMIZATION,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=4.0,
            reason="Profile content needs update",
            facts=facts,
            suggested_cta="binary_yes_stop",
            suppression_key=f"profile_opt:{features.merchant_id}",
        )

    def _create_patient_recall_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None, customer_id: str
    ) -> Opportunity:
        """Create patient recall opportunity."""
        facts = ["Recall window open", "Customer lapsed_soft state"]
        return Opportunity(
            kind=OpportunityKind.PATIENT_RECALL,
            merchant_id=features.merchant_id,
            customer_id=customer_id,
            trigger_id=trigger_id,
            raw_score=7.0,
            reason="Customer recall due",
            facts=facts,
            suggested_cta="open_ended",
            suppression_key=f"recall:{customer_id}",
        )

    def _create_customer_followup_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create customer followup opportunity."""
        facts = [f"Lapse rate: {features.lapse_rate:.2f}"]
        return Opportunity(
            kind=OpportunityKind.CUSTOMER_FOLLOWUP,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=5.0,
            reason="High customer lapse rate",
            facts=facts,
            suggested_cta="open_ended",
            suppression_key=f"customer_followup:{features.merchant_id}",
        )

    def _create_festival_campaign_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create festival campaign opportunity."""
        facts = ["Festival approaching", f"Category: {features.category_slug}"]
        return Opportunity(
            kind=OpportunityKind.FESTIVAL_CAMPAIGN,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=6.0,
            reason="Festival relevant to category",
            facts=facts,
            suggested_cta="open_ended",
            suppression_key=f"festival:{features.merchant_id}",
        )

    def _create_compliance_alert_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create compliance alert opportunity."""
        facts = ["Regulation change", f"Category: {features.category_slug}"]
        return Opportunity(
            kind=OpportunityKind.COMPLIANCE_ALERT,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=9.0,
            reason="Regulatory compliance requirement",
            facts=facts,
            suggested_cta="open_ended",
            suppression_key=f"compliance:{features.merchant_id}",
        )

    def _create_curious_ask_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create curious ask opportunity."""
        facts = ["Engagement cadence", "Curiosity-driven conversation"]
        return Opportunity(
            kind=OpportunityKind.CURIOUS_ASK,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=3.0,
            reason="Scheduled curiosity engagement",
            facts=facts,
            suggested_cta="open_ended",
            suppression_key=f"curious:{features.merchant_id}",
        )

    def _create_winback_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create winback opportunity."""
        facts = ["Subscription expired or winback eligible"]
        return Opportunity(
            kind=OpportunityKind.WINBACK,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=7.0,
            reason="Merchant winback opportunity",
            facts=facts,
            suggested_cta="binary_yes_stop",
            suppression_key=f"winback:{features.merchant_id}",
        )

    def _create_milestone_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create milestone celebration opportunity."""
        facts = ["Milestone reached or imminent"]
        return Opportunity(
            kind=OpportunityKind.MILESTONE_CELEBRATION,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=4.0,
            reason="Merchant milestone achievement",
            facts=facts,
            suggested_cta="none",
            suppression_key=f"milestone:{features.merchant_id}",
        )

    def _create_active_planning_opportunity(
        self, features: ExtractedFeatures, trigger_id: str | None
    ) -> Opportunity:
        """Create active planning opportunity."""
        facts = ["Merchant initiated planning conversation"]
        return Opportunity(
            kind=OpportunityKind.ACTIVE_PLANNING,
            merchant_id=features.merchant_id,
            trigger_id=trigger_id,
            raw_score=10.0,
            reason="Merchant has active planning intent",
            facts=facts,
            suggested_cta="open_ended",
            suppression_key=f"planning:{features.merchant_id}",
        )
