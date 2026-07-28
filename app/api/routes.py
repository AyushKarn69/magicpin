"""FastAPI routes for challenge endpoints."""

import asyncio
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.dependencies import (
    get_context_manager,
    get_context_store,
    get_conversation_store,
    get_decision_engine,
    get_intent_detector,
    get_knowledge_graph,
    get_llm_provider,
)
from app.api.models import (
    ContextPushRequest,
    ContextPushResponse,
    HealthResponse,
    MetadataResponse,
    ReplyRequest,
    ReplyResponse,
    TickAction,
    TickRequest,
    TickResponse,
)
from app.context.knowledge_graph import KnowledgeGraph
from app.context.manager import ContextManager
from app.context.stores import ContextStore
from app.engine.decision_engine import DecisionEngine
from app.llm.provider import LLMProvider
from app.memory.conversation_store import ConversationStore
from app.memory.intent_detector import IntentDetector
from app.models.conversation import ConversationState
from app.models.decision import DecisionCard
from app.prompts.prompt_compiler import PromptCompiler
from app.utils.config import get_settings
from app.utils.logging import get_logger
from app.validators.output_validator import OutputValidator

logger = get_logger(__name__)
router = APIRouter()
prompt_compiler = PromptCompiler()
output_validator = OutputValidator()

# Track server start time
_start_time = time.time()


@router.get("/v1/healthz", response_model=HealthResponse)
async def healthz(
    context_manager: ContextManager = Depends(get_context_manager),
) -> HealthResponse:
    """Health check endpoint."""
    uptime = int(time.time() - _start_time)
    counts = context_manager.get_counts()
    
    logger.debug("healthz_check", uptime=uptime, contexts=counts)
    
    return HealthResponse(
        status="ok",
        uptime_seconds=uptime,
        contexts_loaded=counts,
    )


@router.get("/v1/metadata", response_model=MetadataResponse)
async def metadata() -> MetadataResponse:
    """Metadata endpoint."""
    settings = get_settings()
    
    return MetadataResponse(
        team_name=settings.team_name,
        team_members=settings.get_team_members_list(),
        model=settings.model_name,
        approach=settings.approach,
        contact_email=settings.contact_email,
        version=settings.version,
        submitted_at=datetime.utcnow().isoformat() + "Z",
    )


@router.post("/v1/context", response_model=ContextPushResponse)
async def push_context(
    request: ContextPushRequest,
    response: Response,
    context_manager: ContextManager = Depends(get_context_manager),
    knowledge_graph: KnowledgeGraph = Depends(get_knowledge_graph),
) -> ContextPushResponse:
    """Receive context push."""
    logger.info(
        "context_push_received",
        scope=request.scope,
        context_id=request.context_id,
        version=request.version,
    )

    if request.scope not in {"category", "merchant", "customer", "trigger"}:
        response.status_code = 400
        return ContextPushResponse(
            accepted=False,
            reason="invalid_scope",
            details=f"Unsupported scope: {request.scope}",
        )

    try:
        # Store the context
        success, current_version = context_manager.put_context(
            scope=request.scope,
            context_id=request.context_id,
            version=request.version,
            payload=request.payload,
        )

        if not success:
            response.status_code = 409
            return ContextPushResponse(
                accepted=False,
                reason="stale_version",
                current_version=current_version,
            )

        # Update knowledge graph
        if request.scope == "merchant":
            from app.models.contexts import MerchantContext
            merchant = MerchantContext(**request.payload)
            knowledge_graph.index_merchant(merchant)
        elif request.scope == "customer":
            from app.models.contexts import CustomerContext
            customer = CustomerContext(**request.payload)
            knowledge_graph.index_customer(customer)
        elif request.scope == "trigger":
            from app.models.contexts import TriggerContext
            trigger = TriggerContext(**request.payload)
            knowledge_graph.index_trigger(trigger)

        return ContextPushResponse(
            accepted=True,
            ack_id=f"ack_{request.context_id}_v{request.version}",
            stored_at=datetime.utcnow().isoformat() + "Z",
        )

    except Exception as e:
        logger.error("context_push_failed", error=str(e), context_id=request.context_id)
        return JSONResponse(
            status_code=400,
            content={
                "accepted": False,
                "reason": f"validation_error: {str(e)}",
            },
        )


