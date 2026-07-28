"""Main Decision Engine orchestrator."""

from app.adapters.category_adapter import CategoryAdapterRegistry
from app.context.knowledge_graph import KnowledgeGraph
from app.context.manager import ContextManager
from app.context.stores import ContextStore
from app.engine.business_rules import BusinessRuleEngine
from app.engine.feature_extraction import FeatureExtractor
from app.engine.opportunity_generator import OpportunityGenerator
from app.engine.priority_scorer import PriorityScorer
from app.llm.provider import LLMProvider
from app.memory.conversation_store import ConversationStore
from app.models.conversation import ConversationState
from app.planner.decision_planner import DecisionPlanner
from app.prompts.prompt_compiler import PromptCompiler
from app.utils.logging import get_logger
from app.validators.output_validator import OutputValidator

logger = get_logger(__name__)


class ComposedAction:
    """Result of composing a message."""

    def __init__(
        self,
        conversation_id: str,
        merchant_id: str,
        customer_id: str | None,
        send_as: str,
        trigger_id: str,
        template_name: str,
        template_params: list[str],
        body: str,
        cta: str,
        suppression_key: str,
        rationale: str,
    ):
        self.conversation_id = conversation_id
        self.merchant_id = merchant_id
        self.customer_id = customer_id
        self.send_as = send_as
        self.trigger_id = trigger_id
        self.template_name = template_name
        self.template_params = template_params
        self.body = body
        self.cta = cta
        self.suppression_key = suppression_key
        self.rationale = rationale


