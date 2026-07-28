"""Feature extraction from raw contexts."""

from datetime import datetime

from app.models.contexts import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from app.models.features import ExtractedFeatures
from app.utils.logging import get_logger

logger = get_logger(__name__)


class FeatureExtractor:
    """Extract structured business features from contexts."""

    def extract(
        self,
        merchant: MerchantContext,
        category: CategoryContext,
        trigger: TriggerContext | None = None,
        customer: CustomerContext | None = None,
    ) -> ExtractedFeatures:
        """Extract all features from contexts."""
        features = ExtractedFeatures(
            merchant_id=merchant.merchant_id,
            category_slug=merchant.category_slug,
        )

        # Performance features
        self._extract_performance_features(features, merchant, category)

        # Offer features
        self._extract_offer_features(features, merchant)

        # Subscription features
        self._extract_subscription_features(features, merchant)

        # Engagement features
        self._extract_engagement_features(features, merchant)

        # Customer features
        self._extract_customer_features(features, merchant)

        # Review features
        self._extract_review_features(features, merchant)

        # Language features
        self._extract_language_features(features, merchant)

        # Signals
        features.signals = merchant.signals

        # Trigger features
        if trigger:
            self._extract_trigger_features(features, trigger)

        logger.debug(
            "features_extracted",
            merchant_id=merchant.merchant_id,
            features_count=len(features.model_dump(exclude_none=True)),
        )

        return features

    def _extract_performance_features(
        self,
        features: ExtractedFeatures,
        merchant: MerchantContext,
        category: CategoryContext,
    ) -> None:
        """Extract performance-related features."""
        perf = merchant.performance
        peer = category.peer_stats

        # CTR comparison
        features.ctr_delta_vs_peer = perf.ctr - peer.avg_ctr

        # Declining metrics
        features.calls_declining = perf.delta_7d.calls_pct < -0.30
        features.views_declining = perf.delta_7d.views_pct < -0.20

        # Performance spike
        features.performance_spike = (
            perf.delta_7d.calls_pct > 0.20 or perf.delta_7d.views_pct > 0.25
        )

    def _extract_offer_features(
        self, features: ExtractedFeatures, merchant: MerchantContext
    ) -> None:
        """Extract offer-related features."""
        active_offers = [o for o in merchant.offers if o.status == "active"]
        expired_offers = [o for o in merchant.offers if o.status == "expired"]

        features.active_offer_count = len(active_offers)
        features.expired_offer_count = len(expired_offers)

        if active_offers:
            features.has_recent_offer = True
            # Calculate recency from most recent active offer
            try:
                most_recent = max(
                    active_offers,
                    key=lambda o: datetime.fromisoformat(o.started)
                    if o.started
                    else datetime.min,
                )
                if most_recent.started:
                    started_date = datetime.fromisoformat(most_recent.started)
                    features.offer_recency_days = (
                        datetime.utcnow() - started_date
                    ).days
            except (ValueError, AttributeError):
                pass

    def _extract_subscription_features(
        self, features: ExtractedFeatures, merchant: MerchantContext
    ) -> None:
        """Extract subscription-related features."""
        sub = merchant.subscription

        if sub.status == "expired":
            features.subscription_expired = True
        elif sub.status == "active" and sub.days_remaining:
            features.days_until_renewal = sub.days_remaining
            features.subscription_risk = sub.days_remaining < 30

    def _extract_engagement_features(
        self, features: ExtractedFeatures, merchant: MerchantContext
    ) -> None:
        """Extract engagement history features."""
        if merchant.conversation_history:
            last_turn = merchant.conversation_history[-1]
            try:
                last_ts = datetime.fromisoformat(last_turn.ts.replace("Z", "+00:00"))
                days_since = (datetime.utcnow() - last_ts).days
                features.days_since_last_vera_contact = days_since
                features.last_engagement_type = last_turn.engagement
            except (ValueError, AttributeError):
                pass

        # Stale posts signal
        for signal in merchant.signals:
            if signal.startswith("stale_posts:"):
                features.has_stale_posts = True
                try:
                    days = int(signal.split(":")[1].replace("d", ""))
                    features.stale_posts_days = days
                except (IndexError, ValueError):
                    pass

    def _extract_customer_features(
        self, features: ExtractedFeatures, merchant: MerchantContext
    ) -> None:
        """Extract customer aggregate features."""
        agg = merchant.customer_aggregate

        if agg.total_unique_ytd > 0:
            features.lapse_rate = agg.lapsed_180d_plus / agg.total_unique_ytd

        if agg.retention_6mo_pct > 0:
            features.retention_rate = agg.retention_6mo_pct
        elif agg.retention_3mo_pct > 0:
            features.retention_rate = agg.retention_3mo_pct

        features.high_risk_cohort_count = agg.high_risk_adult_count

    def _extract_review_features(
        self, features: ExtractedFeatures, merchant: MerchantContext
    ) -> None:
        """Extract review theme features."""
        for theme in merchant.review_themes:
            if theme.sentiment == "neg":
                features.negative_review_themes.append(theme.theme)
            elif theme.sentiment == "pos":
                features.positive_review_themes.append(theme.theme)

    def _extract_language_features(
        self, features: ExtractedFeatures, merchant: MerchantContext
    ) -> None:
        """Extract language preference features."""
        languages = merchant.identity.languages
        features.supports_hindi = "hi" in languages

        if len(languages) == 1:
            features.language_preference = languages[0]
        elif "hi" in languages and "en" in languages:
            features.language_preference = "hi-en mix"
        else:
            features.language_preference = "english"

    def _extract_trigger_features(
        self, features: ExtractedFeatures, trigger: TriggerContext
    ) -> None:
        """Extract trigger-specific features."""
        features.trigger_id = trigger.id
        features.trigger_kind = trigger.kind
        features.trigger_urgency = trigger.urgency
        features.trigger_scope = trigger.scope