@router.post("/v1/tick", response_model=TickResponse)
async def tick(
    request: TickRequest,
    decision_engine: DecisionEngine = Depends(get_decision_engine),
) -> TickResponse:
    """Periodic tick - bot evaluates triggers and initiates messages."""
    logger.info(
        "tick_received",
        now=request.now,
        trigger_count=len(request.available_triggers),
    )
    
    actions: list[TickAction] = []
    
    for trigger_id in request.available_triggers:
        try:
            # Process trigger through decision engine
            action = decision_engine.process_trigger(trigger_id)
            
            if action:
                actions.append(
                    TickAction(
                        conversation_id=action.conversation_id,
                        merchant_id=action.merchant_id,
                        customer_id=action.customer_id,
                        send_as=action.send_as,
                        trigger_id=action.trigger_id,
                        template_name=action.template_name,
                        template_params=action.template_params,
                        body=action.body,
                        cta=action.cta,
                        suppression_key=action.suppression_key,
                        rationale=action.rationale,
                    )
                )
        except Exception as e:
            logger.error(
                "trigger_processing_failed",
                trigger_id=trigger_id,
                error=str(e),
            )
            # Continue processing other triggers
            continue
    
    logger.info("tick_completed", actions_generated=len(actions))
    
    return TickResponse(actions=actions)


