"""Conversation memory with state machine and suppression tracking."""

import threading
from datetime import datetime, timedelta

from app.models.conversation import ConversationSession, ConversationState, ConversationTurn
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ConversationStore:
    """Thread-safe conversation memory store."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._suppression_log: dict[str, datetime] = {}
        self._lock = threading.RLock()
        logger.info("conversation_store_initialized")

    def create_session(
        self,
        conversation_id: str,
        merchant_id: str,
        customer_id: str | None = None,
    ) -> ConversationSession:
        """Create a new conversation session."""
        with self._lock:
            session = ConversationSession(
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
            )
            self._sessions[conversation_id] = session
            logger.info(
                "conversation_created",
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
            )
            return session

    def get_session(self, conversation_id: str) -> ConversationSession | None:
        """Get an existing conversation session."""
        with self._lock:
            return self._sessions.get(conversation_id)

    def add_turn(
        self,
        conversation_id: str,
        from_role: str,
        message: str,
        engagement: str | None = None,
        auto_reply_detected: bool = False,
        intent: str | None = None,
    ) -> None:
        """Add a turn to a conversation."""
        with self._lock:
            session = self._sessions.get(conversation_id)
            if not session:
                logger.warning("conversation_not_found", conversation_id=conversation_id)
                return

            turn = ConversationTurn(
                ts=datetime.utcnow(),
                from_role=from_role,  # type: ignore
                message=message,
                engagement=engagement,
                auto_reply_detected=auto_reply_detected,
                intent=intent,
            )
            session.history.append(turn)
            session.updated_at = datetime.utcnow()

            if auto_reply_detected:
                session.auto_reply_count += 1

            logger.debug(
                "conversation_turn_added",
                conversation_id=conversation_id,
                from_role=from_role,
                auto_reply_detected=auto_reply_detected,
                intent=intent,
            )

    def transition_state(
        self, conversation_id: str, new_state: ConversationState
    ) -> None:
        """Transition conversation to a new state."""
        with self._lock:
            session = self._sessions.get(conversation_id)
            if not session:
                logger.warning("conversation_not_found", conversation_id=conversation_id)
                return

            old_state = session.state
            session.state = new_state
            session.updated_at = datetime.utcnow()

            logger.info(
                "conversation_state_transition",
                conversation_id=conversation_id,
                old_state=old_state.value,
                new_state=new_state.value,
            )

    def record_suppression(self, suppression_key: str) -> None:
        """Record a suppression key to prevent duplicates."""
        with self._lock:
            self._suppression_log[suppression_key] = datetime.utcnow()
            logger.debug("suppression_recorded", suppression_key=suppression_key)

    def is_suppressed(self, suppression_key: str, window_days: int = 7) -> bool:
        """Check if a suppression key was used recently."""
        with self._lock:
            last_used = self._suppression_log.get(suppression_key)
            if not last_used:
                return False

            age = datetime.utcnow() - last_used
            return age < timedelta(days=window_days)

    def cleanup_old_suppressions(self, days: int = 30) -> None:
        """Remove old suppression entries."""
        with self._lock:
            cutoff = datetime.utcnow() - timedelta(days=days)
            keys_to_remove = [
                key
                for key, ts in self._suppression_log.items()
                if ts < cutoff
            ]
            for key in keys_to_remove:
                del self._suppression_log[key]

            if keys_to_remove:
                logger.info(
                    "suppressions_cleaned", removed_count=len(keys_to_remove)
                )

    def detect_auto_reply(self, conversation_id: str, message: str) -> bool:
        """
        Deterministic auto-reply detection.
        
        Rules:
        1. Same message repeated 3+ times
        2. Contains auto-reply indicators
        3. Matches common WhatsApp Business templates
        """
        with self._lock:
            session = self._sessions.get(conversation_id)
            if not session:
                return False

            # Rule 1: Same message repeated
            merchant_messages = [
                turn.message
                for turn in session.history
                if turn.from_role == "merchant"
            ]
            if merchant_messages.count(message) >= 2:  # This would be the 3rd
                logger.info(
                    "auto_reply_detected_repetition",
                    conversation_id=conversation_id,
                    message_preview=message[:50],
                )
                return True

            # Rule 2: Auto-reply indicators
            auto_reply_phrases = [
                "automated assistant",
                "auto-reply",
                "out of office",
                "automatic response",
                "away from",
                "currently unavailable",
            ]
            message_lower = message.lower()
            for phrase in auto_reply_phrases:
                if phrase in message_lower:
                    logger.info(
                        "auto_reply_detected_phrase",
                        conversation_id=conversation_id,
                        phrase=phrase,
                    )
                    return True

            # Rule 3: Common templates
            common_templates = [
                "thank you for contacting",
                "thanks for your message",
                "we will get back to you",
                "aapki jaankari ke liye bahut-bahut shukriya",
            ]
            for template in common_templates:
                if template in message_lower:
                    logger.info(
                        "auto_reply_detected_template",
                        conversation_id=conversation_id,
                        template=template,
                    )
                    return True

            return False