class DecisionEngine:
    """
    Main orchestrator for the AI Decision Engine pipeline.
    
    Pipeline:
    Context Store → Knowledge Graph → Feature Extraction →
    Opportunity Generator → Business Rule Engine → Priority Scorer →
    Decision Planner → Prompt Compiler → LLM Provider →
    Output Validator → Result
    """

    def __init__(
        self,
        context_store: ContextStore,
        knowledge_graph: KnowledgeGraph,
        conversation_store: ConversationStore,
        adapter_registry: CategoryAdapterRegistry,
        llm_provider: LLMProvider,
        context_manager: ContextManager | None = None,
    ):
        self.context_store = context_store
        self.context_manager = context_manager or ContextManager(context_store)
        self.knowledge_graph = knowledge_graph
        self.conversation_store = conversation_store
        self.adapter_registry = adapter_registry

        # Pipeline components
        self.feature_extractor = FeatureExtractor()
        self.opportunity_generator = OpportunityGenerator()
        self.business_rule_engine = BusinessRuleEngine(conversation_store)
        self.priority_scorer = PriorityScorer()
        self.decision_planner = DecisionPlanner(adapter_registry)
        self.prompt_compiler = PromptCompiler()
        self.llm_provider = llm_provider
        self.output_validator = OutputValidator()

        logger.info("decision_engine_initialized")

    def process_trigger(self, trigger_id: str) -> ComposedAction | None:
        """
        Process a single trigger through the full pipeline.
        
        Returns ComposedAction if successful, None if no action needed.
        """
        logger.info("processing_trigger", trigger_id=trigger_id)

        # Step 1: Load trigger context
        trigger = self.context_store.triggers.get(trigger_id)
        if not trigger:
            logger.warning("trigger_not_found", trigger_id=trigger_id)
            return None

        # Step 2: Load associated contexts
        merchant = self.context_store.merchants.get(trigger.merchant_id)
        if not merchant:
            logger.warning("merchant_not_found", merchant_id=trigger.merchant_id)
            return None

        category = self.context_store.categories.get(merchant.category_slug)
        if not category:
            logger.warning("category_not_found", category=merchant.category_slug)
            return None

        customer = None
        if trigger.customer_id:
            customer = self.context_store.customers.get(trigger.customer_id)

        # Step 3: Feature extraction
        features = self.feature_extractor.extract(
            merchant=merchant,
            category=category,
            trigger=trigger,
            customer=customer,
        )

        # Step 4: Generate opportunities
        opportunities = self.opportunity_generator.generate(
            features=features,
            trigger_id=trigger_id,
            customer_id=trigger.customer_id,
        )

        if not opportunities:
            logger.info("no_opportunities_generated", trigger_id=trigger_id)
            return None

        # Step 5: Apply business rules
        adjusted_opportunities = self.business_rule_engine.apply_rules(
            opportunities, features
        )

        # Filter out suppressed opportunities (score = 0)
        valid_opportunities = [o for o in adjusted_opportunities if o.adjusted_score > 0]
        if not valid_opportunities:
            logger.info("all_opportunities_suppressed", trigger_id=trigger_id)
            return None

        # Step 6: Priority scoring and ranking
        ranked_opportunities = self.priority_scorer.score_and_rank(
            valid_opportunities, features
        )

        # Step 7: Select top opportunity
        top_opportunity = ranked_opportunities[0]

        # Check minimum threshold
        if top_opportunity.weighted_score < 5.0:
            logger.info(
                "top_opportunity_below_threshold",
                trigger_id=trigger_id,
                score=top_opportunity.weighted_score,
            )
            return None

        # Step 8: Create Decision Card
        decision_card = self.decision_planner.plan(
            opportunity=top_opportunity,
            merchant=merchant,
            category=category,
            customer_id=trigger.customer_id,
        )

        # Step 9: Compile prompt with minimal facts only
        prompt = self.prompt_compiler.compile(
            decision_card,
            merchant=merchant,
            category=category,
            customer=customer,
            trigger=trigger,
        )
        cache_key = self._cache_key(decision_card, merchant, category, customer, trigger)

        # Step 10: Generate message via LLM, retry once on invalid output
        message_body, parsed_response, validation = self._compose_message(
            prompt=prompt,
            card=decision_card,
            category=category,
            merchant=merchant,
            customer=customer,
            trigger=trigger,
            cache_key=cache_key,
        )

        if not validation.valid:
            logger.error(
                "message_validation_failed",
                trigger_id=trigger_id,
                errors=validation.errors,
            )
            return None

        # Step 12: Create conversation and record suppression
        conversation_id = f"conv_{merchant.merchant_id}_{trigger_id}"
        self.conversation_store.create_session(
            conversation_id=conversation_id,
            merchant_id=merchant.merchant_id,
            customer_id=trigger.customer_id,
        )
        self.conversation_store.record_suppression(decision_card.suppression_key)

        # Step 13: Build action
        action = ComposedAction(
            conversation_id=conversation_id,
            merchant_id=merchant.merchant_id,
            customer_id=trigger.customer_id,
            send_as=decision_card.send_as,
            trigger_id=trigger_id,
            template_name="vera_generic_v1",
            template_params=[merchant.identity.name, "param2", "param3"],
            body=message_body,
            cta=decision_card.cta,
            suppression_key=decision_card.suppression_key,
            rationale=parsed_response.rationale if parsed_response else decision_card.reason,
        )

        logger.info(
            "action_composed",
            conversation_id=conversation_id,
            merchant_id=merchant.merchant_id,
            opportunity=top_opportunity.kind.value,
            score=top_opportunity.weighted_score,
        )

        return action

    def _compose_message(
        self,
        prompt: str,
        card,
        category,
        merchant,
        customer,
        trigger,
        cache_key: str,
    ) -> tuple[str, object | None, object]:
        """Compose a response, retry once on invalid output, and fall back deterministically."""
        raw_response = self.llm_provider.compose(prompt, cache_key=cache_key)
        parsed_response, validation = self.output_validator.validate_raw_response(
            raw_response,
            card=card,
            category=category,
            merchant=merchant,
            customer=customer,
            trigger=trigger,
        )

        if validation.valid:
            return parsed_response.body if parsed_response else raw_response, parsed_response, validation

        retry_response = self.llm_provider.compose(prompt, cache_key=f"{cache_key}:retry")
        parsed_retry, retry_validation = self.output_validator.validate_raw_response(
            retry_response,
            card=card,
            category=category,
            merchant=merchant,
            customer=customer,
            trigger=trigger,
        )

        if retry_validation.valid:
            return (
                parsed_retry.body if parsed_retry else retry_response,
                parsed_retry,
                retry_validation,
            )

        fallback_provider = getattr(self.llm_provider, "fallback_provider", None)
        if fallback_provider is None:
            fallback_provider = self.llm_provider

        fallback_response = fallback_provider.compose(prompt, cache_key=f"{cache_key}:fallback")
        parsed_fallback, fallback_validation = self.output_validator.validate_raw_response(
            fallback_response,
            card=card,
            category=category,
            merchant=merchant,
            customer=customer,
            trigger=trigger,
        )

        if parsed_fallback is not None and fallback_validation.valid:
            return parsed_fallback.body, parsed_fallback, fallback_validation

        return (
            fallback_response,
            parsed_fallback,
            fallback_validation,
        )

    def _cache_key(self, card, merchant, category, customer, trigger) -> str:
        import hashlib
        import json

        payload = {
            "decision_card": card.model_dump(mode="json"),
            "merchant": merchant.model_dump(mode="json") if merchant else None,
            "category": category.model_dump(mode="json") if category else None,
            "customer": customer.model_dump(mode="json") if customer else None,
            "trigger": trigger.model_dump(mode="json") if trigger else None,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