@router.post("/v1/reply", response_model=ReplyResponse)
async def reply(
    request: ReplyRequest,
    conversation_store: ConversationStore = Depends(get_conversation_store),
    intent_detector: IntentDetector = Depends(get_intent_detector),
    context_store: ContextStore = Depends(get_context_store),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> ReplyResponse:
    """Handle merchant/customer reply."""
    logger.info(
        "reply_received",
        conversation_id=request.conversation_id,
        from_role=request.from_role,
        turn_number=request.turn_number,
    )
    
    # Get or create conversation session
    session = conversation_store.get_session(request.conversation_id)
    if not session:
        if request.turn_number != 1:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conversation_store.create_session(
            conversation_id=request.conversation_id,
            merchant_id=request.merchant_id,
            customer_id=request.customer_id,
        )
        session = conversation_store.get_session(request.conversation_id)
    
    # Detect auto-reply
    auto_reply = conversation_store.detect_auto_reply(
        request.conversation_id, request.message
    )
    
    # Detect intent
    intent = intent_detector.detect_intent(request.message)
    
    # Add turn to conversation
    conversation_store.add_turn(
        conversation_id=request.conversation_id,
        from_role=request.from_role,
        message=request.message,
        auto_reply_detected=auto_reply,
        intent=intent,
    )
    
    # Deterministic State Machine & Action Decision Rules
    if auto_reply:
        if session.auto_reply_count == 1:
            fallback_body = "Understood. Is there someone else I could connect with about this?"
            fallback_cta = "open_ended"
            fallback_rationale = "Auto-reply detected - attempting clarification"
        elif session.auto_reply_count == 2:
            conversation_store.transition_state(
                request.conversation_id, ConversationState.WAITING
            )
            return ReplyResponse(
                action="wait",
                wait_seconds=86400,
                rationale="Second consecutive auto-reply detected - waiting 24 hours",
            )
        else:
            conversation_store.transition_state(
                request.conversation_id, ConversationState.ENDED
            )
            return ReplyResponse(
                action="end",
                rationale="Multiple auto-replies detected - ending conversation",
            )
    elif intent == "REJECTION":
        conversation_store.transition_state(
            request.conversation_id, ConversationState.ENDED
        )
        return ReplyResponse(
            action="end",
            rationale="Merchant not interested - ending conversation gracefully",
        )
    elif intent == "COMMITMENT":
        conversation_store.transition_state(
            request.conversation_id, ConversationState.ACTION
        )
        fallback_body = (
            "I'm preparing the campaign draft now using the current context. "
            "I'll also line up the next Google Business post. Reply CONFIRM "
            "and I'll finalize both."
        )
        fallback_cta = "binary_confirm"
        fallback_rationale = "Merchant committed - transitioning to action"
    elif intent == "QUESTION":
        fallback_body = (
            "That part is outside this workflow, so I'll keep this focused on "
            "the current business action. I can prepare the draft from the "
            "verified context now. Reply CONFIRM to proceed."
        )
        fallback_cta = "open_ended"
        fallback_rationale = "Merchant asked question - providing clarification"
    else:  # NEUTRAL / INFORMATION_PROVIDED / Default
        fallback_body = (
            "I've noted this and am preparing the next business draft from the "
            "current context. Reply CONFIRM if you want me to finalize it now."
        )
        fallback_cta = "binary_confirm"
        fallback_rationale = "Continuing conversation"

    # Action is "send": Attempt LLM realization with fallback safety
    try:
        merchant_id = session.merchant_id or request.merchant_id
        merchant = context_store.merchants.get(merchant_id) if merchant_id else None
        category = (
            context_store.categories.get(merchant.category_slug)
            if (merchant and merchant.category_slug)
            else None
        )
        customer = (
            context_store.customers.get(session.customer_id)
            if session.customer_id
            else None
        )

        history_facts = [
            f"{turn.from_role}: {turn.message}"
            for turn in session.history[-3:]
        ] or [f"merchant: {request.message}"]

        card_cta = (
            "binary_yes_stop"
            if fallback_cta in ("binary_confirm", "binary_yes_stop")
            else "open_ended"
        )

        card = DecisionCard(
            decision=f"Respond to merchant message (intent: {intent})",
            priority=3,
            facts=history_facts[:5],
            reason=f"Merchant sent turn {request.turn_number} with intent {intent}",
            cta=card_cta,
            tone=category.voice.tone if (category and category.voice) else "warm_retail",
            audience="merchant",
            send_as="vera",
            constraints={"max_body_length": 500},
            suppression_key=f"reply:{request.conversation_id}:{request.turn_number}",
            merchant_id=merchant_id or "unknown",
            customer_id=session.customer_id or request.customer_id,
            trigger_id="reply",
        )

        prompt = prompt_compiler.compile(
            card=card,
            merchant=merchant,
            category=category,
            customer=customer,
            trigger=None,
        )

        cache_key = f"reply:{request.conversation_id}:{request.turn_number}"
        raw_response = await asyncio.wait_for(
            asyncio.to_thread(llm_provider.compose, prompt, cache_key),
            timeout=7.0,
        )

        parsed, validation = output_validator.validate_raw_response(
            raw_response,
            card=card,
            category=category,
            merchant=merchant,
            customer=customer,
            trigger=None,
        )

        if validation.valid and parsed and parsed.body:
            return ReplyResponse(
                action="send",
                body=parsed.body,
                cta=parsed.cta or fallback_cta,
                rationale=parsed.rationale or fallback_rationale,
            )
        else:
            logger.warning(
                "reply_llm_validation_failed",
                errors=validation.errors if validation else [],
                conversation_id=request.conversation_id,
            )
    except Exception as e:
        logger.warning(
            "reply_llm_fallback_used",
            error=str(e),
            conversation_id=request.conversation_id,
        )

    # Fallback to deterministic response if LLM or validation failed or timed out
    return ReplyResponse(
        action="send",
        body=fallback_body,
        cta=fallback_cta,
        rationale=fallback_rationale,
    )
