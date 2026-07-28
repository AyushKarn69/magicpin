"""Category adapter system for vertical-specific behavior."""

from abc import ABC, abstractmethod

from app.models.contexts import (
    DigestItem,
    OfferTemplate,
    SeasonalBeat,
    VoiceProfile,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CategoryAdapter(ABC):
    """Base adapter interface for category-specific logic."""

    @abstractmethod
    def get_voice(self) -> VoiceProfile:
        """Return voice profile for this category."""
        pass

    @abstractmethod
    def get_offer_catalog(self) -> list[OfferTemplate]:
        """Return canonical offer templates."""
        pass

    @abstractmethod
    def get_seasonal_beats(self) -> list[SeasonalBeat]:
        """Return seasonal patterns."""
        pass

    @abstractmethod
    def lookup_digest_item(self, item_id: str) -> DigestItem | None:
        """Lookup a specific digest item."""
        pass


class DentistAdapter(CategoryAdapter):
    """Adapter for dentistry vertical."""

    def get_voice(self) -> VoiceProfile:
        return VoiceProfile(
            tone="peer_clinical",
            vocab_allowed=[
                "fluoride varnish",
                "caries",
                "recall",
                "prophylaxis",
                "radiograph",
                "endodontic",
            ],
            taboos=["cure", "guaranteed", "painless", "best dentist"],
        )

    def get_offer_catalog(self) -> list[OfferTemplate]:
        return [
            OfferTemplate(title="Dental Cleaning @ ₹299", value="299"),
            OfferTemplate(title="Free Consultation", value="0"),
            OfferTemplate(title="Teeth Whitening @ ₹1,499", value="1499"),
            OfferTemplate(title="Dental Checkup @ ₹199", value="199"),
        ]

    def get_seasonal_beats(self) -> list[SeasonalBeat]:
        return [
            SeasonalBeat(month_range="Nov-Feb", note="exam-stress bruxism spike"),
            SeasonalBeat(month_range="Oct-Dec", note="wedding whitening peak"),
        ]

    def lookup_digest_item(self, item_id: str) -> DigestItem | None:
        # In production, this would query a digest database
        return None


class SalonAdapter(CategoryAdapter):
    """Adapter for salon vertical."""

    def get_voice(self) -> VoiceProfile:
        return VoiceProfile(
            tone="warm_retail",
            vocab_allowed=["balayage", "hair spa", "keratin", "styling"],
            taboos=["permanent", "guaranteed results"],
        )

    def get_offer_catalog(self) -> list[OfferTemplate]:
        return [
            OfferTemplate(title="Haircut @ ₹99", value="99"),
            OfferTemplate(title="Hair Spa @ ₹499", value="499"),
            OfferTemplate(title="Bridal Package @ ₹9,999", value="9999"),
            OfferTemplate(title="Manicure + Pedicure @ ₹599", value="599"),
        ]

    def get_seasonal_beats(self) -> list[SeasonalBeat]:
        return [
            SeasonalBeat(month_range="Oct-Dec", note="wedding season peak"),
            SeasonalBeat(month_range="Apr-Jun", note="summer treatments"),
        ]

    def lookup_digest_item(self, item_id: str) -> DigestItem | None:
        return None


class RestaurantAdapter(CategoryAdapter):
    """Adapter for restaurant vertical."""

    def get_voice(self) -> VoiceProfile:
        return VoiceProfile(
            tone="friendly_casual",
            vocab_allowed=["combo", "thali", "delivery", "dine-in"],
            taboos=["best food", "world-class"],
        )

    def get_offer_catalog(self) -> list[OfferTemplate]:
        return [
            OfferTemplate(title="Weekday Lunch Thali @ ₹149", value="149"),
            OfferTemplate(title="Buy 1 Get 1 Free Pizza", value="0"),
            OfferTemplate(title="Family Combo @ ₹999", value="999"),
            OfferTemplate(title="Free Delivery > ₹299", value="0"),
        ]

    def get_seasonal_beats(self) -> list[SeasonalBeat]:
        return [
            SeasonalBeat(month_range="Mar-May", note="IPL match nights"),
            SeasonalBeat(month_range="Oct-Nov", note="festival season"),
        ]

    def lookup_digest_item(self, item_id: str) -> DigestItem | None:
        return None


class GymAdapter(CategoryAdapter):
    """Adapter for gym vertical."""

    def get_voice(self) -> VoiceProfile:
        return VoiceProfile(
            tone="motivational",
            vocab_allowed=["PT", "membership", "workout", "training"],
            taboos=["guaranteed weight loss", "instant results"],
        )

    def get_offer_catalog(self) -> list[OfferTemplate]:
        return [
            OfferTemplate(title="3 FREE Trial Classes", value="0"),
            OfferTemplate(title="First Month @ ₹499", value="499"),
            OfferTemplate(title="Personal Training Package @ ₹2,999", value="2999"),
        ]

    def get_seasonal_beats(self) -> list[SeasonalBeat]:
        return [
            SeasonalBeat(month_range="Jan-Feb", note="New Year resolution peak"),
            SeasonalBeat(month_range="Apr-Jun", note="summer fitness goals"),
        ]

    def lookup_digest_item(self, item_id: str) -> DigestItem | None:
        return None


class PharmacyAdapter(CategoryAdapter):
    """Adapter for pharmacy vertical."""

    def get_voice(self) -> VoiceProfile:
        return VoiceProfile(
            tone="professional_helpful",
            vocab_allowed=["prescription", "refill", "delivery", "chronic"],
            taboos=["cure", "treatment", "medical advice"],
        )

    def get_offer_catalog(self) -> list[OfferTemplate]:
        return [
            OfferTemplate(title="Free Home Delivery > ₹499", value="0"),
            OfferTemplate(title="Senior Citizen 15% OFF", value="0"),
            OfferTemplate(title="Monthly Medicine Pack @ ₹999", value="999"),
        ]

    def get_seasonal_beats(self) -> list[SeasonalBeat]:
        return [
            SeasonalBeat(month_range="Mar-Jun", note="summer ORS/sunscreen demand"),
            SeasonalBeat(month_range="Oct-Feb", note="cold/flu medication peak"),
        ]

    def lookup_digest_item(self, item_id: str) -> DigestItem | None:
        return None


class CategoryAdapterRegistry:
    """Registry for category adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, CategoryAdapter] = {
            "dentists": DentistAdapter(),
            "salons": SalonAdapter(),
            "restaurants": RestaurantAdapter(),
            "gyms": GymAdapter(),
            "pharmacies": PharmacyAdapter(),
        }
        logger.info(
            "category_adapter_registry_initialized",
            categories=list(self._adapters.keys()),
        )

    def get_adapter(self, category_slug: str) -> CategoryAdapter:
        """Get adapter for a category."""
        adapter = self._adapters.get(category_slug)
        if not adapter:
            logger.warning(
                "category_adapter_not_found",
                category=category_slug,
                fallback="dentists",
            )
            return self._adapters["dentists"]  # Default fallback
        return adapter

    def register_adapter(self, category_slug: str, adapter: CategoryAdapter) -> None:
        """Register a new category adapter."""
        self._adapters[category_slug] = adapter
        logger.info("category_adapter_registered", category=category_slug)
