"""Knowledge graph for fast entity relationship traversal."""

from collections import defaultdict

from app.models.contexts import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class KnowledgeGraph:
    """
    Knowledge graph connecting entities for fast traversal.
    
    Relationships:
    - Merchant -> Category (via category_slug)
    - Customer -> Merchant (via merchant_id)
    - Trigger -> Merchant (via merchant_id)
    - Trigger -> Customer (via customer_id, optional)
    """

    def __init__(self) -> None:
        # Indexed relationships
        self._merchant_to_category: dict[str, str] = {}
        self._customer_to_merchant: dict[str, str] = {}
        self._merchant_to_customers: dict[str, list[str]] = defaultdict(list)
        self._merchant_to_triggers: dict[str, list[str]] = defaultdict(list)
        self._trigger_to_merchant: dict[str, str] = {}
        self._trigger_to_customer: dict[str, str | None] = {}
        
        logger.info("knowledge_graph_initialized")

    def index_merchant(self, merchant: MerchantContext) -> None:
        """Index a merchant and its category relationship."""
        self._merchant_to_category[merchant.merchant_id] = merchant.category_slug
        logger.debug(
            "merchant_indexed",
            merchant_id=merchant.merchant_id,
            category=merchant.category_slug,
        )

    def index_customer(self, customer: CustomerContext) -> None:
        """Index a customer and its merchant relationship."""
        self._customer_to_merchant[customer.customer_id] = customer.merchant_id
        
        # Bidirectional: merchant -> customers
        if customer.customer_id not in self._merchant_to_customers[customer.merchant_id]:
            self._merchant_to_customers[customer.merchant_id].append(customer.customer_id)
        
        logger.debug(
            "customer_indexed",
            customer_id=customer.customer_id,
            merchant_id=customer.merchant_id,
        )

    def index_trigger(self, trigger: TriggerContext) -> None:
        """Index a trigger and its relationships."""
        self._trigger_to_merchant[trigger.id] = trigger.merchant_id
        self._trigger_to_customer[trigger.id] = trigger.customer_id
        
        # Bidirectional: merchant -> triggers
        if trigger.id not in self._merchant_to_triggers[trigger.merchant_id]:
            self._merchant_to_triggers[trigger.merchant_id].append(trigger.id)
        
        logger.debug(
            "trigger_indexed",
            trigger_id=trigger.id,
            merchant_id=trigger.merchant_id,
            customer_id=trigger.customer_id,
        )

    def get_category_for_merchant(self, merchant_id: str) -> str | None:
        """Get category slug for a merchant."""
        return self._merchant_to_category.get(merchant_id)

    def get_merchant_for_customer(self, customer_id: str) -> str | None:
        """Get merchant ID for a customer."""
        return self._customer_to_merchant.get(customer_id)

    def get_customers_for_merchant(self, merchant_id: str) -> list[str]:
        """Get all customer IDs for a merchant."""
        return self._merchant_to_customers.get(merchant_id, [])

    def get_triggers_for_merchant(self, merchant_id: str) -> list[str]:
        """Get all trigger IDs for a merchant."""
        return self._merchant_to_triggers.get(merchant_id, [])

    def get_merchant_for_trigger(self, trigger_id: str) -> str | None:
        """Get merchant ID for a trigger."""
        return self._trigger_to_merchant.get(trigger_id)

    def get_customer_for_trigger(self, trigger_id: str) -> str | None:
        """Get customer ID for a trigger (may be None)."""
        return self._trigger_to_customer.get(trigger_id)
