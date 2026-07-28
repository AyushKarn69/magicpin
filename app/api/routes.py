"""FastAPI routes for challenge endpoints."""

import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    get_context_manager,
    get_conversation_store,
    get_decision_engine,
    get_intent_detector,
    get_knowledge_graph,
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
from app.engine.decision_engine import DecisionEngine
from app.memory.conversation_store import ConversationStore
from app.memory.intent_detector import IntentDetector
from app.models.conversation import ConversationState
from app.utils.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

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
        return JSONResponse(
            status_code=400,
            content={
                "accepted": False,
                "reason": "invalid_scope",
                "details": f"Unsupported scope: {request.scope}",
            },
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
            return JSONResponse(
                status_code=409,
                content={
                    "accepted": False,
                    "reason": "stale_version",
                    "current_version": current_version,
                },
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
        # Create a new conversation session if it doesn't exist
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
    
    # Handle auto-reply
    if auto_reply:
        if session.auto_reply_count >= 2:
            # End conversation after 2 auto-replies
            conversation_store.transition_state(
                request.conversation_id, ConversationState.ENDED
            )
            return ReplyResponse(
                action="end",
                rationale="Multiple auto-replies detected - ending conversation",
            )
        else:
            # Try one more time
            return ReplyResponse(
                action="send",
                body="Understood. Is there someone else I could connect with about this?",
                cta="open_ended",
                rationale="Auto-reply detected - attempting clarification",
            )
    
    # Handle intent-based transitions
    if intent == "COMMITMENT":
        # Transition to ACTION state on commitment (regardless of current state)
        conversation_store.transition_state(
            request.conversation_id, ConversationState.ACTION
        )
        return ReplyResponse(
            action="send",
            body=(
                "I'm preparing the campaign draft now using the current context. "
                "I'll also line up the next Google Business post. Reply CONFIRM "
                "and I'll finalize both."
            ),
            cta="binary_confirm",
            rationale="Merchant committed - transitioning to action",
        )
    
    elif intent == "REJECTION":
        conversation_store.transition_state(
            request.conversation_id, ConversationState.ENDED
        )
        return ReplyResponse(
            action="end",
            rationale="Merchant not interested - ending conversation gracefully",
        )
    
    elif intent == "QUESTION":
        return ReplyResponse(
            action="send",
            body=(
                "That part is outside this workflow, so I'll keep this focused on "
                "the current business action. I can prepare the draft from the "
                "verified context now. Reply CONFIRM to proceed."
            ),
            cta="open_ended",
            rationale="Merchant asked question - providing clarification",
        )
    
    # Default: acknowledge and continue
    return ReplyResponse(
        action="send",
        body=(
            "I've noted this and am preparing the next business draft from the "
            "current context. Reply CONFIRM if you want me to finalize it now."
        ),
        cta="binary_confirm",
        rationale="Continuing conversation",
    )
